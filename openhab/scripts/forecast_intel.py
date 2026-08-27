#!/usr/bin/env python3
"""Forecast intelligence for the Earthship (design: docs/plans/2026-07-17-openmeteo-forecast-integration-design.md).

Daily at 06:40: score yesterday's predictions against measured actuals,
calibrate the transparent model coefficients, predict today (PV kWh,
curtailment hours, tonight's SoC trough), issue the thermal advisory, and
materialize tomorrow-snapshot items for the UI. Accuracy is the product:
rolling errors are posted to items and shown next to every prediction.

Model (validated against 30 days of history, 2026-07-17):
  PV_pred = min(k_res × RadSum_kWh/m², Demand)
  Demand  = D_direct + (100 − dawn_trough)/100 × BANK_KWH / 0.95   [kWh]
  k_res   seeded 1.0  [0.5, 1.3]  — calibrated on resource-limited (cloudy) days
  D_direct seeded 4.0 [2.5, 6.0]  — calibrated on demand-limited (curtailing) days
DM policy: ONLY predicted trough < 30% (full 4P 400 Ah bank, 20.48 kWh, since 2026-07-18).
"""
import json, math, os, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

BASE = "http://127.0.0.1:8080/rest"
ENV_FILE = os.path.expanduser("~/.config/hex/openhab.env")
NOTIFY = "/etc/openhab/scripts/nostr_notify.sh"
STATE_DIR = os.path.expanduser("~/.local/state/forecast-intel")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
BANK_KWH, RESERVE_SOC, ETA_RT = 20.48, 10, 0.95  # full 4P 400Ah bank (2026-07-19; was 5.12 single-module interim)
K_RES_BOUNDS, D_DIRECT_BOUNDS, ALPHA = (0.5, 1.3), (2.5, 6.0), 0.2
TROUGH_DM_THRESHOLD = 30  # full-bank policy (was 42 on the single 100 Ah bank)
DETAIL_MAX_BYTES = 64 * 1024
_TOKEN = None

# ---- Site settings -------------------------------------------------------
# openHAB is authoritative for where and in which zone this site sits
# (Settings > Regional). These literals are only the fallback used before
# load_site_settings() runs and whenever that read fails — the pipeline must
# never die because a config fetch flaked. They matched openHAB as of
# 2026-07-26 (the previous longitude literal had drifted 2.8 m).
I18N_CONFIG_PATH = "/services/org.openhab.i18n/config"
FALLBACK_LAT, FALLBACK_LON = 38.3739919, -105.7744609
FALLBACK_TZ_NAME = "America/Denver"


def open_meteo_url(lat, lon, tz_name):
    return (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&hourly=temperature_2m,precipitation_probability,precipitation,"
            "shortwave_radiation,wind_speed_10m,weather_code"
            "&daily=temperature_2m_max,temperature_2m_min,shortwave_radiation_sum,"
            "precipitation_probability_max,precipitation_sum,cloud_cover_mean,weather_code"
            "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
            f"&timezone={urllib.parse.quote(tz_name, safe='')}&forecast_days=10")


# Rebound by load_site_settings(). MOUNTAIN keeps its name: it is the site's
# local zone, referenced at ~18 call sites and imported by forecast_backfill.
LAT, LON = FALLBACK_LAT, FALLBACK_LON
SITE_TZ_NAME = FALLBACK_TZ_NAME
MOUNTAIN = ZoneInfo(FALLBACK_TZ_NAME)
OM_URL = open_meteo_url(LAT, LON, SITE_TZ_NAME)


def _parse_site_config(config):
    """Validate openHAB's regional config, or return None to keep fallbacks.

    All-or-nothing on purpose: a half-adopted config (real coordinates, junk
    zone) would score days against the wrong window, which is worse than
    uniformly using the known-good literals.
    """
    if not isinstance(config, dict):
        return None
    lat_lon = str(config.get("location", "")).split(",")
    if len(lat_lon) != 2:
        return None
    try:
        lat, lon = float(lat_lon[0]), float(lat_lon[1])
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    tz_name = str(config.get("timezone", ""))
    try:
        zone = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return lat, lon, tz_name, zone


def load_site_settings():
    """Adopt openHAB's location/timezone once at startup; never raise."""
    global LAT, LON, SITE_TZ_NAME, MOUNTAIN, OM_URL
    try:
        parsed = _parse_site_config(oh_get(I18N_CONFIG_PATH))
    except Exception as e:
        print(f"site settings: openHAB read failed ({e}); using fallbacks", file=sys.stderr)
        parsed = None
    if parsed is None:
        LAT, LON = FALLBACK_LAT, FALLBACK_LON
        SITE_TZ_NAME = FALLBACK_TZ_NAME
    else:
        LAT, LON, SITE_TZ_NAME, _zone = parsed
    MOUNTAIN = ZoneInfo(SITE_TZ_NAME)
    OM_URL = open_meteo_url(LAT, LON, SITE_TZ_NAME)


def token():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip().removeprefix("export ")
            if line.startswith("OPENHAB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("no token")


def auth_token():
    global _TOKEN
    if _TOKEN is None:
        _TOKEN = token()
    return _TOKEN


def oh_get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + auth_token()})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def oh_put_state(item, value):
    req = urllib.request.Request(f"{BASE}/items/{item}/state", data=str(value).encode(),
                                 headers={"Authorization": "Bearer " + auth_token(),
                                          "Content-Type": "text/plain"}, method="PUT")
    urllib.request.urlopen(req, timeout=15)


def safe_put(item, value, failures=None):
    """PUT one item, never raise: one openHAB flap must not abort the run.

    Failed item names are appended to `failures` so the caller can log them.
    Returns True on success.
    """
    try:
        oh_put_state(item, value)
        return True
    except Exception as e:
        print(f"PUT failed for {item}: {e}", file=sys.stderr)
        if failures is not None:
            failures.append(item)
        return False


def fetch_forecast(url=None, attempts=3, delays=(10, 30), opener=None, sleep=None):
    """Fetch the Open-Meteo snapshot with a small retry (transient net flaps)."""
    # Resolved at call time, not as a default arg: a `url=OM_URL` default binds
    # at import and would silently ignore whatever load_site_settings adopted.
    url = url or OM_URL
    opener = opener or (lambda u: urllib.request.urlopen(u, timeout=20))
    sleep = sleep or time.sleep
    last = None
    for attempt in range(1, attempts + 1):
        try:
            with opener(url) as r:
                return json.load(r)
        except Exception as e:
            last = e
            print(f"open-meteo fetch attempt {attempt}/{attempts} failed: {e}", file=sys.stderr)
            if attempt < attempts:
                sleep(delays[min(attempt - 1, len(delays) - 1)])
    raise last


def series(item, start, end):
    """Persistence points for [start, end).

    Aware datetimes are converted to true UTC for the REST query (openHAB
    expects "...Z"); naive datetimes are assumed to already be UTC wall time
    (legacy callers). Returned timestamps are aware UTC. Unparseable persisted
    states (UNDEF/NULL/garbage) are skipped instead of raising.
    """
    fmt = "%Y-%m-%dT%H:%M:%SZ"

    def as_utc(dt):
        return dt if dt.tzinfo is None else dt.astimezone(timezone.utc)

    d = oh_get(f"/persistence/items/{item}?starttime={as_utc(start).strftime(fmt)}"
               f"&endtime={as_utc(end).strftime(fmt)}")
    pts = []
    for p in d.get("data", []):
        try:
            pts.append((datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc),
                        float(str(p["state"]).split()[0])))
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    return pts


def local_day_window_utc(day):
    """UTC (start, end) covering one local America/Denver calendar day.

    Exact across DST: boundaries are true local midnights converted to UTC,
    so the window is 23/24/25 h as appropriate. This replaces the old fixed
    utc_off=6h shift which, in winter (MST = UTC-7), started the window one
    hour early and leaked the previous day's 23:00 point of midnight-reset
    accumulators (PV today, RainFallDay) into the next day's max().
    """
    start = datetime.combine(day, datetime.min.time(), tzinfo=MOUNTAIN)
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=MOUNTAIN)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)



HOURLY_KALMAN_Q = 0.10
HOURLY_KALMAN_R = 9.0
HOURLY_TARGET_LIMIT = 96
HOURLY_TARGET_MAX_AGE = timedelta(hours=72)
HOURLY_MATCH_WINDOW = timedelta(minutes=15)


def hourly_model_seed():
    """Return one independent scalar-bias bucket for each local clock hour."""
    return {
        str(hour): {"b": 0.0, "P": 10.0, "count": 0}
        for hour in range(24)
    }

DEFAULT_STATE = {"k_res": 1.0, "d_direct": 4.0, "predictions": {},
                 "pv_errors": [], "trough_errors": [], "dm_sent": {},
                 "hourly_temp_model": hourly_model_seed(),
                 "hourly_temp_targets": {}}


def _quarantine_state():
    quarantine = STATE_FILE + ".corrupt-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        os.replace(STATE_FILE, quarantine)
        print(f"CORRUPT STATE: {STATE_FILE} failed to parse; quarantined to "
              f"{quarantine}; starting from defaults", file=sys.stderr)
    except OSError as e:
        print(f"CORRUPT STATE: {STATE_FILE} failed to parse and quarantine "
              f"failed ({e}); starting from defaults", file=sys.stderr)


def load_state():
    """Load state, merged over defaults so missing keys never KeyError.

    A file that exists but does not parse is precious evidence (learned k_res,
    kalman biases) — it is quarantined to state.json.corrupt-<ts>, loudly
    logged, and defaults are returned, instead of being silently shadowed and
    later overwritten by save_state.
    """
    defaults = json.loads(json.dumps(DEFAULT_STATE))   # deep copy
    try:
        with open(STATE_FILE) as f:
            loaded = json.load(f)
    except OSError:
        return defaults          # first run: no file yet
    except ValueError:
        _quarantine_state()
        return defaults
    if not isinstance(loaded, dict):
        _quarantine_state()
        return defaults
    defaults.update(loaded)      # schema-tolerant: old files lacking new keys
    loaded_model = loaded.get("hourly_temp_model")
    if isinstance(loaded_model, dict):
        model = hourly_model_seed()
        for hour, bucket in loaded_model.items():
            if hour in model and isinstance(bucket, dict):
                model[hour].update(bucket)
        defaults["hourly_temp_model"] = model
    if not isinstance(defaults.get("hourly_temp_targets"), dict):
        defaults["hourly_temp_targets"] = {}
    return defaults


def save_state(st):
    """Atomic write: temp file in the same dir, fsync, os.replace.

    A crash or full disk mid-write must never leave a truncated state.json —
    the learned calibration in it is irreplaceable.
    """
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, STATE_FILE)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


SCORE_QUANTITIES = ("pv", "trough", "precip", "hi", "lo")


def _migrate_scored(state):
    """Honor a legacy whole-day last_scored_day marker on first run after
    upgrade: treat every quantity as scored for that day, then the
    per-quantity structure takes over."""
    legacy = state.pop("last_scored_day", None)
    if legacy:
        state.setdefault("scored", {}).setdefault(legacy, list(SCORE_QUANTITIES))


def should_score(state, ykey, quantity):
    """True if `quantity` has not yet been scored for day ykey.

    Scoring appends to rolling error arrays, so each quantity must score at
    most once per day (the 2026-07-19 dev session fired the service 5x and
    duplicated errors). Markers are PER QUANTITY because a whole-day flag
    marked days scored even when some series had no data yet — live evidence:
    precip_errors stayed stuck while temps scored. A same-day re-run may now
    pick up quantities that were missing earlier without double-appending the
    ones that already scored.
    """
    _migrate_scored(state)
    return quantity not in state.get("scored", {}).get(ykey, [])


def mark_scored(state, ykey, quantity):
    """Mark one quantity scored for ykey; prune markers to the last 3 days."""
    _migrate_scored(state)
    day = state.setdefault("scored", {}).setdefault(ykey, [])
    if quantity not in day:
        day.append(quantity)
    for stale in sorted(state["scored"])[:-3]:
        state["scored"].pop(stale, None)


# --- Kalman bias filters (ML v3a, 2026-07-19) -------------------------------
# Scalar random-walk bias per quantity: state b = (forecast - measured) bias,
# P = its variance. Q (drift/day) and R (daily error variance) from the
# 364-day backfill analysis. Radiation deliberately has NO filter: its bias is
# proportional (measured/forecast ~ 0.66, stable) and k_res already learns
# that ratio — an additive filter here would double-correct.
KALMAN_CFG = {
    "hi": {"Q": 0.05, "R": 6.0},
    "lo": {"Q": 0.10, "R": 32.0},
}
BACKFILL_CSV = os.path.expanduser("~/.local/state/forecast-intel/backfill/dataset.csv")


def kalman_seed():
    """Seed biases from the last 60 backfilled days; fall back to the
    year-long constants from the 2026-07-19 analysis if the csv is absent."""
    seeds = {"hi": -2.5, "lo": 9.0}
    import csv as _csv
    try:
        with open(BACKFILL_CSV, newline="") as f:
            rows = list(_csv.DictReader(f))[-60:]
        for key, fc_col, m_col in (("hi", "fc_hi", "m_hi"), ("lo", "fc_lo", "m_lo")):
            errs = []
            for row in rows:
                try:
                    errs.append(float(row[fc_col]) - float(row[m_col]))
                except (KeyError, TypeError, ValueError):
                    continue
            if errs:
                seeds[key] = round(sum(errs) / len(errs), 2)
    except (OSError, _csv.Error, UnicodeDecodeError, ValueError) as e:
        print(f"kalman_seed: falling back to year-long constants ({e})", file=sys.stderr)
    return {key: {"b": seeds[key], "P": 1.0} for key in KALMAN_CFG}


def kalman_update(filt, key, err):
    """One innovation step: err = raw_forecast - measured for the scored day."""
    cfg = KALMAN_CFG[key]
    state = filt[key]
    P = state["P"] + cfg["Q"]
    K = P / (P + cfg["R"])
    state["b"] = round(state["b"] + K * (err - state["b"]), 3)
    state["P"] = round((1 - K) * P, 4)
    return state["b"]


def measured_trough(for_night_ending_today):
    """min(BMS_SOC) 20:00 previous day -> 11:00 given day, local time."""
    d0 = for_night_ending_today
    start = datetime.combine(d0 - timedelta(days=1), datetime.min.time(), tzinfo=MOUNTAIN).replace(hour=20)
    end = datetime.combine(d0, datetime.min.time(), tzinfo=MOUNTAIN).replace(hour=11)
    pts = series("BMS_SOC", start.astimezone(timezone.utc), end.astimezone(timezone.utc))
    return min((v for _, v in pts), default=None)


OUTDOOR_TEMP_ITEM = "AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature"
RAIN_DAY_ITEM = "AmbientWeatherWS2902A_RainFallDay"


def measured_day_weather(day):
    """(rain_total_in, temp_hi_f, temp_lo_f) for one local calendar day.

    Rain uses max(RainFallDay) — the gauge's daily accumulator resets at
    midnight, so the day's maximum is its total. The window is the exact
    local calendar day (see local_day_window_utc) in both MST and MDT.
    """
    window = local_day_window_utc(day)
    rain = max((v for _, v in series(RAIN_DAY_ITEM, *window)), default=None)
    temps = [v for _, v in series(OUTDOOR_TEMP_ITEM, *window)]
    return rain, (max(temps) if temps else None), (min(temps) if temps else None)


def _series_value(series_data, key, index):
    values = series_data.get(key, [])
    return values[index] if index < len(values) else None


def _rounded(value):
    return round(value) if value is not None else None


def _hour_label(local_timestamp):
    hr = int(local_timestamp[11:13])
    return "12a" if hr == 0 else (f"{hr}a" if hr < 12 else ("12p" if hr == 12 else f"{hr-12}p"))


def _offset_timestamp(local_timestamp, previous=None):
    """Attach the correct Mountain offset, including repeated DST hours."""
    parsed = datetime.fromisoformat(local_timestamp)
    if parsed.tzinfo is not None:
        return parsed.astimezone(MOUNTAIN)
    candidates = {
        parsed.replace(tzinfo=MOUNTAIN, fold=fold).timestamp():
        parsed.replace(tzinfo=MOUNTAIN, fold=fold)
        for fold in (0, 1)
    }
    ordered = [candidates[key] for key in sorted(candidates)]
    if previous is not None:
        later = [candidate for candidate in ordered if candidate.timestamp() > previous.timestamp()]
        if later:
            return later[0]
    return ordered[0]



def _local_datetime(value):
    """Normalize an input datetime to the configured site zone."""
    return (value.replace(tzinfo=MOUNTAIN) if value.tzinfo is None
            else value.astimezone(MOUNTAIN))


def _target_instant(value):
    """Parse an offset-aware target key as a UTC instant, or return None."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _observation_instant(value):
    """Normalize persistence timestamps; legacy naive rows are UTC wall time."""
    try:
        parsed = (datetime.fromisoformat(value.replace("Z", "+00:00"))
                  if isinstance(value, str) else value)
    except ValueError:
        return None
    if not isinstance(parsed, datetime):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ensure_hourly_model(state):
    model = hourly_model_seed()
    loaded = state.get("hourly_temp_model")
    if isinstance(loaded, dict):
        for hour, bucket in loaded.items():
            if hour in model and isinstance(bucket, dict):
                model[hour].update(bucket)
    state["hourly_temp_model"] = model
    return model


def _bound_hourly_targets(state):
    """Keep valid offset-aware target records ordered by instant, newest 96."""
    targets = state.get("hourly_temp_targets")
    if not isinstance(targets, dict):
        targets = {}
    ordered = sorted(
        ((instant, key, record)
         for key, record in targets.items()
         if (instant := _target_instant(key)) is not None and isinstance(record, dict)),
        key=lambda row: (row[0], row[1]),
    )[-HOURLY_TARGET_LIMIT:]
    state["hourly_temp_targets"] = {key: record for _, key, record in ordered}
    return state["hourly_temp_targets"]


def capture_next_day_hourly(snapshot, now):
    """Return one raw provider target for each hour of the next local day."""
    now_local = _local_datetime(now)
    capture_key = now_local.isoformat(timespec="seconds")
    next_day = now_local.date() + timedelta(days=1)
    hourly = snapshot.get("hourly", {}) if isinstance(snapshot, dict) else {}
    times = hourly.get("time", []) if isinstance(hourly, dict) else []
    temperatures = hourly.get("temperature_2m", []) if isinstance(hourly, dict) else []
    targets = {}
    previous = None
    for timestamp, raw_value in zip(times, temperatures):
        try:
            target = _offset_timestamp(timestamp, previous=previous)
        except (TypeError, ValueError):
            continue
        previous = target
        if target.date() != next_day or isinstance(raw_value, bool):
            continue
        try:
            raw = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(raw):
            continue
        targets[target.isoformat(timespec="seconds")] = {
            "raw": raw, "captured_at": capture_key,
        }
    return targets


def score_hourly_targets(state, now):
    """Score elapsed raw targets once against nearest trustworthy observations."""
    now_utc = _local_datetime(now).astimezone(timezone.utc)
    model = _ensure_hourly_model(state)
    targets = state.get("hourly_temp_targets")
    if not isinstance(targets, dict):
        targets = {}
        state["hourly_temp_targets"] = targets

    for key in list(targets):
        instant = _target_instant(key)
        if instant is not None and now_utc - instant > HOURLY_TARGET_MAX_AGE:
            targets.pop(key, None)
    targets = _bound_hourly_targets(state)

    elapsed = []
    for key, record in targets.items():
        instant = _target_instant(key)
        if instant is not None and instant + HOURLY_MATCH_WINDOW <= now_utc:
            elapsed.append((instant, key, record))
    if not elapsed:
        return 0

    start = min(row[0] for row in elapsed) - HOURLY_MATCH_WINDOW
    end = max(row[0] for row in elapsed) + HOURLY_MATCH_WINDOW + timedelta(seconds=1)
    try:
        rows = series(OUTDOOR_TEMP_ITEM, start, end)
    except Exception:
        return 0
    observations = []
    for timestamp, measured_value in rows:
        instant = _observation_instant(timestamp)
        if instant is None or isinstance(measured_value, bool):
            continue
        try:
            measured = float(measured_value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(measured):
            observations.append((instant, measured))

    scored = 0
    for target, key, record in elapsed:
        raw_value = record.get("raw")
        if isinstance(raw_value, bool):
            continue
        try:
            raw = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(raw):
            continue
        candidates = [
            (abs((instant - target).total_seconds()), instant, measured)
            for instant, measured in observations
            if abs((instant - target).total_seconds()) <= HOURLY_MATCH_WINDOW.total_seconds()
        ]
        if not candidates:
            continue
        _, _, measured = min(candidates, key=lambda row: (row[0], row[1]))
        hour = str(target.astimezone(MOUNTAIN).hour)
        bucket = model[hour]
        try:
            bias, variance = float(bucket["b"]), float(bucket["P"])
            count = int(bucket.get("count", 0))
        except (KeyError, TypeError, ValueError, OverflowError):
            bias, variance, count = 0.0, 10.0, 0
        if not math.isfinite(bias) or not math.isfinite(variance):
            bias, variance = 0.0, 10.0
        predicted_variance = variance + HOURLY_KALMAN_Q
        gain = predicted_variance / (predicted_variance + HOURLY_KALMAN_R)
        innovation = raw - measured
        bucket["b"] = round(bias + gain * (innovation - bias), 3)
        bucket["P"] = round((1 - gain) * predicted_variance, 4)
        bucket["count"] = max(count, 0) + 1
        targets.pop(key, None)
        scored += 1
    return scored


def hourly_temperature_correction(raw, raw_low, raw_high, low_correction,
                                  high_correction, bucket):
    """Blend daily fallback toward learned local-hour correction."""
    position = (clamp((raw - raw_low) / (raw_high - raw_low), 0.0, 1.0)
                if raw_high > raw_low else 0.5)
    fallback = low_correction + position * (high_correction - low_correction)
    learned = -bucket["b"]
    weight = min(bucket["count"] / 14.0, 1.0)
    return round(clamp(fallback * (1 - weight) + learned * weight,
                       -20.0, 20.0), 1)

def _finite_correction(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _hourly_model_snapshot(hourly_model=None):
    """Return a safe generation-time copy without mutating learned state."""
    source = hourly_model if isinstance(hourly_model, dict) else {}
    model = hourly_model_seed()
    for hour in range(24):
        bucket = source.get(str(hour))
        if not isinstance(bucket, dict):
            continue
        bias = bucket.get("b")
        variance = bucket.get("P")
        count = bucket.get("count")
        if (not isinstance(bias, bool) and isinstance(bias, (int, float))
                and math.isfinite(bias)):
            model[str(hour)]["b"] = bias
        if (not isinstance(variance, bool)
                and isinstance(variance, (int, float))
                and math.isfinite(variance)):
            model[str(hour)]["P"] = variance
        if not isinstance(count, bool) and isinstance(count, int) and count >= 0:
            model[str(hour)]["count"] = count
    return model


def normalize_temperature_adjustment(adjustment=None, hourly_model=None):
    """Return daily corrections plus generation-time hourly provenance."""
    source = adjustment if isinstance(adjustment, dict) else {}
    model = _hourly_model_snapshot(hourly_model)
    buckets = [
        {
            "hour": hour,
            "count": model[str(hour)]["count"],
            "weight": min(model[str(hour)]["count"] / 14.0, 1.0),
        }
        for hour in range(24)
    ]
    return {
        "highCorrectionF": _finite_correction(source.get("highCorrectionF")),
        "lowCorrectionF": _finite_correction(source.get("lowCorrectionF")),
        "hourlyMethod": ("hourly-blend"
                         if any(bucket["count"] > 0 for bucket in buckets)
                         else "daily-fallback"),
        "hourBuckets": buckets,
    }


def temperature_adjustment_from_state(state):
    """Read learned biases without adding defaults to persisted state."""
    source = state if isinstance(state, dict) else {}
    kalman = source.get("kalman", {})
    high = kalman.get("hi", {}) if isinstance(kalman, dict) else {}
    low = kalman.get("lo", {}) if isinstance(kalman, dict) else {}
    high_bias = high.get("b") if isinstance(high, dict) else None
    low_bias = low.get("b") if isinstance(low, dict) else None
    return normalize_temperature_adjustment({
        "highCorrectionF": -_finite_correction(high_bias),
        "lowCorrectionF": -_finite_correction(low_bias),
    }, hourly_model=source.get("hourly_temp_model"))


def _adjusted_temperature(value, correction):
    return value + correction if value is not None else None


def build_forecast_payloads(snapshot, pv_per_day, now, temperature_adjustment=None,
                            hourly_model=None):
    """Return legacy payloads plus corrected detail v2 from one snapshot."""
    model = _hourly_model_snapshot(hourly_model)
    adjustment = normalize_temperature_adjustment(temperature_adjustment, model)
    high_correction = adjustment["highCorrectionF"]
    low_correction = adjustment["lowCorrectionF"]
    hourly = snapshot["hourly"]
    daily = snapshot["daily"]
    if now.tzinfo is None:
        now_local = now.replace(tzinfo=MOUNTAIN)
    else:
        now_local = now.astimezone(MOUNTAIN)
    pv_days = list(pv_per_day or [])

    day_indexes = {
        day_string: index for index, day_string in enumerate(daily["time"])
    }
    corrected_hours = []
    previous = None
    for index, local_timestamp in enumerate(hourly["time"]):
        aware = _offset_timestamp(local_timestamp, previous)
        previous = aware
        raw = _series_value(hourly, "temperature_2m", index)
        day_index = day_indexes.get(local_timestamp[:10])
        raw_low = (_series_value(daily, "temperature_2m_min", day_index)
                   if day_index is not None else None)
        raw_high = (_series_value(daily, "temperature_2m_max", day_index)
                    if day_index is not None else None)
        corrected = raw
        values = (raw, raw_low, raw_high)
        if all(not isinstance(value, bool) and isinstance(value, (int, float))
               and math.isfinite(value) for value in values):
            correction = hourly_temperature_correction(
                raw, raw_low, raw_high, low_correction, high_correction,
                model[str(aware.hour)],
            )
            corrected = raw + correction
        corrected_hours.append((aware, corrected))

    now_iso = now_local.strftime("%Y-%m-%dT%H:00")
    try:
        start = hourly["time"].index(now_iso)
    except ValueError:
        start = 0
    legacy_hourly = []
    for index in range(start, min(start + 14, len(hourly["time"]))):
        legacy_hourly.append({
            "h": _hour_label(hourly["time"][index]),
            "t": _rounded(corrected_hours[index][1]),
            "p": _series_value(hourly, "precipitation_probability", index) or 0,
            "a": round(_series_value(hourly, "precipitation", index) or 0, 2),
            "r": _rounded(_series_value(hourly, "shortwave_radiation", index) or 0),
            "w": _series_value(hourly, "weather_code", index),
        })

    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    legacy_daily = []
    day_count = min(10, len(daily["time"]))
    for index in range(min(7, day_count)):
        day_date = date.fromisoformat(daily["time"][index])
        legacy_daily.append({
            "d": "Today" if day_date == now_local.date() else names[day_date.weekday()],
            "hi": _rounded(_adjusted_temperature(
                _series_value(daily, "temperature_2m_max", index), high_correction)),
            "lo": _rounded(_adjusted_temperature(
                _series_value(daily, "temperature_2m_min", index), low_correction)),
            "p": _series_value(daily, "precipitation_probability_max", index) or 0,
            "a": round(_series_value(daily, "precipitation_sum", index) or 0, 2),
            "w": _series_value(daily, "weather_code", index),
            "pv": pv_days[index] if index < len(pv_days) else None,
        })

    hours_by_date = {day_string: [] for day_string in daily["time"][:day_count]}
    for index, local_timestamp in enumerate(hourly["time"]):
        aware, corrected = corrected_hours[index]
        day_string = local_timestamp[:10]
        if day_string not in hours_by_date:
            continue
        hours_by_date[day_string].append({
            "at": aware.isoformat(timespec="seconds"),
            "tempF": corrected,
            "precipPct": _series_value(hourly, "precipitation_probability", index),
            "precipIn": _series_value(hourly, "precipitation", index),
            "radiationWm2": _series_value(hourly, "shortwave_radiation", index),
            "windMph": _series_value(hourly, "wind_speed_10m", index),
            "weatherCode": _series_value(hourly, "weather_code", index),
        })

    detail_days = []
    for index, day_string in enumerate(daily["time"][:day_count]):
        day_date = date.fromisoformat(day_string)
        detail_days.append({
            "date": day_string,
            "label": "Today" if day_date == now_local.date() else names[day_date.weekday()],
            "summary": {
                "highF": _adjusted_temperature(
                    _series_value(daily, "temperature_2m_max", index), high_correction),
                "lowF": _adjusted_temperature(
                    _series_value(daily, "temperature_2m_min", index), low_correction),
                "precipPct": _series_value(daily, "precipitation_probability_max", index),
                "precipSumIn": _series_value(daily, "precipitation_sum", index),
                "weatherCode": _series_value(daily, "weather_code", index),
                "pvKwh": pv_days[index] if index < len(pv_days) else None,
            },
            "hours": hours_by_date[day_string],
        })

    detail = {
        "version": 2,
        "generatedAt": now_local.isoformat(timespec="seconds"),
        "timezone": SITE_TZ_NAME,
        "temperatureAdjustment": adjustment,
        "days": detail_days,
    }
    return legacy_hourly, legacy_daily, detail


def serialize_detail(detail):
    """Compact JSON, rejecting payloads at or above the UI's 64 KiB limit."""
    serialized = json.dumps(detail, separators=(",", ":"), ensure_ascii=False)
    size = len(serialized.encode("utf-8"))
    if size >= DETAIL_MAX_BYTES:
        raise ValueError(f"Forecast_10Day_JSON is {size} bytes; limit is below {DETAIL_MAX_BYTES}")
    return serialized


def publish_forecast_payloads(payloads, put_state=oh_put_state):
    """Publish both legacy items before attempting the additive detail item."""
    legacy_hourly, legacy_daily, detail = payloads
    put_state("Forecast_Hourly_JSON", json.dumps(legacy_hourly))
    put_state("Forecast_Daily_JSON", json.dumps(legacy_daily))
    try:
        put_state("Forecast_10Day_JSON", serialize_detail(detail))
    except Exception as error:
        print(f"Forecast_10Day_JSON publish failed after legacy updates: {error}", file=sys.stderr)
        raise


def align_pv_days(pv_days, stored_date, today):
    """Realign the stored per-day PV list to today's forecast days.

    pv_days is computed by the 06:40 run with index 0 = that day; the 2-hourly
    json refresh between 00:00 and 06:40 would otherwise pair yesterday's list
    day-misaligned against today's daily forecast. stored_date None = legacy
    state written before pv_days_date existed: pass through unchanged
    (pre-upgrade behavior; the next morning run stamps the date).
    """
    if not pv_days:
        return None
    if stored_date is None:
        return list(pv_days)
    try:
        offset = (today - date.fromisoformat(str(stored_date))).days
    except ValueError:
        return None
    if offset == 0:
        return list(pv_days)
    if 0 < offset < len(pv_days):
        return list(pv_days)[offset:]
    return None   # future-dated or entirely stale: unusable


def build_json_items(snapshot=None, pv_per_day=None, now=None, put_state=None,
                     temperature_adjustment=None, hourly_model=None):
    """Materialize legacy JSON items plus additive ten-day detail from one fetch."""
    now_local = now or datetime.now(MOUNTAIN)
    if now_local.tzinfo is None:
        now_local = now_local.replace(tzinfo=MOUNTAIN)
    if snapshot is None:
        snapshot = fetch_forecast()
    state = None
    if (pv_per_day is None or temperature_adjustment is None
            or hourly_model is None):
        try:
            state = load_state()
        except Exception:
            state = {}
    if pv_per_day is None:   # standalone JSON refresh: reuse the morning's PV estimates
        pv_per_day = align_pv_days(
            state.get("pv_days"), state.get("pv_days_date"),
            now_local.astimezone(MOUNTAIN).date(),
        )
    if temperature_adjustment is None:
        temperature_adjustment = temperature_adjustment_from_state(state)
    if hourly_model is None:
        hourly_model = state.get("hourly_temp_model")
    payloads = build_forecast_payloads(
        snapshot, pv_per_day, now_local,
        temperature_adjustment=temperature_adjustment,
        hourly_model=hourly_model,
    )
    publish_forecast_payloads(payloads, put_state=put_state or oh_put_state)
    return payloads


def main():
    st = load_state()
    now = datetime.now()
    today = date.today()
    log = []
    put_failed = []

    def put(item, value):
        safe_put(item, value, put_failed)

    hourly_scored = score_hourly_targets(st, now)
    save_state(st)  # commit consumed/pruned evidence before later fallible work
    if hourly_scored:
        log.append(f"hourly-temp scored: {hourly_scored} raw targets")

    # ---- Phase 1: score yesterday, per quantity — a quantity whose series
    # had no data on an earlier run today may still score on a re-run,
    # without double-appending the ones that already scored ----
    ykey = (today - timedelta(days=1)).isoformat()
    yp = st["predictions"].get(ykey)
    rain_actual, hi_actual, lo_actual = measured_day_weather(today - timedelta(days=1))
    if yp:
        if should_score(st, ykey, "pv"):
            pv_pts = series("MPPT60_EnergyFromPV_Today", *local_day_window_utc(today - timedelta(days=1)))
            pv_actual = max((v for _, v in pv_pts), default=None)
            if pv_actual is not None and yp.get("pv") is not None:
                if pv_actual < 1e-9:
                    log.append(f"PV scoring skipped: measured {pv_actual:.2f} kWh (zero-production day, no %-error defined)")
                    mark_scored(st, ykey, "pv")
                else:
                    err = (yp["pv"] - pv_actual) / pv_actual * 100
                    st["pv_errors"] = (st["pv_errors"] + [abs(err)])[-7:]
                    put("Forecast_PV_Error_7d", round(sum(st["pv_errors"]) / len(st["pv_errors"]), 1))
                    log.append(f"PV scored: pred {yp['pv']:.2f} vs actual {pv_actual:.2f} kWh (err {err:+.0f}%)")
                    # ---- Phase 2: calibrate ----
                    demand_y = yp.get("demand")
                    radsum_y = yp.get("radsum")
                    if demand_y and radsum_y:
                        if pv_actual < 0.9 * demand_y and radsum_y > 0.5:   # resource-limited day
                            k_imp = pv_actual / radsum_y
                            st["k_res"] = clamp(st["k_res"] * (1 - ALPHA) + k_imp * ALPHA, *K_RES_BOUNDS)
                            log.append(f"calibrated k_res -> {st['k_res']:.3f} (resource-limited day)")
                        else:                                               # demand-limited day
                            deficit = yp.get("deficit_kwh", 0)
                            d_imp = pv_actual - deficit
                            st["d_direct"] = clamp(st["d_direct"] * (1 - ALPHA) + d_imp * ALPHA, *D_DIRECT_BOUNDS)
                            log.append(f"calibrated d_direct -> {st['d_direct']:.2f} (demand-limited day)")
                    mark_scored(st, ykey, "pv")
        if should_score(st, ykey, "trough"):
            tr_actual = measured_trough(today)
            if tr_actual is not None and yp.get("trough") is not None:
                terr = yp["trough"] - tr_actual
                st["trough_errors"] = (st["trough_errors"] + [abs(terr)])[-7:]
                put("Forecast_Trough_Error_7d", round(sum(st["trough_errors"]) / len(st["trough_errors"]), 1))
                log.append(f"trough scored: pred {yp['trough']:.0f} vs actual {tr_actual:.0f} (err {terr:+.1f} pts)")
                mark_scored(st, ykey, "trough")

        # ---- Phase 1b: forecast-vs-measured divergence (goal: learn where
        # Open-Meteo diverges from THIS site and adjust over time) ----
        if should_score(st, ykey, "precip") and rain_actual is not None and yp.get("precip_in") is not None:
            perr = yp["precip_in"] - rain_actual
            st["precip_errors"] = (st.get("precip_errors", []) + [abs(perr)])[-7:]
            put("Forecast_Precip_Error_7d", round(sum(st["precip_errors"]) / len(st["precip_errors"]), 2))
            log.append(f"precip scored: pred {yp['precip_in']:.2f} vs actual {rain_actual:.2f} in (err {perr:+.2f})")
            mark_scored(st, ykey, "precip")
        kalman = st.setdefault("kalman", kalman_seed())
        if should_score(st, ykey, "hi") and hi_actual is not None and yp.get("hi") is not None:
            herr = yp["hi"] - hi_actual   # raw-forecast error: the filter learns truth
            st["temp_hi_errors"] = (st.get("temp_hi_errors", []) + [herr])[-7:]   # signed: feeds bias
            put("Forecast_TempHigh_Error_7d", round(sum(abs(e) for e in st["temp_hi_errors"]) / len(st["temp_hi_errors"]), 1))
            put("Forecast_TempHigh_Bias_7d", round(sum(st["temp_hi_errors"]) / len(st["temp_hi_errors"]), 1))
            b = kalman_update(kalman, "hi", herr)
            log.append(f"temp-hi scored: pred {yp['hi']:.0f} vs actual {hi_actual:.0f} (err {herr:+.1f}F, kalman bias {b:+.2f})")
            mark_scored(st, ykey, "hi")
        if should_score(st, ykey, "lo") and lo_actual is not None and yp.get("lo") is not None:
            lerr = yp["lo"] - lo_actual
            st["temp_lo_errors"] = (st.get("temp_lo_errors", []) + [abs(lerr)])[-7:]
            put("Forecast_TempLow_Error_7d", round(sum(st["temp_lo_errors"]) / len(st["temp_lo_errors"]), 1))
            b = kalman_update(kalman, "lo", lerr)
            log.append(f"temp-lo scored: pred {yp['lo']:.0f} vs actual {lo_actual:.0f} (err {lerr:+.1f}F, kalman bias {b:+.2f})")
            mark_scored(st, ykey, "lo")

    # ---- Phase 1c: day-3 horizon skill (how trustworthy is 3-day planning) ----
    # Consume-on-success only: a field is popped from the record when it was
    # actually scored, so a missing actual (e.g. empty rain series) leaves the
    # day-3 record intact for a later same-day re-run instead of destroying it.
    horizon = st.setdefault("horizon", {})
    h3 = horizon.get(ykey)
    if h3:
        if hi_actual is not None and h3.get("hi") is not None:
            e3 = h3.pop("hi") - hi_actual
            st["day3_hi_errors"] = (st.get("day3_hi_errors", []) + [abs(e3)])[-7:]
            put("Forecast_Day3_High_Error_7d", round(sum(st["day3_hi_errors"]) / len(st["day3_hi_errors"]), 1))
            log.append(f"day3-hi scored: pred {e3 + hi_actual:.0f} vs actual {hi_actual:.0f} (err {e3:+.1f}F)")
        if rain_actual is not None and h3.get("precip_in") is not None:
            e3p = h3.pop("precip_in") - rain_actual
            st["day3_precip_errors"] = (st.get("day3_precip_errors", []) + [abs(e3p)])[-7:]
            put("Forecast_Day3_Precip_Error_7d", round(sum(st["day3_precip_errors"]) / len(st["day3_precip_errors"]), 2))
            log.append(f"day3-precip scored: pred {e3p + rain_actual:.2f} vs actual {rain_actual:.2f} in (err {e3p:+.2f})")
        if h3.get("hi") is None and h3.get("precip_in") is None:
            horizon.pop(ykey, None)
    for stale_key in [k for k in horizon if k < (today - timedelta(days=7)).isoformat()]:
        horizon.pop(stale_key, None)

    # ---- Phase 3: fetch forecast, predict today ----
    snapshot = fetch_forecast()
    targets = st.setdefault("hourly_temp_targets", {})
    for key, record in capture_next_day_hourly(snapshot, now).items():
        targets.setdefault(key, record)
    _bound_hourly_targets(st)
    save_state(st)  # preserve the first consistent capture before later work
    om = snapshot["daily"]
    highs, lows = om["temperature_2m_max"], om["temperature_2m_min"]
    radsum_kwh = om["shortwave_radiation_sum"][0] / 3.6   # MJ/m² -> kWh/m²
    precip_prob = om["precipitation_probability_max"]
    precip_sum = om.get("precipitation_sum", [])
    cloud_mean = om.get("cloud_cover_mean", [None] * len(highs))

    dawn_trough = measured_trough(today)
    soc_now = None
    try:
        soc_now = float(oh_get("/items/BMS_SOC")["state"])
    except Exception:
        pass
    trough_ref = dawn_trough if dawn_trough is not None else (soc_now or 60)

    deficit_kwh = (100 - trough_ref) / 100 * BANK_KWH / ETA_RT
    demand = st["d_direct"] + deficit_kwh
    resource = st["k_res"] * radsum_kwh
    pv_pred = round(min(resource, demand), 2)
    curtail = round(clamp((resource - demand) / 1.0, 0, 8) * 2) / 2 if resource > demand else 0.0

    # tonight's trough: dusk SoC estimate minus the MEASURED typical overnight
    # drop (trailing 3 nights of dusk->trough from persistence — the real
    # discharge window is ~14 h, dusk to charge crossover, which a fixed
    # 20:30-06:00 load integral underestimated badly: modeled 32 pts vs
    # observed 44-50 on the first attempt 2026-07-17)
    # Full 400 Ah bank (2026-07-19): shallow troughs (>=90) are the normal
    # signal now, not cutover artifacts — sample every measured night and
    # floor each drop at 1 pt. Fallback 12 ≈ the old 100 Ah-era 47-pt drop
    # scaled by the 4x capacity increase.
    drops = []
    for back in range(1, 5):
        night = today - timedelta(days=back - 1)
        if night < date(2026, 7, 19):       # first full-bank overnight measurement
            break
        tr = measured_trough(night)
        if tr is not None and 12 <= tr <= 99:
            drops.append(max(99 - tr, 1.0))
        if len(drops) == 3:
            break
    drop_pct = (sum(drops) / len(drops)) if drops else 12.0
    dusk_soc = 99 if resource >= demand - 0.3 else clamp(trough_ref + (pv_pred - st["d_direct"]) / BANK_KWH * 100 * ETA_RT, 12, 99)
    if cloud_mean[1] is not None and cloud_mean[1] > 70:
        drop_pct += 2   # cloudy tomorrow morning -> later charge crossover
    trough_pred = round(clamp(dusk_soc - drop_pct, 12, 99))

    # thermal advisory (thresholds from 45-day indoor/outdoor analysis).
    # ML v3a: advisory decisions and the Tomorrow items use Kalman
    # bias-corrected temps (corrected = raw - learned bias); scoring and the
    # predictions store keep RAW forecasts so the filters keep learning truth.
    kalman = st.setdefault("kalman", kalman_seed())
    b_hi, b_lo = kalman["hi"]["b"], kalman["lo"]["b"]
    put("Forecast_HighCorrection_F", round(-b_hi, 1))
    put("Forecast_LowCorrection_F", round(-b_lo, 1))
    t_high = highs[1] - b_hi
    streak3 = sum(highs[1:4]) / 3 - b_hi
    if t_high >= 95 or streak3 >= 92:
        advisory = f"close_up_tomorrow|Close up tomorrow — {t_high:.0f}° forecast" + (f", {streak3:.0f}° 3-day streak" if streak3 >= 92 else "")
    elif t_high >= 90:
        advisory = f"vent_tonight|Vent tonight — {t_high:.0f}° tomorrow, pre-cool the mass"
    else:
        advisory = "none|No thermal action needed"

    for item, val in [("Predicted_PV_Today_kWh", pv_pred), ("Predicted_Curtailment_Hours", curtail),
                      ("Predicted_SoC_Trough_Tomorrow", trough_pred), ("Thermal_Advisory", advisory),
                      ("Forecast_Tomorrow_High", round(highs[1] - b_hi, 1)), ("Forecast_Tomorrow_Low", round(lows[1] - b_lo, 1)),
                      ("Forecast_Tomorrow_PrecipProb", precip_prob[1] if precip_prob[1] is not None else 0)]:
        put(item, val)

    st["predictions"][today.isoformat()] = {
        "pv": pv_pred, "trough": trough_pred, "curtail": curtail, "advisory": advisory.split("|")[0],
        "radsum": radsum_kwh, "demand": round(demand, 2), "deficit_kwh": round(deficit_kwh, 2),
        "k_res": round(st["k_res"], 3), "d_direct": round(st["d_direct"], 2),
        "hi": highs[0], "lo": lows[0],
        "precip_in": (precip_sum[0] if precip_sum and precip_sum[0] is not None else 0)}
    st["predictions"] = {k: v for k, v in sorted(st["predictions"].items())[-30:]}
    # Day+3 horizon record, scored when that day's actuals exist (Phase 1c).
    if len(highs) > 3:
        st.setdefault("horizon", {})[(today + timedelta(days=3)).isoformat()] = {
            "hi": highs[3],
            "precip_in": (precip_sum[3] if len(precip_sum) > 3 else None),
        }

    # DM policy: deep-cycling warning only, once per day
    if trough_pred < TROUGH_DM_THRESHOLD and st["dm_sent"].get(today.isoformat()) != True:
        try:
            out = subprocess.run([NOTIFY, f"🔋 Forecast: tonight's SoC trough predicted at {trough_pred}% "
                                  f"(below {TROUGH_DM_THRESHOLD}%). Cloudy day ahead ({radsum_kwh:.1f} kWh/m²) — "
                                  "consider deferring heavy loads."], capture_output=True, text=True, timeout=60)
            if "DM sent" in (out.stdout + out.stderr):
                st["dm_sent"] = {today.isoformat(): True}
        except Exception:
            pass

    # per-day PV estimates for the 7-day view (typical demand cap ~6.9 kWh)
    try:
        pv_days = [round(min(st["k_res"] * (r or 0) / 3.6, 6.9), 1) for r in om["shortwave_radiation_sum"]]
        st["pv_days"] = pv_days
        st["pv_days_date"] = today.isoformat()   # lets the 2-hourly json refresh realign after midnight
        build_json_items(
            snapshot=snapshot,
            pv_per_day=pv_days,
            now=now,
            put_state=put,
            temperature_adjustment={
                "highCorrectionF": -b_hi,
                "lowCorrectionF": -b_lo,
            },
            hourly_model=st.get("hourly_temp_model"),
        )
    except Exception as e:
        log.append(f"json build failed: {e}")

    save_state(st)
    if put_failed:
        log.append("PUT FAILED: " + ",".join(put_failed))
    line = (f"{now.isoformat(timespec='seconds')} pv={pv_pred} curtail={curtail} trough={trough_pred} "
            f"adv={advisory.split('|')[0]} k={st['k_res']:.3f} D={st['d_direct']:.2f} | " + "; ".join(log or ["first run, nothing to score"]))
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(os.path.join(STATE_DIR, "log"), "a") as f:
        f.write(line + "\n")
    print(line)


if __name__ == "__main__":
    load_site_settings()
    if len(sys.argv) > 1 and sys.argv[1] == "json":
        build_json_items()
        print(datetime.now().isoformat(timespec="seconds") + " json refresh")
    else:
        main()
