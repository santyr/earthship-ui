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


def _daily_adjustment(high=2.5, low=-9.0):
    return {
        "highCorrectionF": high,
        "lowCorrectionF": low,
        "hourlyMethod": "daily-fallback",
        "hourBuckets": [
            {"hour": hour, "count": 0, "weight": 0.0}
            for hour in range(24)
        ],
    }


def test_forecast_payload_v2_applies_only_daily_temperature_corrections():
    snapshot = _snapshot()
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    snapshot["hourly"] = {
        "time": [now.strftime("%Y-%m-%dT%H:00")],
        "temperature_2m": [71.25],
        "precipitation_probability": [35],
        "precipitation": [0.12],
        "shortwave_radiation": [410.0],
        "wind_speed_10m": [13.5],
        "weather_code": [2],
    }
    original_bytes = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    raw_hi = snapshot["daily"]["temperature_2m_max"][0]
    raw_lo = snapshot["daily"]["temperature_2m_min"][0]
    adjustment = _daily_adjustment()

    legacy_hourly, legacy_daily, detail = fi.build_forecast_payloads(
        snapshot, [6.4], now, temperature_adjustment=adjustment
    )

    assert detail["version"] == 2
    assert detail["temperatureAdjustment"] == adjustment
    assert legacy_daily[0]["hi"] == round(raw_hi + 2.5)
    assert legacy_daily[0]["lo"] == round(raw_lo - 9.0)
    assert detail["days"][0]["summary"]["highF"] == raw_hi + 2.5
    assert detail["days"][0]["summary"]["lowF"] == raw_lo - 9.0
    assert legacy_hourly[0] == {
        "h": fi._hour_label(snapshot["hourly"]["time"][0]),
        "t": round(71.25),
        "p": 35,
        "a": 0.12,
        "r": 410,
        "w": 2,
    }
    assert detail["days"][0]["summary"]["precipPct"] == 10
    assert detail["days"][0]["summary"]["precipSumIn"] == 0.0
    assert detail["days"][0]["summary"]["weatherCode"] == 1
    detail_hour = detail["days"][0]["hours"][0]
    assert detail_hour["tempF"] == 71.25
    assert detail_hour["precipPct"] == 35
    assert detail_hour["precipIn"] == 0.12
    assert detail_hour["radiationWm2"] == 410.0
    assert detail_hour["windMph"] == 13.5
    assert detail_hour["weatherCode"] == 2
    assert json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8") == original_bytes


@pytest.mark.parametrize("temperature_adjustment", [
    None,
    {"highCorrectionF": float("nan"), "lowCorrectionF": "not-a-number"},
])
def test_forecast_payload_normalizes_missing_or_nonfinite_daily_corrections(
        temperature_adjustment):
    _, legacy_daily, detail = fi.build_forecast_payloads(
        _snapshot(), [], datetime.now(),
        temperature_adjustment=temperature_adjustment,
    )

    assert detail["temperatureAdjustment"] == _daily_adjustment(high=0.0, low=0.0)
    assert legacy_daily[0]["hi"] == 90
    assert legacy_daily[0]["lo"] == 60


def test_standalone_json_refresh_reads_daily_kalman_without_mutating_state(monkeypatch):
    state = {
        "pv_days": [6.4],
        "pv_days_date": date.today().isoformat(),
        "kalman": {
            "hi": {"b": -2.5, "P": 1.25},
            "lo": {"b": 9.0, "P": 2.5},
        },
    }
    original = json.loads(json.dumps(state))
    published = {}
    loads = []

    def load():
        loads.append(True)
        return state

    monkeypatch.setattr(fi, "load_state", load)

    _, legacy_daily, detail = fi.build_json_items(
        snapshot=_snapshot(),
        now=datetime.now(),
        put_state=lambda item, value: published.setdefault(item, value),
    )

    assert detail["temperatureAdjustment"] == _daily_adjustment()
    assert legacy_daily[0]["hi"] == 92
    assert legacy_daily[0]["lo"] == 51
    assert json.loads(published["Forecast_10Day_JSON"])["version"] == 2
    assert loads == [True]
    assert state == original


def test_main_passes_post_scoring_daily_kalman_to_json_builder(monkeypatch, tmp_path):
    ykey = (date.today() - timedelta(days=1)).isoformat()
    state = _scoring_state(ykey)
    captured = []
    monkeypatch.setattr(fi, "build_json_items", lambda **kwargs: captured.append(kwargs))
    data = {
        fi.RAIN_DAY_ITEM: [0.05],
        fi.OUTDOOR_TEMP_ITEM: [60.0, 88.0],
        "MPPT60_EnergyFromPV_Today": [7.0],
        "BMS_SOC": [85.0],
    }

    saved, _ = _run_main(monkeypatch, tmp_path, state, data)

    adjustment = captured[0]["temperature_adjustment"]
    assert adjustment["highCorrectionF"] == pytest.approx(-saved["kalman"]["hi"]["b"])
    assert adjustment["lowCorrectionF"] == pytest.approx(-saved["kalman"]["lo"]["b"])
    assert saved["predictions"][date.today().isoformat()]["hi"] == 90.0
    assert saved["predictions"][date.today().isoformat()]["lo"] == 60.0


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

# ---------------------------------------------------------------- hourly temperature learning

def test_load_state_migrates_hourly_defaults_without_overwriting_prior_bucket(
        tmp_path, monkeypatch):
    sf = _state_paths(tmp_path, monkeypatch)
    prior = {"b": 3.25, "P": 2.5, "count": 9}
    sf.write_text(json.dumps({
        "hourly_temp_model": {"7": prior},
        "hourly_temp_targets": {"2026-08-28T07:00:00-06:00": {
            "raw": 48.0, "captured_at": "2026-08-27T06:40:00-06:00",
        }},
    }))

    st = fi.load_state()

    assert len(st["hourly_temp_model"]) == 24
    assert st["hourly_temp_model"]["7"] == prior
    assert st["hourly_temp_model"]["8"] == {"b": 0.0, "P": 10.0, "count": 0}
    assert list(st["hourly_temp_targets"]) == ["2026-08-28T07:00:00-06:00"]


def test_hourly_model_seed_has_24_independent_local_hour_buckets():
    model = fi.hourly_model_seed()

    assert list(model) == [str(hour) for hour in range(24)]
    assert all(bucket == {"b": 0.0, "P": 10.0, "count": 0}
               for bucket in model.values())
    model["0"]["count"] = 1
    assert model["1"]["count"] == 0


def test_capture_next_day_hourly_keeps_only_raw_next_local_day_values():
    now = datetime(2026, 8, 27, 6, 40, tzinfo=fi.MOUNTAIN)
    snapshot = {"hourly": {
        "time": [
            "2026-08-27T23:00", "2026-08-28T00:00",
            "2026-08-28T01:00", "2026-08-29T00:00",
        ],
        "temperature_2m": [41.0, 42.25, 43.5, 44.0],
    }}

    targets = fi.capture_next_day_hourly(snapshot, now)

    assert targets == {
        "2026-08-28T00:00:00-06:00": {
            "raw": 42.25, "captured_at": "2026-08-27T06:40:00-06:00",
        },
        "2026-08-28T01:00:00-06:00": {
            "raw": 43.5, "captured_at": "2026-08-27T06:40:00-06:00",
        },
    }


def test_capture_next_day_hourly_uses_distinct_offset_keys_for_repeated_dst_hour():
    now = datetime(2026, 10, 31, 6, 40, tzinfo=fi.MOUNTAIN)
    snapshot = {"hourly": {
        "time": ["2026-11-01T01:00", "2026-11-01T01:00", "2026-11-01T02:00"],
        "temperature_2m": [30.0, 29.0, 28.0],
    }}

    targets = fi.capture_next_day_hourly(snapshot, now)

    assert list(targets) == [
        "2026-11-01T01:00:00-06:00",
        "2026-11-01T01:00:00-07:00",
        "2026-11-01T02:00:00-07:00",
    ]
    assert [target["raw"] for target in targets.values()] == [30.0, 29.0, 28.0]


def test_capture_next_day_hourly_rejects_nonfinite_raw_values():
    now = datetime(2026, 8, 27, 6, 40, tzinfo=fi.MOUNTAIN)
    snapshot = {"hourly": {
        "time": ["2026-08-28T00:00", "2026-08-28T01:00", "2026-08-28T02:00"],
        "temperature_2m": [float("nan"), float("inf"), 44.0],
    }}

    targets = fi.capture_next_day_hourly(snapshot, now)

    assert list(targets) == ["2026-08-28T02:00:00-06:00"]


def test_score_hourly_targets_uses_earlier_nearest_tie_and_raw_innovation(monkeypatch):
    target = datetime(2026, 8, 27, 12, 0, tzinfo=fi.MOUNTAIN)
    key = target.isoformat()
    future_key = datetime(2026, 8, 27, 14, 0, tzinfo=fi.MOUNTAIN).isoformat()
    state = {
        "hourly_temp_model": fi.hourly_model_seed(),
        "hourly_temp_targets": {
            key: {"raw": 74.0, "captured_at": "2026-08-26T06:40:00-06:00"},
            future_key: {"raw": 80.0, "captured_at": "2026-08-26T06:40:00-06:00"},
        },
    }
    calls = []

    def observations(item, start, end):
        calls.append((item, start, end))
        return [
            (target.astimezone(UTC) - timedelta(minutes=10), 70.0),
            (target.astimezone(UTC) + timedelta(minutes=10), 80.0),
        ]

    monkeypatch.setattr(fi, "series", observations)

    assert fi.score_hourly_targets(
        state, target + timedelta(minutes=30)
    ) == 1

    bucket = state["hourly_temp_model"]["12"]
    gain = 10.1 / (10.1 + 9.0)
    assert bucket["b"] == pytest.approx(round(gain * (74.0 - 70.0), 3))
    assert bucket["P"] == pytest.approx(round((1 - gain) * 10.1, 4))
    assert bucket["count"] == 1
    assert key not in state["hourly_temp_targets"]
    assert future_key in state["hourly_temp_targets"]
    assert len(calls) == 1
    item, start, end = calls[0]
    assert item == fi.OUTDOOR_TEMP_ITEM
    assert start == target.astimezone(UTC) - timedelta(minutes=15)
    assert end > target.astimezone(UTC) + timedelta(minutes=15)


def test_score_hourly_targets_keeps_unmatched_and_rejects_nonfinite_observation(monkeypatch):
    target = datetime(2026, 8, 27, 12, 0, tzinfo=fi.MOUNTAIN)
    key = target.isoformat()
    state = {
        "hourly_temp_model": fi.hourly_model_seed(),
        "hourly_temp_targets": {
            key: {"raw": 74.0, "captured_at": "2026-08-26T06:40:00-06:00"},
        },
    }
    monkeypatch.setattr(fi, "series", lambda *_: [
        (target.astimezone(UTC), float("nan")),
        (target.astimezone(UTC) + timedelta(minutes=16), 70.0),
    ])

    assert fi.score_hourly_targets(state, target + timedelta(minutes=30)) == 0

    assert key in state["hourly_temp_targets"]
    assert state["hourly_temp_model"]["12"]["count"] == 0


def test_score_hourly_targets_prunes_only_after_72_hours(monkeypatch):
    now = datetime(2026, 8, 27, 12, 0, tzinfo=fi.MOUNTAIN)
    exactly_72h = (now - timedelta(hours=72)).isoformat()
    stale = (now - timedelta(hours=72, seconds=1)).isoformat()
    state = {"hourly_temp_targets": {
        exactly_72h: {"raw": 40.0, "captured_at": now.isoformat()},
        stale: {"raw": 39.0, "captured_at": now.isoformat()},
    }}
    monkeypatch.setattr(fi, "series", lambda *_: [])

    assert fi.score_hourly_targets(state, now) == 0

    assert exactly_72h in state["hourly_temp_targets"]
    assert stale not in state["hourly_temp_targets"]


def test_score_hourly_targets_bounds_newest_96(monkeypatch):
    now = datetime(2026, 8, 27, 12, 0, tzinfo=fi.MOUNTAIN)
    newest = []
    targets = {}
    for minute in range(100):
        key = (now + timedelta(days=1, minutes=minute)).isoformat()
        newest.append(key)
        targets[key] = {"raw": 50.0, "captured_at": now.isoformat()}
    state = {"hourly_temp_targets": targets}
    monkeypatch.setattr(fi, "series", lambda *_: [])

    assert fi.score_hourly_targets(state, now) == 0

    assert list(state["hourly_temp_targets"]) == newest[-96:]


def test_score_hourly_targets_repeated_dst_instants_share_local_hour_bucket(monkeypatch):
    first = datetime.fromisoformat("2026-11-01T01:00:00-06:00")
    second = datetime.fromisoformat("2026-11-01T01:00:00-07:00")
    state = {
        "hourly_temp_model": fi.hourly_model_seed(),
        "hourly_temp_targets": {
            first.isoformat(): {"raw": 35.0, "captured_at": "2026-10-31T06:40:00-06:00"},
            second.isoformat(): {"raw": 34.0, "captured_at": "2026-10-31T06:40:00-06:00"},
        },
    }
    monkeypatch.setattr(fi, "series", lambda *_: [
        (first.astimezone(UTC), 33.0),
        (second.astimezone(UTC), 30.0),
    ])

    assert fi.score_hourly_targets(state, second + timedelta(minutes=30)) == 2

    assert state["hourly_temp_targets"] == {}
    assert state["hourly_temp_model"]["1"]["count"] == 2
    assert sum(bucket["count"] for bucket in state["hourly_temp_model"].values()) == 2


def test_hourly_blend_moves_from_daily_fallback_to_bucket_bias():
    bucket = {"b": 4.0, "P": 1.0, "count": 7}
    # raw 50 is halfway from daily 40..60; fallback correction is (-8 + 2)/2 = -3
    assert fi.hourly_temperature_correction(50, 40, 60, -8, 2, bucket) == -3.5


def test_hourly_correction_uses_bucket_at_full_weight_without_feedback():
    bucket = {"b": 4.25, "P": 1.0, "count": 14}

    assert fi.hourly_temperature_correction(50, 40, 60, -8, 2, bucket) == -4.2
    assert bucket == {"b": 4.25, "P": 1.0, "count": 14}


def test_hourly_correction_clamps():
    assert fi.hourly_temperature_correction(
        50, 40, 60, -50, -50, {"b": 0, "P": 1, "count": 0}
    ) == -20
    assert fi.hourly_temperature_correction(
        50, 40, 60, 50, 50, {"b": 0, "P": 1, "count": 0}
    ) == 20


def test_main_saves_hourly_score_before_later_failure(monkeypatch):
    target = datetime.now(fi.MOUNTAIN).replace(microsecond=0) - timedelta(hours=1)
    key = target.isoformat()
    state = json.loads(json.dumps(fi.DEFAULT_STATE))
    state["hourly_temp_targets"][key] = {
        "raw": 64.0,
        "captured_at": (target - timedelta(days=1)).isoformat(),
    }
    saves = []
    monkeypatch.setattr(fi, "load_state", lambda: state)
    monkeypatch.setattr(
        fi, "save_state",
        lambda current: saves.append(json.loads(json.dumps(current))),
    )
    monkeypatch.setattr(
        fi, "series",
        lambda item, *_: [(target.astimezone(UTC), 60.0)]
        if item == fi.OUTDOOR_TEMP_ITEM else [],
    )

    def fail_after_score(_day):
        raise RuntimeError("post-score failure")

    monkeypatch.setattr(fi, "measured_day_weather", fail_after_score)

    with pytest.raises(RuntimeError, match="post-score failure"):
        fi.main()

    assert len(saves) == 1
    saved = saves[0]
    assert key not in saved["hourly_temp_targets"]
    assert saved["hourly_temp_model"][str(target.hour)]["count"] == 1


def test_main_saves_first_hourly_capture_before_failure_and_retry(monkeypatch):
    now_local = datetime.now(fi.MOUNTAIN)
    target_wall = f"{(now_local.date() + timedelta(days=1)).isoformat()}T12:00"
    target_key = fi._offset_timestamp(target_wall).isoformat(timespec="seconds")
    durable = json.loads(json.dumps(fi.DEFAULT_STATE))
    snapshots = iter([
        {"daily": {}, "hourly": {"time": [target_wall], "temperature_2m": [41.0]}},
        {"daily": {}, "hourly": {"time": [target_wall], "temperature_2m": [99.0]}},
    ])

    def load():
        return json.loads(json.dumps(durable))

    def save(current):
        durable.clear()
        durable.update(json.loads(json.dumps(current)))

    monkeypatch.setattr(fi, "load_state", load)
    monkeypatch.setattr(fi, "save_state", save)
    monkeypatch.setattr(fi, "measured_day_weather", lambda _day: (None, None, None))
    monkeypatch.setattr(fi, "fetch_forecast", lambda: next(snapshots))

    with pytest.raises(KeyError, match="temperature_2m_max"):
        fi.main()
    first_record = json.loads(json.dumps(durable["hourly_temp_targets"][target_key]))
    assert first_record["raw"] == 41.0

    with pytest.raises(KeyError, match="temperature_2m_max"):
        fi.main()

    assert durable["hourly_temp_targets"][target_key] == first_record
