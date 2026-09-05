#!/usr/bin/env python3
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys

import psycopg2

import forecast_intel
from thermal_model.actions import parse_thermal_message
from thermal_model.artifacts import ArtifactRegistry, DEFAULT_STATE_DIRECTORY
from thermal_model.dataset import latent_mass_from_series
from thermal_model.journal import ActionJournal, JournalUnavailable, audit_schema
from thermal_model.pipeline import (
    TrainingRefused,
    build_unavailable_shadow,
    run_backtest,
    run_shadow,
    run_training,
    write_shadow_output,
)
from thermal_model.schema import ModeEvent, THERMAL_ITEMS, validate_shadow_output


DEFAULT_SHADOW_PATH = DEFAULT_STATE_DIRECTORY.parent / "shadow.json"
DEFAULT_TRAINING_DAYS = 400
THERMAL_MODEL_ITEM = "Thermal_Model_JSON"
MAX_SHADOW_BYTES = 16 * 1024
RUNTIME_REVISION_PATHS = (
    "thermal_intel.py",
    "forecast_intel.py",
    "thermal_model/__init__.py",
    "thermal_model/actions.py",
    "thermal_model/artifacts.py",
    "thermal_model/behavior.py",
    "thermal_model/dataset.py",
    "thermal_model/dynamics.py",
    "thermal_model/evaluation.py",
    "thermal_model/journal.py",
    "thermal_model/pipeline.py",
    "thermal_model/schema.py",
    "thermal_model/solar.py",
)


def _aware_iso(value):
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include timezone information")
    return parsed


def _build_parser():
    parser = argparse.ArgumentParser(description="Local thermal intelligence tooling")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    subparsers.add_parser(
        "schema-audit",
        help="read-only exact thermal_intel PostgreSQL schema audit",
    )

    journal = subparsers.add_parser("journal", help="append one local THERMAL message")
    journal.add_argument("--message-file", required=True, type=Path)
    journal.add_argument("--idempotency-key", required=True)
    journal.add_argument("--received-at", type=_aware_iso)

    for name, help_text in (
        ("train", "fit, backtest, and promote one offline candidate"),
        ("backtest", "write one chronological offline evaluation report"),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--start", type=_aware_iso)
        command.add_argument("--end", type=_aware_iso)
        command.add_argument(
            "--state-dir", type=Path, default=DEFAULT_STATE_DIRECTORY
        )

    shadow = subparsers.add_parser(
        "shadow", help="write one bounded shadow prediction"
    )
    shadow.add_argument("--output", type=Path, default=DEFAULT_SHADOW_PATH)
    shadow.add_argument(
        "--publish",
        action="store_true",
        help="publish the validated shadow JSON to Thermal_Model_JSON",
    )
    return parser


def _jdbc_series(item, start, end):
    """Read exactly the OpenHAB JDBC persistence service for [start, end)."""
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    payload = forecast_intel.oh_get(
        f"/persistence/items/{item}?serviceId=jdbc"
        f"&starttime={start_utc.strftime(fmt)}"
        f"&endtime={end_utc.strftime(fmt)}"
    )
    points = []
    for point in payload.get("data", []):
        try:
            at = datetime.fromtimestamp(point["time"] / 1000, tz=timezone.utc)
            value = float(str(point["state"]).split()[0])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if start_utc <= at < end_utc:
            points.append((at, value))
    return points


def _schema_audit_command(parser):
    admin_dsn = os.environ.get("THERMAL_DATABASE_ADMIN_URL")
    dsn = admin_dsn or os.environ.get("THERMAL_DATABASE_URL")
    if not dsn:
        parser.error(
            "THERMAL_DATABASE_ADMIN_URL or THERMAL_DATABASE_URL is required"
        )
    runtime_role = os.environ.get("THERMAL_DATABASE_RUNTIME_ROLE")
    expected_owner = os.environ.get("THERMAL_DATABASE_EXPECTED_OWNER")
    if not runtime_role:
        parser.error("THERMAL_DATABASE_RUNTIME_ROLE is required")
    if not expected_owner:
        parser.error("THERMAL_DATABASE_EXPECTED_OWNER is required")
    result = audit_schema(
        dsn,
        runtime_role=runtime_role,
        expected_owner=expected_owner,
        require_current_user_owner=admin_dsn is not None,
    )
    print(
        json.dumps(
            {
                "fingerprint": result["fingerprint"],
                "schema": result["schema"],
                "status": "exact",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _journal(args, parser):
    dsn = os.environ.get("THERMAL_DATABASE_URL")
    if not dsn:
        parser.error("THERMAL_DATABASE_URL is required")
    try:
        payload = args.message_file.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        parser.error(f"unable to read UTF-8 message file: {exc}")
    received_at = args.received_at or datetime.now(timezone.utc)
    parsed = parse_thermal_message(text, received_at, args.idempotency_key)
    journal = ActionJournal(dsn)
    inserted = journal.append_batch(parsed.actions, parsed.modes, payload=payload)
    stored_actions = journal.events_for_receipt(args.idempotency_key)
    stored_modes = journal.modes_for_receipt(args.idempotency_key)
    receipt = {
        "action_event_ids": [event.event_id for event in stored_actions],
        "idempotency_key": args.idempotency_key,
        "inserted": inserted,
        "mode_event_ids": [event.event_id for event in stored_modes],
    }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


def _date_range(args, now):
    end = args.end or now
    start = args.start or end - timedelta(days=DEFAULT_TRAINING_DAYS)
    if end <= start:
        raise ValueError("end must be after start")
    return start, end


def _runtime_manifest_revision(root):
    root = Path(root)
    digest = sha256()
    for relative in RUNTIME_REVISION_PATHS:
        encoded_name = relative.encode("utf-8")
        try:
            content = (root / relative).read_bytes()
        except OSError as exc:
            raise RuntimeError(
                f"runtime revision file unavailable: {relative}"
            ) from exc
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _code_revision():
    return _runtime_manifest_revision(Path(__file__).resolve().parent)


def _offline_journal(parser):
    dsn = os.environ.get("THERMAL_DATABASE_URL")
    if not dsn:
        parser.error("THERMAL_DATABASE_URL is required")
    return ActionJournal(dsn)


def _training_kwargs(args, parser, now):
    start, end = _date_range(args, now)
    return {
        "start": start,
        "end": end,
        "registry": ArtifactRegistry(args.state_dir),
        "journal": _offline_journal(parser),
        "series_reader": _jdbc_series,
        "forecast_reader": forecast_intel.fetch_forecast,
        "clock": lambda: now,
        "revision_reader": _code_revision,
        "site_settings_loader": forecast_intel.load_site_settings,
    }


def _train(args, parser, now):
    try:
        result = run_training(**_training_kwargs(args, parser, now))
    except TrainingRefused as exc:
        print(
            json.dumps(
                {"status": "refused", "reasons": list(exc.reasons)},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "promoted",
                "codeRevision": result.artifact.code_revision,
                "trainedThrough": result.artifact.trained_through,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


def _backtest(args, parser, now):
    report = run_backtest(**_training_kwargs(args, parser, now))
    print(
        json.dumps(
            {
                "status": "backtested",
                "generatedAt": report["generated_at"],
                "report": str(Path(args.state_dir).expanduser() / "backtest-report.json"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


_MODE_TIMELINE_FIELD = "_modeTimeline"
_VALID_MODES = {"spring", "warm", "fall_charge", "winter"}


def _mode_at(timeline, at):
    at_utc = at.astimezone(timezone.utc)
    active = [
        event
        for event in timeline
        if event.effective_at.astimezone(timezone.utc) <= at_utc
    ]
    if not active:
        return None
    return max(
        active,
        key=lambda event: (
            event.effective_at.astimezone(timezone.utc),
            event.received_at.astimezone(timezone.utc),
            event.event_id,
        ),
    ).mode


def _apply_mode_timeline(rows, modes, now):
    """Project only correction-aware journal modes; never infer from calendar."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("mode timeline origin must include timezone information")
    rows = tuple(rows)
    modes = tuple(modes)
    if not all(isinstance(event, ModeEvent) for event in modes):
        raise TypeError("mode timeline must contain only ModeEvent records")
    ordered = tuple(
        sorted(
            modes,
            key=lambda event: (
                event.effective_at.astimezone(timezone.utc),
                event.received_at.astimezone(timezone.utc),
                event.event_id,
            ),
        )
    )
    active = _mode_at(ordered, now)
    if active not in _VALID_MODES:
        raise ValueError("no evidence-backed active thermal mode")
    timeline = tuple(
        (event.effective_at.astimezone(timezone.utc), event.mode)
        for event in ordered
    )
    projected = []
    for row in rows:
        at = row.get("at")
        if isinstance(at, str):
            at = datetime.fromisoformat(at)
        if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("forecast timestamp must include timezone information")
        mode = _mode_at(ordered, at)
        if mode not in _VALID_MODES:
            raise ValueError("forecast precedes evidence-backed active thermal mode")
        projected.append({**row, "at": at, "mode": mode, _MODE_TIMELINE_FIELD: timeline})
    return projected


def _forecast_rows(snapshot, now):
    _, _, detail = forecast_intel.build_forecast_payloads(snapshot, [], now)
    rows = []
    for day in detail["days"]:
        for row in day["hours"]:
            rows.append({**row, "at": datetime.fromisoformat(row["at"])})
    return rows


def _five_minute_bucket(at):
    at_utc = at.astimezone(timezone.utc)
    return at_utc.replace(
        minute=at_utc.minute - at_utc.minute % 5,
        second=0,
        microsecond=0,
    )


def _aligned_observed_history(histories):
    """Join independent Item histories by UTC five-minute bucket.

    Each Item/bucket uses its chronologically latest finite reading; an exact
    timestamp tie uses the larger numeric value so input ordering cannot alter
    the representative. Buckets missing either hallway or mass are omitted.
    """
    bucketed = {}
    for role in ("air", "mass"):
        representatives = {}
        for at, raw_value in histories.get(role, ()):
            if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            bucket = _five_minute_bucket(at)
            candidate = (at.astimezone(timezone.utc), value)
            if bucket not in representatives or candidate > representatives[bucket]:
                representatives[bucket] = candidate
        bucketed[role] = {
            bucket: candidate[1] for bucket, candidate in representatives.items()
        }
    return [
        {
            "at": bucket,
            "hallwayF": bucketed["air"][bucket],
            "massF": bucketed["mass"][bucket],
        }
        for bucket in sorted(set(bucketed["air"]) & set(bucketed["mass"]))[-25:]
    ]


def _current_states(now, series_reader=None, state_reader=None):
    series_reader = series_reader or _jdbc_series
    state_reader = state_reader or (lambda item: forecast_intel.oh_get(f"/items/{item}"))
    start = now - timedelta(hours=24)
    end = now + timedelta(seconds=1)
    histories = {
        role: tuple(series_reader(item, start, end))
        for role, item in THERMAL_ITEMS.items()
    }
    current = {}
    for role, item in THERMAL_ITEMS.items():
        # JDBC records changes; an unchanged reading can still be freshly
        # reported. Only the Item's actual update timestamp proves freshness.
        state = state_reader(item)
        if not isinstance(state, dict) or state.get("name") != item:
            raise ValueError(f"invalid current {role} Item identity")
        timestamp = state.get("lastStateUpdate")
        if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp <= 0:
            raise ValueError(f"missing or invalid current {role} update timestamp")
        at = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)
        parts = str(state.get("state", "")).split()
        if not parts:
            raise ValueError(f"missing current {role} value")
        value = float(parts[0])
        if not math.isfinite(value):
            raise ValueError(f"invalid current {role} value")
        current[role] = {"at": at, "value": value}
        if at <= now and (not histories[role] or at > max(point[0] for point in histories[role])):
            histories[role] = (*histories[role], (at, value))

    latent_mass = latent_mass_from_series(histories["mass"])
    if latent_mass is not None and current.get("mass") is not None:
        _, value = latent_mass
        current["mass"] = {**current["mass"], "value": value}

    current["observed"] = _aligned_observed_history(histories)
    return current


def publish_shadow_output(payload, put_state=None):
    """Validate and publish exactly one observational thermal shadow state."""
    validate_shadow_output(payload)
    if payload["confidence"]["grade"] == "unavailable":
        raise ValueError("unavailable thermal shadow output cannot be published")
    encoded = json.dumps(payload, separators=(",", ":"))
    if len(encoded.encode("utf-8")) >= MAX_SHADOW_BYTES:
        raise ValueError("shadow output exceeds the 16 KiB publication bound")
    transport = forecast_intel.oh_put_state if put_state is None else put_state
    transport(THERMAL_MODEL_ITEM, encoded)
    return encoded


def _shadow(args, now, put_state=None, journal=None):
    current = None
    failed_input = "site settings input"
    try:
        forecast_intel.load_site_settings()
        failed_input = "current state input"
        current = _current_states(now)
        failed_input = "forecast input"
        snapshot = forecast_intel.fetch_forecast()
        rows = _forecast_rows(
            snapshot, now.astimezone(forecast_intel.MOUNTAIN)
        )
        if journal is not None or not all(
            row.get("mode") in _VALID_MODES for row in rows
        ):
            failed_input = "mode journal input"
            if journal is None:
                dsn = os.environ.get("THERMAL_DATABASE_URL")
                if not dsn:
                    raise ValueError("THERMAL_DATABASE_URL is required for thermal mode evidence")
                journal = ActionJournal(dsn)
            if not rows:
                raise ValueError("forecast input contains no rows")
            horizon_end = max(
                (
                    datetime.fromisoformat(row["at"])
                    if isinstance(row.get("at"), str)
                    else row["at"]
                )
                for row in rows
            )
            modes = journal.effective_modes(
                now, horizon_end + timedelta(microseconds=1)
            )
            rows = _apply_mode_timeline(rows, modes, now)
        failed_input = "accepted artifact input"
        output = run_shadow(
            registry=ArtifactRegistry(DEFAULT_STATE_DIRECTORY),
            current=current,
            forecast=rows,
            now=now,
            site_timezone=forecast_intel.MOUNTAIN,
        )
    except (JournalUnavailable, psycopg2.Error):
        output = build_unavailable_shadow(
            now=now,
            reasons=("action journal unavailable",),
            current=current,
            fallback_reason="action journal unavailable",
        )
    except (
        KeyError, OSError, RuntimeError, TypeError, ValueError
    ) as exc:
        output = build_unavailable_shadow(
            now=now, reasons=(str(exc),), current=current,
            fallback_reason=f"{failed_input} unavailable",
        )
    write_shadow_output(args.output, output)
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":"))
    unavailable = output["confidence"]["grade"] == "unavailable"
    if getattr(args, "publish", False) and not unavailable:
        publish_shadow_output(output, put_state=put_state)
    print(encoded, file=sys.stderr if unavailable else sys.stdout)
    return int(unavailable)


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        if args.subcommand == "schema-audit":
            _schema_audit_command(parser)
            return 0
        if args.subcommand == "journal":
            _journal(args, parser)
            return 0
        if args.subcommand == "train":
            return _train(args, parser, now)
        if args.subcommand == "backtest":
            return _backtest(args, parser, now)
        if args.subcommand == "shadow":
            return _shadow(args, now)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"status": "error", "reasons": [str(exc)]},
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    parser.error("unsupported subcommand")


if __name__ == "__main__":
    raise SystemExit(main())
