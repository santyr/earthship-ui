#!/usr/bin/env python3
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import forecast_intel
from thermal_model.actions import parse_thermal_message
from thermal_model.artifacts import ArtifactRegistry, DEFAULT_STATE_DIRECTORY
from thermal_model.journal import ActionJournal
from thermal_model.pipeline import (
    TrainingRefused,
    build_unavailable_shadow,
    run_backtest,
    run_shadow,
    run_training,
    write_shadow_output,
)
from thermal_model.schema import THERMAL_ITEMS


DEFAULT_SHADOW_PATH = DEFAULT_STATE_DIRECTORY.parent / "shadow.json"
DEFAULT_TRAINING_DAYS = 90


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
        "shadow", help="write one bounded local-only shadow prediction"
    )
    shadow.add_argument("--output", type=Path, default=DEFAULT_SHADOW_PATH)
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


def _code_revision():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        revision = result.stdout.strip().lower()
        if 7 <= len(revision) <= 64 and all(
            character in "0123456789abcdef" for character in revision
        ):
            return revision
    except (OSError, subprocess.SubprocessError):
        pass
    digest = sha256()
    package = Path(__file__).resolve().parent / "thermal_model"
    for path in sorted(package.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


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


def _season_mode(at):
    month = at.month
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4):
        return "spring"
    if month in (5, 6, 7, 8, 9):
        return "warm"
    return "fall_charge"


def _forecast_rows(snapshot, now):
    _, _, detail = forecast_intel.build_forecast_payloads(snapshot, [], now)
    rows = []
    for day in detail["days"]:
        for row in day["hours"]:
            at = datetime.fromisoformat(row["at"])
            rows.append({**row, "mode": _season_mode(at)})
    return rows


def _current_states(now, series_reader=None):
    series_reader = series_reader or _jdbc_series
    start = now - timedelta(hours=24)
    end = now + timedelta(seconds=1)
    histories = {
        role: tuple(series_reader(item, start, end))
        for role, item in THERMAL_ITEMS.items()
    }
    current = {}
    for role, points in histories.items():
        if points:
            at, value = max(points, key=lambda point: point[0])
            current[role] = {"at": at, "value": value}
        elif role != "glazing":
            current[role] = None

    air = {at: value for at, value in histories["air"]}
    mass = {at: value for at, value in histories["mass"]}
    current["observed"] = [
        {"at": at, "hallwayF": air[at], "massF": mass[at]}
        for at in sorted(set(air) & set(mass))[-25:]
    ]
    return current


def _shadow(args, now):
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
        failed_input = "accepted artifact input"
        output = run_shadow(
            registry=ArtifactRegistry(DEFAULT_STATE_DIRECTORY),
            current=current,
            forecast=rows,
            now=now,
            site_timezone=forecast_intel.MOUNTAIN,
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
    print(encoded, file=sys.stderr if unavailable else sys.stdout)
    return int(unavailable)


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
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
