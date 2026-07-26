"""Focused tests for forecast_intel data-quality hardening.

Covers (2026-07-22 audit fixes):
- scoring idempotency, now PER QUANTITY (regression guard for the 2026-07-19
  bug where N same-day runs appended N duplicate errors, and for the whole-day
  marker bug where an empty rain series left precip permanently unscored)
- timezone-exact local-day windows in MST and MDT (regression guard for the
  fixed utc_off=6h shift that leaked midnight-reset accumulators across days
  in winter)
- atomic state save + corrupt-state quarantine + schema-tolerant load
- Open-Meteo fetch retry, PUT failure collection, pv_days realignment
"""
import contextlib
import importlib.util
import io
import json
import os
from datetime import date, datetime, timedelta, timezone

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "forecast_intel", os.path.join(os.path.dirname(__file__), "forecast_intel.py"))
fi = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fi)

UTC = timezone.utc


# ---------------------------------------------------------------- scoring markers

def test_should_score_fresh_state():
    # A day never scored before must be scored, for every quantity.
    for q in fi.SCORE_QUANTITIES:
        assert fi.should_score({}, "2026-07-20", q) is True


def test_legacy_last_scored_day_honored():
    # Live state written before the upgrade has last_scored_day only: that day
    # must count as fully scored (no double-append on first run after upgrade).
    st = {"last_scored_day": "2026-07-20"}
    for q in fi.SCORE_QUANTITIES:
        assert fi.should_score(st, "2026-07-20", q) is False
    assert "last_scored_day" not in st          # migrated
    assert set(st["scored"]["2026-07-20"]) == set(fi.SCORE_QUANTITIES)


def test_new_day_after_prior_scores():
    st = {"last_scored_day": "2026-07-19"}
    for q in fi.SCORE_QUANTITIES:
        assert fi.should_score(st, "2026-07-20", q) is True


def test_partial_day_requantifies_only_missing():
    st = {}
    fi.mark_scored(st, "2026-07-20", "hi")
    fi.mark_scored(st, "2026-07-20", "lo")
    assert fi.should_score(st, "2026-07-20", "hi") is False
    assert fi.should_score(st, "2026-07-20", "precip") is True


def test_five_reruns_append_exactly_one_error():
    # Simulate the exact 2026-07-19 failure: five runs scoring the same day.
    st = {"pv_errors": []}
    ykey = "2026-07-18"
    for _ in range(5):
        if fi.should_score(st, ykey, "pv"):
            st["pv_errors"] = (st["pv_errors"] + [61.25])[-7:]
            fi.mark_scored(st, ykey, "pv")
    assert st["pv_errors"] == [61.25], "re-runs must not duplicate the day's error"


def test_mark_scored_prunes_to_three_days():
    st = {}
    for d in range(1, 6):
        fi.mark_scored(st, f"2026-07-{d:02d}", "pv")
    assert sorted(st["scored"]) == ["2026-07-03", "2026-07-04", "2026-07-05"]


# ---------------------------------------------------------------- timezone windows

def _capture_series(monkeypatch):
    calls = []
    monkeypatch.setattr(fi, "series", lambda item, s, e: calls.append((item, s, e)) or [])
    return calls


def test_day_window_mst_january(monkeypatch):
    # MST = UTC-7: local midnight boundaries are 07:00Z, NOT the old fixed 06:00Z
    # (which pulled the previous local day's 23:00 accumulator point into max()).
    calls = _capture_series(monkeypatch)
    fi.measured_day_weather(date(2026, 1, 15))
    assert len(calls) == 2   # rain + temp share the window
    for _, s, e in calls:
        assert s == datetime(2026, 1, 15, 7, 0, tzinfo=UTC)
        assert e == datetime(2026, 1, 16, 7, 0, tzinfo=UTC)


def test_day_window_mdt_july(monkeypatch):
    # MDT = UTC-6.
    calls = _capture_series(monkeypatch)
    fi.measured_day_weather(date(2026, 7, 15))
    for _, s, e in calls:
        assert s == datetime(2026, 7, 15, 6, 0, tzinfo=UTC)
        assert e == datetime(2026, 7, 16, 6, 0, tzinfo=UTC)


def test_day_window_dst_transition_days():
    # Spring forward 2026-03-08: 23 h local day. Fall back 2026-11-01: 25 h.
    s, e = fi.local_day_window_utc(date(2026, 3, 8))
    assert s == datetime(2026, 3, 8, 7, 0, tzinfo=UTC)
    assert e == datetime(2026, 3, 9, 6, 0, tzinfo=UTC)
    s, e = fi.local_day_window_utc(date(2026, 11, 1))
    assert s == datetime(2026, 11, 1, 6, 0, tzinfo=UTC)
    assert e == datetime(2026, 11, 2, 7, 0, tzinfo=UTC)


def test_measured_trough_window_mst(monkeypatch):
    # 20:00 Jan 14 MST -> 03:00Z Jan 15; 11:00 Jan 15 MST -> 18:00Z.
    calls = _capture_series(monkeypatch)
    fi.measured_trough(date(2026, 1, 15))
    (_, s, e), = calls
    assert s == datetime(2026, 1, 15, 3, 0, tzinfo=UTC)
    assert e == datetime(2026, 1, 15, 18, 0, tzinfo=UTC)


def test_series_formats_true_utc_and_skips_unparseable(monkeypatch):
    captured = {}

    def fake_oh_get(path):
        captured["path"] = path
        return {"data": [
            {"time": 1768464000000, "state": "42.5 %"},
            {"time": 1768464060000, "state": "UNDEF"},
            {"time": 1768464120000, "state": "NULL"},
            {"time": 1768464180000, "state": "43.0"},
        ]}

    monkeypatch.setattr(fi, "oh_get", fake_oh_get)
    start = datetime(2026, 1, 15, 0, 0, tzinfo=fi.MOUNTAIN)
    end = datetime(2026, 1, 16, 0, 0, tzinfo=fi.MOUNTAIN)
    pts = fi.series("X", start, end)
    assert "starttime=2026-01-15T07:00:00Z" in captured["path"]
    assert "endtime=2026-01-16T07:00:00Z" in captured["path"]
    assert [v for _, v in pts] == [42.5, 43.0]
    assert all(ts.tzinfo == UTC for ts, _ in pts)


# ---------------------------------------------------------------- state file safety

def _state_paths(tmp_path, monkeypatch):
    sf = tmp_path / "state.json"
    monkeypatch.setattr(fi, "STATE_FILE", str(sf))
    monkeypatch.setattr(fi, "STATE_DIR", str(tmp_path))
    return sf


def test_load_state_missing_file_returns_defaults(tmp_path, monkeypatch):
    _state_paths(tmp_path, monkeypatch)
    st = fi.load_state()
    assert st["k_res"] == 1.0 and st["predictions"] == {} and st["dm_sent"] == {}


def test_load_state_corrupt_quarantines_and_logs(tmp_path, monkeypatch, capsys):
    sf = _state_paths(tmp_path, monkeypatch)
    sf.write_text("{not json!!")
    st = fi.load_state()
    assert st["k_res"] == 1.0                       # defaults returned
    assert not sf.exists()                          # corrupt file moved aside...
    corrupt = list(tmp_path.glob("state.json.corrupt-*"))
    assert len(corrupt) == 1
    assert corrupt[0].read_text() == "{not json!!"  # ...and preserved as evidence
    assert "CORRUPT STATE" in capsys.readouterr().err


def test_load_state_merges_over_defaults(tmp_path, monkeypatch):
    # Old schema files (missing new keys) must never KeyError in main().
    sf = _state_paths(tmp_path, monkeypatch)
    sf.write_text('{"k_res": 0.88}')
    st = fi.load_state()
    assert st["k_res"] == 0.88
    for key in ("predictions", "pv_errors", "trough_errors", "dm_sent", "d_direct"):
        assert key in st


def test_save_state_atomic_temp_plus_replace(tmp_path, monkeypatch):
    sf = _state_paths(tmp_path, monkeypatch)
    replaced = []
    real_replace = os.replace

    def spy(src, dst):
        replaced.append((src, dst))
        return real_replace(src, dst)

    monkeypatch.setattr(fi.os, "replace", spy)
    fi.save_state({"k_res": 0.9})
    assert replaced == [(str(sf) + ".tmp", str(sf))]
    assert json.loads(sf.read_text())["k_res"] == 0.9
    assert not (tmp_path / "state.json.tmp").exists()


def test_save_state_failure_leaves_original_intact(tmp_path, monkeypatch):
    sf = _state_paths(tmp_path, monkeypatch)
    sf.write_text('{"k_res": 0.7}')
    with pytest.raises(TypeError):
        fi.save_state({"bad": object()})   # unserializable -> mid-write failure
    assert json.loads(sf.read_text()) == {"k_res": 0.7}, "partial write must not clobber state.json"


# ---------------------------------------------------------------- network resilience

def test_fetch_forecast_retries_then_succeeds():
    calls, sleeps = [], []

    def opener(url):
        calls.append(url)
        if len(calls) < 3:
            raise OSError("connection reset")
        return contextlib.closing(io.StringIO('{"ok": 1}'))

    out = fi.fetch_forecast(url="u", opener=opener, sleep=sleeps.append)
    assert out == {"ok": 1}
    assert len(calls) == 3
    assert sleeps == [10, 30]


def test_fetch_forecast_exhausts_and_raises():
    sleeps = []

    def opener(url):
        raise OSError("down")

    with pytest.raises(OSError):
        fi.fetch_forecast(url="u", opener=opener, sleep=sleeps.append)
    assert sleeps == [10, 30]   # no sleep after the final attempt


def test_safe_put_collects_failures_and_never_raises(monkeypatch, capsys):
    def flaky(item, value):
        if item == "Bad":
            raise OSError("openhab flapped")

    monkeypatch.setattr(fi, "oh_put_state", flaky)
    fails = []
    assert fi.safe_put("Good", 1, fails) is True
    assert fi.safe_put("Bad", 2, fails) is False
    assert fails == ["Bad"]
    assert "PUT failed for Bad" in capsys.readouterr().err


# ---------------------------------------------------------------- pv_days alignment

def test_align_pv_days():
    days = [6.1, 6.2, 6.3, 6.4]
    today = date(2026, 7, 22)
    assert fi.align_pv_days(days, "2026-07-22", today) == days           # same day
    assert fi.align_pv_days(days, "2026-07-21", today) == [6.2, 6.3, 6.4]  # post-midnight shift
    assert fi.align_pv_days(days, "2026-07-01", today) is None           # fully stale
    assert fi.align_pv_days(days, "2026-07-23", today) is None           # future-dated: unusable
    assert fi.align_pv_days(days, None, today) == days                   # legacy state passthrough
    assert fi.align_pv_days([], "2026-07-22", today) is None


# ---------------------------------------------------------------- main() end-to-end

def _snapshot():
    days = [(date.today() + timedelta(days=i)).isoformat() for i in range(10)]
    return {
        "daily": {
            "time": days,
            "temperature_2m_max": [90.0] * 10,
            "temperature_2m_min": [60.0] * 10,
            "shortwave_radiation_sum": [25.0] * 10,
            "precipitation_probability_max": [10] * 10,
            "precipitation_sum": [0.0] * 10,
            "cloud_cover_mean": [20] * 10,
            "weather_code": [1] * 10,
        },
        "hourly": {
            "time": [], "temperature_2m": [], "precipitation_probability": [],
            "precipitation": [], "shortwave_radiation": [], "wind_speed_10m": [],
            "weather_code": [],
        },
    }


def _run_main(monkeypatch, tmp_path, st, series_data):
    """Run main() fully stubbed; returns (state, puts) as saved/put."""
    t = datetime.now(UTC)
    saved = {}
    puts = []
    monkeypatch.setattr(fi, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fi, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(fi, "load_state", lambda: st)
    monkeypatch.setattr(fi, "save_state", lambda s: saved.update(s))
    monkeypatch.setattr(fi, "series",
                        lambda item, s, e: [(t, v) for v in series_data.get(item, [])])
    monkeypatch.setattr(fi, "oh_get", lambda path: {"state": "82"})
    monkeypatch.setattr(fi, "oh_put_state", lambda item, value: puts.append(item))
    monkeypatch.setattr(fi, "fetch_forecast", lambda *a, **k: _snapshot())
    fi.main()
    return saved, puts


def _scoring_state(ykey):
    return {
        "k_res": 1.0, "d_direct": 4.0,
        "predictions": {ykey: {"pv": 7.5, "trough": 80, "radsum": 7.0, "demand": 8.0,
                               "deficit_kwh": 2.0, "hi": 90.0, "lo": 62.0, "precip_in": 0.1}},
        "pv_errors": [], "trough_errors": [], "dm_sent": {},
        "kalman": {"hi": {"b": 0.0, "P": 1.0}, "lo": {"b": 0.0, "P": 1.0}},
        "horizon": {ykey: {"hi": 91.0, "precip_in": 0.2}},
    }


def test_rain_scores_once_on_rerun_temps_never_double(monkeypatch, tmp_path):
    # Live failure mode: 06:40 run finds temps but the rain series is empty ->
    # the old whole-day marker locked precip out forever. Now a same-day re-run
    # scores rain exactly once while temps/pv/trough do NOT double-append.
    ykey = (date.today() - timedelta(days=1)).isoformat()
    st = _scoring_state(ykey)
    data = {
        fi.RAIN_DAY_ITEM: [],                       # rain missing at 06:40
        fi.OUTDOOR_TEMP_ITEM: [60.0, 88.0],
        "MPPT60_EnergyFromPV_Today": [7.0],
        "BMS_SOC": [85.0],
    }
    st1, _ = _run_main(monkeypatch, tmp_path, st, data)
    assert len(st1["pv_errors"]) == 1
    assert len(st1["trough_errors"]) == 1
    assert len(st1["temp_hi_errors"]) == 1
    assert len(st1["temp_lo_errors"]) == 1
    assert st1.get("precip_errors", []) == []            # nothing to score yet
    assert set(st1["scored"][ykey]) == {"pv", "trough", "hi", "lo"}
    # day-3 horizon: hi consumed, precip preserved for the re-run (not destroyed)
    assert st1["day3_hi_errors"] == [pytest.approx(3.0)]
    assert st1["horizon"][ykey] == {"precip_in": 0.2}

    # same-day re-run: rain has appeared
    data[fi.RAIN_DAY_ITEM] = [0.05]
    st2, _ = _run_main(monkeypatch, tmp_path, dict(st1), data)
    assert st2["precip_errors"] == [pytest.approx(0.05)]   # scored exactly once
    assert len(st2["pv_errors"]) == 1, "pv must not double-append"
    assert len(st2["temp_hi_errors"]) == 1, "temps must not double-append"
    assert len(st2["temp_lo_errors"]) == 1
    assert len(st2["trough_errors"]) == 1
    assert set(st2["scored"][ykey]) == set(fi.SCORE_QUANTITIES)
    assert st2["day3_precip_errors"] == [pytest.approx(0.15)]
    assert len(st2["day3_hi_errors"]) == 1, "day-3 hi must not double-append"
    assert ykey not in st2["horizon"]                      # fully consumed now

    # third run: everything marked, nothing appends
    st3, _ = _run_main(monkeypatch, tmp_path, dict(st2), data)
    assert len(st3["precip_errors"]) == 1
    assert len(st3["pv_errors"]) == 1


def test_zero_pv_day_skipped_with_log_not_division_error(monkeypatch, tmp_path, capsys):
    ykey = (date.today() - timedelta(days=1)).isoformat()
    st = _scoring_state(ykey)
    data = {
        fi.RAIN_DAY_ITEM: [0.0],
        fi.OUTDOOR_TEMP_ITEM: [60.0, 88.0],
        "MPPT60_EnergyFromPV_Today": [0.0],   # genuine zero-production day
        "BMS_SOC": [85.0],
    }
    st1, _ = _run_main(monkeypatch, tmp_path, st, data)
    assert st1["pv_errors"] == []                       # no divide-by-zero append
    assert "pv" in st1["scored"][ykey]                  # but marked: data existed
    log_text = (tmp_path / "log").read_text()
    assert "PV scoring skipped" in log_text


def test_put_failures_collected_not_fatal(monkeypatch, tmp_path):
    # openHAB flapping mid-run must not abort scoring or the state save.
    ykey = (date.today() - timedelta(days=1)).isoformat()
    st = _scoring_state(ykey)
    data = {
        fi.RAIN_DAY_ITEM: [0.05],
        fi.OUTDOOR_TEMP_ITEM: [60.0, 88.0],
        "MPPT60_EnergyFromPV_Today": [7.0],
        "BMS_SOC": [85.0],
    }
    t = datetime.now(UTC)
    saved = {}
    monkeypatch.setattr(fi, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(fi, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(fi, "load_state", lambda: st)
    monkeypatch.setattr(fi, "save_state", lambda s: saved.update(s))
    monkeypatch.setattr(fi, "series",
                        lambda item, s, e: [(t, v) for v in data.get(item, [])])
    monkeypatch.setattr(fi, "oh_get", lambda path: {"state": "82"})

    def flaky_put(item, value):
        raise OSError("openhab down")

    monkeypatch.setattr(fi, "oh_put_state", flaky_put)
    monkeypatch.setattr(fi, "fetch_forecast", lambda *a, **k: _snapshot())
    fi.main()   # must not raise
    assert len(saved["pv_errors"]) == 1, "scoring must complete despite PUT failures"
    assert set(saved["scored"][ykey]) == set(fi.SCORE_QUANTITIES)
    log_text = (tmp_path / "log").read_text()
    assert "PUT FAILED:" in log_text
    assert "Forecast_PV_Error_7d" in log_text


# ---------------------------------------------- openHAB-fed site settings

I18N_PATH = "/services/org.openhab.i18n/config"


@pytest.fixture
def site_globals(monkeypatch):
    """Restore the module-level site globals load_site_settings rebinds."""
    saved = (fi.LAT, fi.LON, fi.MOUNTAIN, fi.OM_URL, fi.SITE_TZ_NAME)
    yield
    (fi.LAT, fi.LON, fi.MOUNTAIN, fi.OM_URL, fi.SITE_TZ_NAME) = saved


def _i18n(monkeypatch, payload):
    def fake_oh_get(path):
        assert path == I18N_PATH, f"unexpected path {path}"
        return payload
    monkeypatch.setattr(fi, "oh_get", fake_oh_get)


def test_site_settings_adopt_openhab_location(site_globals, monkeypatch):
    # openHAB is authoritative for site location; its value must win over the
    # hardcoded fallback (which had drifted 2.8 m in longitude).
    _i18n(monkeypatch, {"location": "38.3739919,-105.7744609",
                        "timezone": "America/Denver"})
    fi.load_site_settings()
    assert (fi.LAT, fi.LON) == (38.3739919, -105.7744609)
    assert "latitude=38.3739919&longitude=-105.7744609" in fi.OM_URL


def test_site_settings_adopt_openhab_timezone(site_globals, monkeypatch):
    # A non-Denver zone proves the value is really read, not coincidence.
    _i18n(monkeypatch, {"location": "33.4,-112.0", "timezone": "America/Phoenix"})
    fi.load_site_settings()
    assert fi.SITE_TZ_NAME == "America/Phoenix"
    assert datetime(2026, 7, 1, tzinfo=fi.MOUNTAIN).utcoffset() == timedelta(hours=-7)
    assert "timezone=America%2FPhoenix" in fi.OM_URL


def test_site_settings_fall_back_when_openhab_unreachable(site_globals, monkeypatch):
    # The daily pipeline must never die because the config read failed.
    def boom(path):
        raise OSError("openhab down")
    monkeypatch.setattr(fi, "oh_get", boom)
    fi.load_site_settings()   # must not raise
    assert (fi.LAT, fi.LON) == (fi.FALLBACK_LAT, fi.FALLBACK_LON)
    assert fi.SITE_TZ_NAME == fi.FALLBACK_TZ_NAME


@pytest.mark.parametrize("payload", [
    {"location": "not-a-location", "timezone": "America/Denver"},
    {"location": "38.4", "timezone": "America/Denver"},
    {"location": "91.0,-105.0", "timezone": "America/Denver"},
    {"location": "38.4,-181.0", "timezone": "America/Denver"},
    {"location": "38.4,-105.0", "timezone": "Not/AZone"},
    {},
])
def test_site_settings_reject_malformed_config(site_globals, monkeypatch, payload):
    # Garbage from openHAB must not poison the Open-Meteo query.
    _i18n(monkeypatch, payload)
    fi.load_site_settings()
    assert (fi.LAT, fi.LON) == (fi.FALLBACK_LAT, fi.FALLBACK_LON)
    assert fi.SITE_TZ_NAME == fi.FALLBACK_TZ_NAME


def test_fetch_forecast_uses_current_om_url(site_globals, monkeypatch):
    # Regression guard: url=OM_URL as a default arg would bind at import time,
    # silently ignoring whatever load_site_settings resolved.
    _i18n(monkeypatch, {"location": "33.4,-112.0", "timezone": "America/Phoenix"})
    fi.load_site_settings()
    seen = []

    def opener(url):
        seen.append(url)
        return contextlib.closing(io.StringIO("{}"))

    fi.fetch_forecast(opener=opener, sleep=lambda _s: None)
    assert seen == [fi.OM_URL]
    assert "latitude=33.4" in seen[0]


def test_detail_payload_stamps_resolved_timezone(site_globals, monkeypatch):
    # The UI validates forecast.json's timezone, so it must be the zone the
    # pipeline actually computed in, not a second hardcoded literal.
    _i18n(monkeypatch, {"location": "33.4,-112.0", "timezone": "America/Phoenix"})
    fi.load_site_settings()
    _, _, detail = fi.build_forecast_payloads(_snapshot(), [], datetime(2026, 7, 20, 6, 40))
    assert detail["timezone"] == "America/Phoenix"


# ---------------------------------------------- backfill shares site settings

def _backfill_module(monkeypatch):
    """Import forecast_backfill against THIS forecast_intel instance."""
    import sys
    monkeypatch.setitem(sys.modules, "forecast_intel", fi)
    monkeypatch.syspath_prepend(os.path.dirname(os.path.abspath(fi.__file__)))
    sys.modules.pop("forecast_backfill", None)
    import forecast_backfill
    monkeypatch.setitem(sys.modules, "forecast_backfill", forecast_backfill)
    return forecast_backfill


def test_backfill_urls_follow_resolved_site_settings(site_globals, monkeypatch):
    # A `from forecast_intel import LAT, LON, MOUNTAIN` snapshots the values at
    # import, so the backfill would keep querying the fallback site forever.
    bf = _backfill_module(monkeypatch)
    _i18n(monkeypatch, {"location": "33.4,-112.0", "timezone": "America/Phoenix"})
    fi.load_site_settings()

    hist = bf.hist_url("2026-01-01", "2026-01-02")
    prev = bf.prev_url("2026-01-01", "2026-01-02")
    for url in (hist, prev):
        assert "latitude=33.4&longitude=-112.0" in url
        assert "timezone=America%2FPhoenix" in url
    assert "start_date=2026-01-01&end_date=2026-01-02" in hist
    assert bf.site_zone() is fi.MOUNTAIN
