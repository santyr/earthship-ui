"""Focused guards for forecast SoC inputs; run with Solar_PV analytics on PYTHONPATH."""
import json
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest
import psycopg2

from earthship_energy import advisory_store, materialize, reader
from earthship_energy.materialize import SystemEpoch
from advisory_windows import trough_window

from qualified_soc_forecast import completed_night_troughs, current_valid_soc


BASE = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)


def evidence(at=BASE, *, soc=85, status="valid"):
    stamp = lambda instant: int(instant.timestamp() * 1000)
    return json.dumps({
        "version": 1, "streamEpoch": str(UUID(int=1)), "recordedAt": stamp(at),
        "status": status, "reason": "ok" if status == "valid" else "input_stale",
        "observedAt": stamp(at) if status == "valid" else None,
        "scaleObservedAt": stamp(at) if status == "valid" else None,
        "validUntil": stamp(at + timedelta(seconds=120)) if status == "valid" else None,
        "soc": soc if status == "valid" else None,
    })


def test_current_atomic_soc_accepts_unchanged_but_fresh_value():
    assert current_valid_soc(evidence(soc=85), BASE + timedelta(seconds=60)) == 85
    assert current_valid_soc(evidence(soc=0), BASE + timedelta(seconds=60)) == 0


def test_current_atomic_soc_rejects_expiry_fault_and_bad_clock():
    assert current_valid_soc(evidence(), BASE + timedelta(seconds=120)) is None
    assert current_valid_soc(evidence(status="unavailable"), BASE) is None
    assert current_valid_soc("{}", BASE) is None
    with pytest.raises(ValueError):
        current_valid_soc(evidence(), BASE.replace(tzinfo=None))


def test_completed_nights_require_explicit_assessor_configuration():
    assert completed_night_troughs(
        [date(2026, 9, 21)], now=BASE, site_timezone="America/Denver",
        environ={},
    ) == {}
    with pytest.raises(ValueError):
        completed_night_troughs(
            [date(2026, 9, 21)] * 2, now=BASE,
            site_timezone="America/Denver", environ={},
        )


def test_completed_night_uses_full_atomic_coverage_and_skips_incomplete(monkeypatch):
    prediction_day = date(2026, 9, 20)
    window = trough_window(prediction_day, "America/Denver")
    rows = [(window.start + timedelta(minutes=minute),
             evidence(window.start + timedelta(minutes=minute), soc=80 if minute == 300 else 85))
            for minute in range(15 * 60)]
    queries = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, sql, params):
            queries.append((sql, params))

        def fetchall(self):
            return [(605,)]

    class Connection:
        closed = False

        def cursor(self):
            return Cursor()

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(psycopg2, "connect", lambda *args, **kwargs: connection)
    monkeypatch.setattr(advisory_store, "AdvisoryStore", lambda dsn: type(
        "Store", (), {"_dsn": dsn, "_hostaddr": "127.0.0.1"})())
    monkeypatch.setattr(materialize, "load_epoch_config", lambda: (SystemEpoch(
        "bank", date(2026, 7, 19), None, True, 400, 20.48, {}),))
    monkeypatch.setattr(reader, "fetch_freshness_observations",
                        lambda *_args, **_kwargs: rows)
    env = {
        "ADVISORY_ASSESS_ENABLED": "1", "ADVISORY_ASSESS_TIMEZONE": "America/Denver",
        "ADVISORY_ASSESS_DSN": "synthetic", "ADVISORY_ASSESS_BANK_EPOCH": "bank",
    }
    result = completed_night_troughs(
        [date(2026, 9, 21), date(2026, 9, 22)], now=BASE,
        site_timezone="America/Denver", environ=env,
    )
    assert result == {date(2026, 9, 21): 80}
    assert len(queries) == 1
    assert connection.closed

    # A change-only minimum at minute 300 cannot qualify the entire night
    # when three hours of acquisition evidence are absent.
    rows = [row for row in rows
            if not window.start + timedelta(minutes=300) <= row[0]
            < window.start + timedelta(minutes=480)]
    assert completed_night_troughs(
        [date(2026, 9, 21)], now=BASE,
        site_timezone="America/Denver", environ=env,
    ) == {}
