#!/usr/bin/env python3
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import sys
import time

import psycopg2

import forecast_intel
from thermal_model.actions import parse_thermal_message
from thermal_model.artifacts import ArtifactRegistry, DEFAULT_STATE_DIRECTORY
from thermal_model.forcing_capture import capture_shadow_inputs
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
    "thermal_temperature_runtime.py",
    "thermal_radiation_runtime.py",
    "weather_radiation_reader.py",
    "weather_radiation_history.py",
    "weather_radiation_evidence.py",
    "weather_radiation_config.py",
    "hourly_temperature_runtime.py",
    "daily_temperature_runtime.py",
    "weather_temperature_reader.py",
    "weather_temperature_history.py",
    "weather_temperature_evidence.py",
    "weather_temperature_config.py",
    "thermal_model/temperature_history.py",
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
        if name == "train":
            command.add_argument(
                "--fit-evidence-dir", type=Path,
                help="record strict final-fit evidence in an existing private directory (off-host qualification)",
            )

    shadow = subparsers.add_parser(
        "shadow", help="write one bounded shadow prediction"
    )
    shadow.add_argument("--output", type=Path, default=DEFAULT_SHADOW_PATH)
    shadow.add_argument("--model-directory", type=Path, default=DEFAULT_STATE_DIRECTORY,
        help="explicit model registry for a compatible staged recovery runtime")
    shadow.add_argument(
        "--publish",
        action="store_true",
        help="publish the validated shadow JSON to Thermal_Model_JSON",
    )
    release = subparsers.add_parser("release", help="recompute thermal release qualification and write explicit v2 output")
    release.add_argument("--evidence-inputs", required=True, type=Path)
    release.add_argument("--model-directory", type=Path, default=DEFAULT_STATE_DIRECTORY)
    release.add_argument("--output", type=Path, default=DEFAULT_STATE_DIRECTORY.parent / "release.json")
    release.add_argument("--publish", action="store_true", help="publish one qualified or unavailable v2 state")
    release.add_argument("--origin-capture-dir", type=Path, help="private immutable v2 origin archive for accepted publications")
    return parser


def _jdbc_series(item, start, end):
    """Read JDBC history, retaining timestamped invalid states as NaN barriers."""
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
        except (KeyError, TypeError, ValueError):
            continue
        try:
            value = float(str(point["state"]).split()[0])
        except (KeyError, TypeError, ValueError, IndexError):
            # Dropping UNDEF/NULL would permit interpolation across a known
            # unavailable observation. Preserve its actual timestamp instead.
            value = math.nan
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


def _journal(args, parser, *, now=None):
    dsn = os.environ.get("THERMAL_DATABASE_URL")
    if not dsn:
        parser.error("THERMAL_DATABASE_URL is required")
    try:
        payload = args.message_file.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        parser.error(f"unable to read UTF-8 message file: {exc}")
    now = now or datetime.now(timezone.utc)
    received_at = args.received_at or now
    if received_at > now:
        raise ValueError('confirmation receipt cannot be in the future')
    parsed = parse_thermal_message(text, received_at, args.idempotency_key)
    if any(event.effective_at > received_at for event in (*parsed.actions, *parsed.modes)):
        raise ValueError('future thermal actions or modes are plans, not completed confirmations')
    journal = ActionJournal(dsn)
    inserted = journal.append_batch(parsed.actions, parsed.modes, payload=payload)
    stored_actions = journal.events_for_receipt(args.idempotency_key)
    stored_modes = journal.modes_for_receipt(args.idempotency_key)
    # A successful append alone is not an acknowledgement of exact storage.
    # Compare full immutable records, not just IDs/counts, before emitting success.
    for expected, stored in ((parsed.actions, stored_actions), (parsed.modes, stored_modes)):
        expected_by_id = {event.event_id: event for event in expected}
        stored_by_id = {event.event_id: event for event in stored}
        if (len(expected_by_id) != len(expected) or len(stored_by_id) != len(stored)
                or expected_by_id != stored_by_id):
            raise ValueError('thermal journal readback does not match submitted confirmation')
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
    from thermal_temperature_runtime import configured_history
    start, end = _date_range(args, now)
    retain_raw = getattr(args, "fit_evidence_dir", None) is not None
    history = (configured_history(_jdbc_series, now, retain_raw=True)
        if retain_raw else configured_history(_jdbc_series, now))
    return {
        "start": start,
        "end": end,
        "registry": ArtifactRegistry(args.state_dir),
        "journal": _offline_journal(parser),
        "series_reader": history,
        "forecast_reader": forecast_intel.fetch_forecast,
        "clock": lambda: now,
        "revision_reader": _code_revision,
        "site_settings_loader": forecast_intel.load_site_settings,
    }


def _train(args, parser, now):
    proof_directory = getattr(args, "fit_evidence_dir", None)
    proof_writer = None
    source_writer = None
    if proof_directory is not None:
        from thermal_model.forcing_capture import _private_directory
        from thermal_model.fit_evidence import write_fit_evidence
        from thermal_model.training_sources import write_training_sources
        root = _private_directory(Path(proof_directory).expanduser().absolute())
        proof_writer = lambda artifact, proof: write_fit_evidence(root, proof, artifact)
        source_writer = lambda artifact, snapshot: write_training_sources(root, snapshot, artifact)
    kwargs = _training_kwargs(args, parser, now)
    if proof_writer is not None:
        kwargs["fit_evidence_writer"] = proof_writer
        kwargs["training_sources_writer"] = source_writer
    try:
        result = run_training(**kwargs)
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


def _current_states(now, series_reader=None, state_reader=None, *, origin_observer=None):
    from thermal_temperature_runtime import configured_shadow_temperatures
    from thermal_radiation_runtime import configured_shadow_radiation
    selected = (configured_shadow_temperatures(now) if origin_observer is None else
                configured_shadow_temperatures(now, origin_observer=origin_observer))
    qualified = dict(selected or {})
    radiation = configured_shadow_radiation(now)
    if radiation is not None:
        qualified['radiation'] = radiation
    series_reader = series_reader or _jdbc_series
    state_reader = state_reader or (lambda item: forecast_intel.oh_get(f"/items/{item}"))
    start = now - timedelta(hours=24)
    end = now + timedelta(seconds=1)
    histories = {
        role: qualified[role]['history'] if qualified is not None and role in qualified
              else tuple(series_reader(item, start, end))
        for role, item in THERMAL_ITEMS.items()
    }
    current = {}
    for role, item in THERMAL_ITEMS.items():
        if qualified is not None and role in qualified:
            current[role] = qualified[role]['current']
            at, value = current[role]['at'], current[role]['value']
            if not histories[role] or at > max(point[0] for point in histories[role]):
                histories[role] = (*histories[role], (at, value))
            continue
        # Legacy/other-source path retains its Item-update contract. An Item
        # update alone is not RF sensor receipt evidence; qualified roles above
        # never enter this fallback.
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



def publish_release_output(*, shadow, qualification_loader, now,
        artifact_sha256, runtime_sha256, sensor_epochs, forecast_rows=None, put_state=None):
    """Recompute qualification and publish one v2 state, including withdrawal.

    The caller supplies the current observed artifact/runtime/epochs and a
    trusted source-backed evaluator. Cached reports and active overrides cannot
    select the operating mode. Transport failure propagates to the caller.
    """
    from thermal_model.release import build_release_output
    output = build_release_output(shadow=shadow,
        qualification_loader=qualification_loader, now=now,
        artifact_sha256=artifact_sha256, runtime_sha256=runtime_sha256,
        sensor_epochs=sensor_epochs, forecast_rows=forecast_rows)
    _publish_validated_release(output, put_state=put_state)
    return output


def _publish_validated_release(output, put_state=None):
    from thermal_model.release import validate_release_output
    validate_release_output(output)
    encoded = json.dumps(output, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) >= MAX_SHADOW_BYTES:
        raise ValueError("thermal release exceeds the 16 KiB publication bound")
    transport = forecast_intel.oh_put_state if put_state is None else put_state
    # Unlike the legacy shadow publisher, unavailable v2 data must be sent:
    # otherwise the last active publication would survive a failed gate.
    transport(THERMAL_MODEL_ITEM, encoded)
    return output


def _origin_runtime_paths():
    paths = list(RUNTIME_REVISION_PATHS)
    if "thermal_model/runtime_bundle.py" not in paths:
        paths.append("thermal_model/runtime_bundle.py")
    return paths


def _origin_runtime_binding():
    from thermal_model.origin_capture import build_runtime_binding
    return build_runtime_binding(Path(__file__).resolve().parent, _origin_runtime_paths())



def _release_runtime_paths():
    return list(dict.fromkeys((*_origin_runtime_paths(),
        "thermal_model/origin_capture.py", "thermal_model/forcing_capture.py",
        "thermal_model/release.py", "thermal_model/graduation_policy.py",
        "thermal_model/graduation_statistics.py", "thermal_model/graduation_decision.py",
        "thermal_model/policy_registration.py", "thermal_model/graduation_evidence.py",
        "thermal_model/recent_cycles.py", "thermal_model/fit_evidence.py",
        "thermal_model/training_sources.py")))


def _release_runtime_binding():
    from thermal_model.origin_capture import build_runtime_binding
    return build_runtime_binding(Path(__file__).resolve().parent, _release_runtime_paths())


def _archive_original_publication(directory, *, output, artifact, snapshot, rows,
        current, origin_temperatures, runtime, inputs_available_at, published_at):
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.origin_capture import build_origin_capture, write_origin_capture
    from thermal_model.runtime_bundle import capture_runtime_bundle
    root = _private_directory(Path(directory))
    bundles = root / "runtime-bundles"
    try:
        bundles.mkdir(mode=0o700)
    except FileExistsError:
        pass
    capture_runtime_bundle(bundles, Path(__file__).resolve().parent,
        _origin_runtime_paths(), expected_binding=runtime)
    record = build_origin_capture(output=output, artifact=artifact, snapshot=snapshot,
        rows=rows, current=current, origin_temperatures=origin_temperatures,
        runtime=runtime, inputs_available_at=inputs_available_at,
        published_at=published_at, known_actions=None)
    return write_origin_capture(root, record)



def _archive_release_publication(directory, *, output, artifact, snapshot, rows,
        current, origin_temperatures, runtime, inputs_available_at, published_at):
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.origin_capture import build_release_origin_capture, write_release_origin_capture
    from thermal_model.runtime_bundle import capture_runtime_bundle
    root = _private_directory(Path(directory))
    bundles = root / "runtime-bundles"
    try:
        bundles.mkdir(mode=0o700)
    except FileExistsError:
        pass
    capture_runtime_bundle(bundles, Path(__file__).resolve().parent,
        _release_runtime_paths(), expected_binding=runtime)
    record = build_release_origin_capture(output=output, artifact=artifact, snapshot=snapshot,
        rows=rows, current=current, origin_temperatures=origin_temperatures,
        runtime=runtime, inputs_available_at=inputs_available_at,
        published_at=published_at, known_actions=None)
    return write_release_origin_capture(root, record)


def _shadow(args, now, put_state=None, journal=None, decision_clock=None,
            published_clock=None, output_handler=None):
    from thermal_temperature_runtime import validate_shadow_receipt_expiry
    from thermal_radiation_runtime import validate_shadow_radiation_expiry
    started = time.monotonic()
    started_at = now
    current = None
    origin_directory = (os.environ.get("THERMAL_ORIGIN_CAPTURE_DIR")
        if getattr(args, "publish", False) else None)
    origin_proofs = []
    artifact_used = []
    snapshot = None
    rows = []
    original_runtime = None
    collect_origin = bool(origin_directory or output_handler is not None)
    if collect_origin:
        try:
            original_runtime = (_release_runtime_binding() if output_handler is not None
                else _origin_runtime_binding())
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            # Missing observational proof never changes the default forecast.
            pass
    failed_input = "site settings input"
    try:
        forecast_intel.load_site_settings()
        failed_input = "current state input"
        current = (_current_states(now, origin_observer=origin_proofs.append)
            if collect_origin else _current_states(now))
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
        # The forecast fetch (and optional mode read) occurs after the command
        # starts. Stamp the decision only after those inputs are available; a
        # start-time stamp would falsely place them in the past for replay.
        decision_at = now if decision_clock is None else decision_clock()
        if (not isinstance(decision_at, datetime) or decision_at.tzinfo is None
                or decision_at.utcoffset() is None or decision_at < now):
            raise ValueError('shadow decision clock is invalid or moved backward')
        now = decision_at.astimezone(timezone.utc)
        failed_input = "accepted artifact input"
        output = run_shadow(
            registry=ArtifactRegistry(getattr(args, "model_directory", DEFAULT_STATE_DIRECTORY)),
            current=current,
            forecast=rows,
            now=now,
            site_timezone=forecast_intel.MOUNTAIN,
            artifact_observer=artifact_used.append,
        )
        # The model serializes to whole seconds. Preserve the post-input
        # decision clock's full precision for capture-safe provenance.
        if output.get('status') == 'shadow':
            output['generatedAt'] = now.isoformat()
        # The decision clock already includes input-fetch latency. Anchor total
        # monotonic elapsed time to command start, never add it twice. A forward
        # wall-clock change still cannot move expiry assessment into the past.
        evidence_check_at = max(now, started_at + timedelta(
            seconds=max(0, time.monotonic()-started)))
        validate_shadow_receipt_expiry(current, evidence_check_at)
        validate_shadow_radiation_expiry(current, evidence_check_at)
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
    if output_handler is not None:
        return output_handler(output, current=current, artifact_used=artifact_used,
            origin_proofs=origin_proofs, runtime=original_runtime,
            now=now, started_at=started_at, started=started,
            snapshot=snapshot, rows=rows)
    write_shadow_output(args.output, output)
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":"))
    unavailable = output["confidence"]["grade"] == "unavailable"
    if getattr(args, "publish", False) and not unavailable:
        publish_shadow_output(output, put_state=put_state)
        capture_dir = os.environ.get("THERMAL_SHADOW_CAPTURE_DIR")
        published_at = ((published_clock() if published_clock else datetime.now(timezone.utc))
            if origin_directory or capture_dir else None)
        if origin_directory:
            try:
                if len(origin_proofs) != 1 or len(artifact_used) != 1 or original_runtime is None:
                    raise ValueError("complete original native/runtime proof unavailable")
                _archive_original_publication(origin_directory, output=output,
                    artifact=artifact_used[0], snapshot=snapshot, rows=rows, current=current,
                    origin_temperatures=origin_proofs[0], runtime=original_runtime,
                    inputs_available_at=now, published_at=published_at)
            except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                print("thermal origin capture gap: original proof unavailable", file=sys.stderr)
        if capture_dir:
            try:
                if len(artifact_used) != 1:
                    raise ValueError('published artifact was not retained for capture')
                capture_shadow_inputs(
                    capture_dir, output=output, snapshot=snapshot, rows=rows,
                    current=current, inputs_available_at=now,
                    published_at=published_at,
                    artifact=artifact_used[0],
                )
            except (OSError, RuntimeError, TypeError, ValueError):
                # An observational archive failure cannot revoke an already
                # accepted UI publication; the missing replay proof is explicit.
                print('thermal forcing capture gap: input archive unavailable',
                      file=sys.stderr)
    print(encoded, file=sys.stderr if unavailable else sys.stdout)
    return int(unavailable)



def _release(args, now, put_state=None, journal=None, decision_clock=None,
             qualification_clock=None, published_clock=None):
    """Generate from original inputs, qualify afresh and deliver explicit v2."""
    from dataclasses import asdict
    from types import SimpleNamespace
    from thermal_model.forcing_capture import _canonical
    from thermal_model.graduation_decision import load_qualification_inputs
    from thermal_model.origin_capture import _temperatures
    from thermal_model.release import build_release_output, unavailable_release, write_release_output
    from thermal_temperature_runtime import validate_shadow_receipt_expiry
    from thermal_radiation_runtime import validate_shadow_radiation_expiry
    try:
        loader = load_qualification_inputs(args.evidence_inputs)
    except (OSError, RuntimeError, TypeError, ValueError):
        def loader(_):
            raise ValueError("original release evidence unavailable")

    def finish(shadow, **context):
        def assessment_clock():
            at = qualification_clock() if qualification_clock else datetime.now(timezone.utc)
            if (not isinstance(at, datetime) or at.utcoffset() is None or at < context['now']):
                raise ValueError("release clock invalid or moved backward")
            return max(at.astimezone(timezone.utc), context['started_at'] + timedelta(
                seconds=max(0, time.monotonic()-context['started'])))
        output = unavailable_release(context['now'])
        try:
            at = assessment_clock()
            if (len(context['artifact_used']) != 1 or len(context['origin_proofs']) != 1
                    or context['runtime'] is None):
                raise ValueError("complete actual artifact/runtime/native origin required")
            epochs, _ = _temperatures(context['origin_proofs'][0], context['current'],
                issued_at=context['now'], published_at=at)
            artifact_digest = sha256(_canonical(asdict(context['artifact_used'][0]))).hexdigest()
            runtime_digest = sha256(_canonical(context['runtime'])).hexdigest()
            output = build_release_output(shadow=shadow, qualification_loader=loader, now=at,
                artifact_sha256=artifact_digest, runtime_sha256=runtime_digest, sensor_epochs=epochs,
                forecast_rows=context['rows'])
            # Qualification can take time. Recheck original native expiry and
            # executing source identity immediately before persistence/delivery.
            completed = assessment_clock()
            _temperatures(context['origin_proofs'][0], context['current'],
                issued_at=context['now'], published_at=completed)
            validate_shadow_receipt_expiry(context['current'], completed)
            validate_shadow_radiation_expiry(context['current'], completed)
            if _release_runtime_binding() != context['runtime']:
                raise ValueError("executing release runtime changed during qualification")
            elapsed = (completed-context['now']).total_seconds()/60
            if elapsed > 20 or any(shadow['provenance']['currentAgeMinutes'][role]+elapsed > 20
                    for role in ('air','mass','outdoor','radiation')):
                raise ValueError("forecast or sensors expired during qualification")
            expires = output['release']['expiresAt']
            if expires is not None and completed >= datetime.fromisoformat(expires):
                raise ValueError("release qualification expired before delivery")
        except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError, OverflowError):
            output = unavailable_release(context['now'])
        write_release_output(args.output, output)
        if args.publish:
            _publish_validated_release(output, put_state=put_state)
            if output['status'] != 'unavailable':
                directory = getattr(args, 'origin_capture_dir', None) or os.environ.get('THERMAL_ORIGIN_CAPTURE_DIR')
                try:
                    if not directory:
                        raise ValueError("release origin archive not configured")
                    published = published_clock() if published_clock else datetime.now(timezone.utc)
                    _archive_release_publication(directory, output=output,
                        artifact=context['artifact_used'][0], snapshot=context['snapshot'],
                        rows=context['rows'], current=context['current'],
                        origin_temperatures=context['origin_proofs'][0], runtime=context['runtime'],
                        inputs_available_at=context['now'], published_at=published)
                except (ImportError, OSError, RuntimeError, TypeError, ValueError, IndexError):
                    # Do not invent proof or retry an already accepted state write.
                    print("thermal release capture gap: original proof unavailable", file=sys.stderr)
        unavailable = output['status'] == 'unavailable'
        print(json.dumps(output, sort_keys=True, separators=(",", ":")),
            file=sys.stderr if unavailable else sys.stdout)
        return int(unavailable)

    return _shadow(SimpleNamespace(publish=False,
        model_directory=getattr(args, "model_directory", DEFAULT_STATE_DIRECTORY)), now, journal=journal,
        decision_clock=decision_clock, output_handler=finish)


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        if args.subcommand == "schema-audit":
            _schema_audit_command(parser)
            return 0
        if args.subcommand == "journal":
            _journal(args, parser, now=now)
            return 0
        if args.subcommand == "train":
            return _train(args, parser, now)
        if args.subcommand == "backtest":
            return _backtest(args, parser, now)
        if args.subcommand == "release":
            return _release(args, now, decision_clock=lambda: datetime.now(timezone.utc))
        if args.subcommand == "shadow":
            return _shadow(args, now, decision_clock=lambda: datetime.now(timezone.utc))
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
