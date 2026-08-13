from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import re
from zoneinfo import ZoneInfo

from .schema import ActionEvent, ModeEvent, SOURCE_WEIGHTS


DENVER = ZoneInfo("America/Denver")
MAX_MESSAGE_BYTES = 4096
FIELDS = {
    "effective",
    "mode",
    "vent",
    "indoor_shades",
    "outdoor_shades",
    "kiva",
    "note",
}
MODES = {"spring", "warm", "fall-charge", "winter"}
STATE_MAP = {
    "indoor_shades": {
        "open": "open",
        "open-day": "open",
        "open-night": "open",
        "closed": "closed",
    },
    "outdoor_shades": {"installed": "installed", "removed": "removed"},
    "kiva": {"on": "on", "off": "off"},
}
ACTION_NAMES = {
    "indoor_shades": "indoor_shade",
    "outdoor_shades": "outdoor_shade",
    "kiva": "kiva",
}
VENT_INTERVAL = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")


@dataclass(frozen=True)
class ParsedThermalMessage:
    idempotency_key: str
    actions: tuple[ActionEvent, ...]
    modes: tuple[ModeEvent, ...]


def _require_aware(value, field):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")


def _event_id(idempotency_key, action, state, effective_at):
    material = f"{idempotency_key}:{action}:{state}:{effective_at.isoformat()}"
    return sha256(material.encode("utf-8")).hexdigest()[:24]


def _parse_clock(hour, minute):
    hour_value = int(hour)
    minute_value = int(minute)
    if hour_value > 23 or minute_value > 59:
        raise ValueError("invalid vent interval time")
    return time(hour_value, minute_value)


def _resolve_local(local_date: date, local_time: time):
    naive = datetime.combine(local_date, local_time)
    candidates = {}
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=DENVER, fold=fold)
        round_trip = candidate.astimezone(timezone.utc).astimezone(DENVER)
        if round_trip.replace(tzinfo=None) == naive:
            candidates[candidate.utcoffset()] = candidate
    if not candidates:
        raise ValueError(f"nonexistent America/Denver local time: {naive.isoformat()}")
    if len(candidates) > 1:
        raise ValueError(f"ambiguous America/Denver local time: {naive.isoformat()}")
    return next(iter(candidates.values()))


def _parse_effective(raw, received_at):
    if raw is None or raw == "now":
        return received_at
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("invalid effective timestamp") from exc
    _require_aware(value, "effective")
    return value


def _parse_fields(text):
    if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
        raise ValueError("THERMAL message exceeds 4096 UTF-8 bytes")
    lines = text.splitlines()
    if not lines or lines[0] != "THERMAL":
        raise ValueError("THERMAL header must be exact")
    parsed = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError("THERMAL fields must use 'name: value'")
        name, value = line.split(":", 1)
        name = name.strip()
        value = value.strip()
        if name not in FIELDS:
            raise ValueError(f"unknown field: {name}")
        if name in parsed:
            raise ValueError(f"duplicate field: {name}")
        if not value:
            raise ValueError(f"empty field: {name}")
        parsed[name] = value
    return parsed


def parse_thermal_message(text, received_at, idempotency_key):
    _require_aware(received_at, "received_at")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        raise ValueError("idempotency_key must be non-empty")
    fields = _parse_fields(text)
    effective_at = _parse_effective(fields.get("effective"), received_at)
    note = fields.get("note", "")
    common = {
        "idempotency_key": idempotency_key,
        "received_at": received_at,
        "source": "manual_dm",
        "confidence": SOURCE_WEIGHTS["manual_dm"],
        "note": note,
    }
    actions = []
    modes = []

    if "mode" in fields:
        raw_mode = fields["mode"]
        if raw_mode not in MODES:
            raise ValueError(f"invalid mode: {raw_mode}")
        mode = raw_mode.replace("-", "_")
        modes.append(
            ModeEvent(
                event_id=_event_id(idempotency_key, "mode", mode, effective_at),
                effective_at=effective_at,
                mode=mode,
                **common,
            )
        )

    if "vent" in fields:
        raw_vent = fields["vent"]
        if raw_vent in {"open", "closed"}:
            actions.append(
                ActionEvent(
                    event_id=_event_id(
                        idempotency_key, "vent", raw_vent, effective_at
                    ),
                    effective_at=effective_at,
                    action="vent",
                    state=raw_vent,
                    **common,
                )
            )
        else:
            match = VENT_INTERVAL.fullmatch(raw_vent)
            if not match:
                raise ValueError(f"invalid vent state or interval: {raw_vent}")
            start_clock = _parse_clock(match.group(1), match.group(2))
            stop_clock = _parse_clock(match.group(3), match.group(4))
            local_date = received_at.astimezone(DENVER).date()
            start_at = _resolve_local(local_date, start_clock)
            stop_date = local_date + timedelta(days=stop_clock <= start_clock)
            stop_at = _resolve_local(stop_date, stop_clock)
            interval_material = (
                f"{idempotency_key}:vent:interval:"
                f"{start_at.isoformat()}:{stop_at.isoformat()}"
            )
            interval_id = sha256(interval_material.encode("utf-8")).hexdigest()[:24]
            for state, at in (("open", start_at), ("closed", stop_at)):
                actions.append(
                    ActionEvent(
                        event_id=_event_id(idempotency_key, "vent", state, at),
                        effective_at=at,
                        action="vent",
                        state=state,
                        interval_id=interval_id,
                        **common,
                    )
                )

    for field, state_map in STATE_MAP.items():
        if field not in fields:
            continue
        raw_state = fields[field]
        if raw_state not in state_map:
            raise ValueError(f"invalid {field} state: {raw_state}")
        state = state_map[raw_state]
        action = ACTION_NAMES[field]
        actions.append(
            ActionEvent(
                event_id=_event_id(idempotency_key, action, state, effective_at),
                effective_at=effective_at,
                action=action,
                state=state,
                **common,
            )
        )

    if not actions and not modes:
        raise ValueError("THERMAL message must contain an action or mode")
    return ParsedThermalMessage(idempotency_key, tuple(actions), tuple(modes))
