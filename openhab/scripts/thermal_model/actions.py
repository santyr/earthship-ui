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


@dataclass(frozen=True)
class RegimeInterval:
    """One evidence-backed seasonal regime interval, normalized to UTC."""

    start: datetime
    end: datetime
    regime: str
    source: str
    confidence: float
    mode_source: str
    mode_confidence: float
    mode_event_id: str


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


def reconstruct_state(regime, *, is_daylight, sunny, cold_cloudy):
    """Return the approved low-confidence seasonal action baseline.

    These labels describe historical household behavior.  They are not control
    rules and never create an action outside an evidence-backed mode interval.
    """
    if regime == "winter":
        return {
            "vent_open": 0.0,
            "indoor_shade_closed": float((not is_daylight) or cold_cloudy),
        }
    if regime == "fall_charge":
        return {
            "vent_open": float(not is_daylight),
            "indoor_shade_closed": None,
        }
    if regime in {"spring", "warm"}:
        return {
            "vent_open": float(not is_daylight),
            "indoor_shade_closed": float(is_daylight and sunny),
        }
    raise ValueError(f"unknown thermal regime: {regime}")


def reconstruct_events(start, end, modes):
    """Convert effective mode records into clipped, evidence-backed intervals.

    No interval is emitted before the first supplied effective mode.  Callers
    should pass ``ActionJournal.effective_modes`` output, which includes the
    last effective mode before ``start`` when one exists.  If raw correction
    records are supplied defensively, the superseded mode is removed and any
    period between its old effective time and the correction is left unknown.
    """
    _require_aware(start, "start")
    _require_aware(end, "end")
    if end <= start:
        raise ValueError("end must be after start")
    start_utc = start.astimezone(timezone.utc)
    end_utc = end.astimezone(timezone.utc)
    records = tuple(modes)
    if not all(isinstance(mode, ModeEvent) for mode in records):
        raise TypeError("modes must contain only ModeEvent records")
    for mode in records:
        _require_aware(mode.received_at, "mode received_at")
        _require_aware(mode.effective_at, "mode effective_at")

    by_id = {mode.event_id: mode for mode in records}
    superseded = {mode.supersedes for mode in records if mode.supersedes}
    effective = [mode for mode in records if mode.event_id not in superseded]
    effective.sort(
        key=lambda mode: (
            mode.effective_at.astimezone(timezone.utc),
            mode.received_at.astimezone(timezone.utc),
            mode.event_id,
        )
    )

    correction_gaps = []
    for correction in effective:
        original = by_id.get(correction.supersedes)
        if original is None:
            continue
        old_at = original.effective_at.astimezone(timezone.utc)
        new_at = correction.effective_at.astimezone(timezone.utc)
        if old_at < new_at:
            correction_gaps.append((old_at, new_at))

    intervals = []
    for index, mode in enumerate(effective):
        mode_start = max(start_utc, mode.effective_at.astimezone(timezone.utc))
        next_start = (
            effective[index + 1].effective_at.astimezone(timezone.utc)
            if index + 1 < len(effective)
            else end_utc
        )
        mode_end = min(end_utc, next_start)
        pieces = [(mode_start, mode_end)] if mode_start < mode_end else []
        for gap_start, gap_end in correction_gaps:
            remaining = []
            for piece_start, piece_end in pieces:
                if gap_end <= piece_start or gap_start >= piece_end:
                    remaining.append((piece_start, piece_end))
                    continue
                if piece_start < gap_start:
                    remaining.append((piece_start, gap_start))
                if gap_end < piece_end:
                    remaining.append((gap_end, piece_end))
            pieces = remaining
        for piece_start, piece_end in pieces:
            intervals.append(
                RegimeInterval(
                    start=piece_start,
                    end=piece_end,
                    regime=mode.mode,
                    source="historical_reconstruction",
                    confidence=SOURCE_WEIGHTS["historical_reconstruction"],
                    mode_source=mode.source,
                    mode_confidence=mode.confidence,
                    mode_event_id=mode.event_id,
                )
            )
    return intervals
