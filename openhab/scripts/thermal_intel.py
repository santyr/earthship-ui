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

from zoneinfo import ZoneInfo
from thermal_model.actions import parse_thermal_message
from thermal_model.dataset import latent_mass_from_series
from thermal_model.journal import ActionJournal, audit_schema
from thermal_model.schema import ModeEvent, THERMAL_ITEMS, validate_shadow_output


THERMAL_MODEL_ITEM = "Thermal_Model_JSON"
MAX_SHADOW_BYTES = 16 * 1024
RUNTIME_REVISION_PATHS = (
    "thermal_intel.py",
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
    parser = argparse.ArgumentParser(description="Local thermal journal and schema tooling")
    commands = parser.add_subparsers(dest="subcommand", required=True)
    commands.add_parser("schema-audit", help="read-only exact thermal_intel PostgreSQL schema audit")
    journal = commands.add_parser("journal", help="append one local THERMAL message")
    journal.add_argument("--message-file", required=True, type=Path)
    journal.add_argument("--idempotency-key", required=True)
    journal.add_argument("--received-at", type=_aware_iso)
    return parser


def _jdbc_series(item, start, end, *, reader):
    """Read JDBC history, retaining timestamped invalid states as NaN barriers."""
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    payload = reader(
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


# Operator forecast assumption, effective at local midnight (still MDT).
# Captured rows freeze it; replay never consults a later operator default.
_VENT_CLOSED_FROM = datetime(2026, 11, 1, tzinfo=ZoneInfo("America/Denver"))


def _apply_vent_default(rows):
    if not rows:
        return rows
    def at(row):
        value = row["at"]
        return datetime.fromisoformat(value) if isinstance(value, str) else value
    if max(at(row) for row in rows) < _VENT_CLOSED_FROM:
        return rows
    return [{**row, "_ventClosedFrom": _VENT_CLOSED_FROM.isoformat()} for row in rows]


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


def _current_states(now, series_reader, state_reader, *, origin_observer=None,receipt_version=1):
    from thermal_temperature_runtime import configured_shadow_temperatures,configured_shadow_temperatures_v2
    from thermal_radiation_runtime import configured_shadow_radiation
    if type(receipt_version) is not int or receipt_version not in (1,2):raise ValueError("explicit supported temperature receipt version required")
    select=configured_shadow_temperatures_v2 if receipt_version==2 else configured_shadow_temperatures
    selected = (select(now) if origin_observer is None else select(now,origin_observer=origin_observer))
    qualified = dict(selected or {})
    radiation = configured_shadow_radiation(now)
    if radiation is not None:
        qualified['radiation'] = radiation
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


def publish_shadow_output(payload, put_state):
    """Validate and publish exactly one observational thermal shadow state."""
    validate_shadow_output(payload)
    if payload["confidence"]["grade"] == "unavailable":
        raise ValueError("unavailable thermal shadow output cannot be published")
    encoded = json.dumps(payload, separators=(",", ":"))
    if len(encoded.encode("utf-8")) >= MAX_SHADOW_BYTES:
        raise ValueError("shadow output exceeds the 16 KiB publication bound")
    transport = put_state
    transport(THERMAL_MODEL_ITEM, encoded)
    return encoded


def publish_release_output(*, shadow, qualification_loader, now,
        artifact_sha256, runtime_sha256, sensor_epochs, forecast_rows=None, put_state):
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


def _publish_validated_release(output, put_state):
    from thermal_model.release import validate_release_output,validate_sensor_release_output
    (validate_sensor_release_output if output.get("version")==3 else validate_release_output)(output)
    encoded = json.dumps(output, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) >= MAX_SHADOW_BYTES:
        raise ValueError("thermal release exceeds the 16 KiB publication bound")
    transport = put_state
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
        current, origin_temperatures, runtime, inputs_available_at, published_at, revision_paths=None):
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.origin_capture import build_origin_capture,write_origin_capture,build_sensor_origin_capture,write_sensor_origin_capture
    from thermal_model.runtime_bundle import capture_runtime_bundle
    root = _private_directory(Path(directory))
    bundles = root / "runtime-bundles"
    try:
        bundles.mkdir(mode=0o700)
    except FileExistsError:
        pass
    capture_runtime_bundle(bundles, Path(__file__).resolve().parent,
        _origin_runtime_paths() if revision_paths is None else revision_paths, expected_binding=runtime)
    native=origin_temperatures.get("schema")=="earthship-thermal-origin-temperatures/v2"
    builder=build_sensor_origin_capture if native else build_origin_capture
    writer=write_sensor_origin_capture if native else write_origin_capture
    record = builder(output=output, artifact=artifact, snapshot=snapshot,
        rows=rows, current=current, origin_temperatures=origin_temperatures,
        runtime=runtime, inputs_available_at=inputs_available_at,
        published_at=published_at, known_actions=None)
    return writer(root, record)


def _archive_release_publication(directory, *, output, artifact, snapshot, rows,
        current, origin_temperatures, runtime, inputs_available_at, published_at):
    from thermal_model.forcing_capture import _private_directory
    from thermal_model.origin_capture import build_release_origin_capture,write_release_origin_capture,build_sensor_release_origin_capture,write_sensor_release_origin_capture
    from thermal_model.runtime_bundle import capture_runtime_bundle
    root = _private_directory(Path(directory))
    bundles = root / "runtime-bundles"
    try:
        bundles.mkdir(mode=0o700)
    except FileExistsError:
        pass
    capture_runtime_bundle(bundles, Path(__file__).resolve().parent,
        _release_runtime_paths(), expected_binding=runtime)
    native=output.get("version")==3
    builder=build_sensor_release_origin_capture if native else build_release_origin_capture
    writer=write_sensor_release_origin_capture if native else write_release_origin_capture
    record = builder(output=output, artifact=artifact, snapshot=snapshot,
        rows=rows, current=current, origin_temperatures=origin_temperatures,
        runtime=runtime, inputs_available_at=inputs_available_at,
        published_at=published_at, known_actions=None)
    return writer(root, record)


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
