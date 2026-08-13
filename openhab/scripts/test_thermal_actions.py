from datetime import datetime, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo

import pytest

from thermal_model.actions import parse_thermal_message


DENVER = ZoneInfo("America/Denver")


def _event_id(key, action, state, effective_at):
    material = f"{key}:{action}:{state}:{effective_at.isoformat()}"
    return sha256(material.encode()).hexdigest()[:24]


def test_parse_exact_thermal_template_and_overnight_vent_interval():
    received_at = datetime(2026, 10, 15, 19, 0, tzinfo=DENVER)
    parsed = parse_thermal_message(
        """THERMAL
effective: now
mode: fall-charge
outdoor_shades: removed
indoor_shades: open-day
vent: 20:30-07:00
kiva: off
note: charging mass ahead of winter
""",
        received_at,
        "dm-42",
    )

    assert parsed.idempotency_key == "dm-42"
    assert len(parsed.modes) == 1
    assert parsed.modes[0].mode == "fall_charge"
    assert parsed.modes[0].effective_at == received_at
    assert parsed.modes[0].note == "charging mass ahead of winter"

    vent_events = [event for event in parsed.actions if event.action == "vent"]
    assert [(event.state, event.effective_at) for event in vent_events] == [
        ("open", datetime(2026, 10, 15, 20, 30, tzinfo=DENVER)),
        ("closed", datetime(2026, 10, 16, 7, 0, tzinfo=DENVER)),
    ]
    assert vent_events[0].interval_id == vent_events[1].interval_id
    assert vent_events[0].interval_id is not None

    states = {(event.action, event.state) for event in parsed.actions}
    assert states == {
        ("vent", "open"),
        ("vent", "closed"),
        ("indoor_shade", "open"),
        ("outdoor_shade", "removed"),
        ("kiva", "off"),
    }
    for event in parsed.actions:
        assert event.idempotency_key == "dm-42"
        assert event.received_at == received_at
        assert event.source == "manual_dm"
        assert event.confidence == 1.0
        assert event.note == "charging mass ahead of winter"
        assert event.event_id == _event_id(
            "dm-42", event.action, event.state, event.effective_at
        )


def test_standalone_transition_uses_aware_effective_time_without_interval():
    received_at = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    parsed = parse_thermal_message(
        "THERMAL\neffective: 2026-08-13T06:15:00-06:00\nvent: open\n",
        received_at,
        "dm-standalone",
    )

    assert len(parsed.actions) == 1
    assert parsed.actions[0].state == "open"
    assert parsed.actions[0].interval_id is None
    assert parsed.actions[0].effective_at.isoformat() == "2026-08-13T06:15:00-06:00"


def test_indoor_shade_aliases_normalize_to_open():
    received_at = datetime(2026, 8, 13, tzinfo=timezone.utc)
    parsed = parse_thermal_message(
        "THERMAL\nindoor_shades: open-night\n", received_at, "dm-open-night"
    )
    assert [(event.action, event.state) for event in parsed.actions] == [
        ("indoor_shade", "open"),
    ]


def test_mode_only_message_is_valid():
    received_at = datetime(2026, 8, 13, tzinfo=timezone.utc)
    parsed = parse_thermal_message(
        "THERMAL\nmode: winter\n", received_at, "dm-mode"
    )
    assert parsed.actions == ()
    assert [mode.mode for mode in parsed.modes] == ["winter"]


@pytest.mark.parametrize(
    "text, match",
    [
        ("thermal\nvent: open\n", "header"),
        ("THERMAL\nrelay: x\n", "unknown field"),
        ("THERMAL\nvent: open\nvent: closed\n", "duplicate field"),
        ("THERMAL\nvent: ajar\n", "invalid vent"),
        ("THERMAL\nmode: summer\n", "invalid mode"),
        ("THERMAL\nindoor_shades: half\n", "invalid indoor_shades"),
        ("THERMAL\noutdoor_shades: half\n", "invalid outdoor_shades"),
        ("THERMAL\nkiva: maybe\n", "invalid kiva"),
        ("THERMAL\neffective: 2026-08-13T06:15:00\nvent: open\n", "timezone"),
        ("THERMAL\nnote: no state\n", "action or mode"),
    ],
)
def test_parser_rejects_text_outside_closed_grammar(text, match):
    with pytest.raises(ValueError, match=match):
        parse_thermal_message(
            text,
            datetime(2026, 8, 13, tzinfo=timezone.utc),
            "dm-invalid",
        )


def test_parser_rejects_naive_received_at_and_oversized_utf8_message():
    with pytest.raises(ValueError, match="received_at.*timezone"):
        parse_thermal_message("THERMAL\nmode: warm\n", datetime(2026, 8, 13), "dm")

    text = "THERMAL\nnote: " + ("\N{SNOWMAN}" * 1362) + "\nmode: warm\n"
    assert len(text) < 4096
    assert len(text.encode("utf-8")) > 4096
    with pytest.raises(ValueError, match="4096"):
        parse_thermal_message(
            text, datetime(2026, 8, 13, tzinfo=timezone.utc), "dm-large"
        )


@pytest.mark.parametrize(
    "received_at, interval",
    [
        (datetime(2026, 11, 1, 0, 10, tzinfo=DENVER), "01:30-03:00"),
        (datetime(2026, 10, 31, 0, 10, tzinfo=DENVER), "03:00-01:30"),
    ],
)
def test_parser_rejects_ambiguous_fall_back_local_times(received_at, interval):
    with pytest.raises(ValueError, match="ambiguous"):
        parse_thermal_message(
            f"THERMAL\nvent: {interval}\n", received_at, "dm-dst-fold"
        )


def test_parser_rejects_nonexistent_spring_forward_local_time():
    received_at = datetime(2026, 3, 8, 0, 10, tzinfo=DENVER)
    with pytest.raises(ValueError, match="nonexistent"):
        parse_thermal_message(
            "THERMAL\nvent: 02:30-04:00\n", received_at, "dm-dst-gap"
        )
