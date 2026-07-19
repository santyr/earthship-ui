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
import json, os, subprocess, sys, urllib.request
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo

BASE = "http://127.0.0.1:8080/rest"
ENV_FILE = os.path.expanduser("~/.config/hex/openhab.env")
NOTIFY = "/etc/openhab/scripts/nostr_notify.sh"
STATE_DIR = os.path.expanduser("~/.local/state/forecast-intel")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
LAT, LON = 38.3739919, -105.7744931
BANK_KWH, RESERVE_SOC, ETA_RT = 20.48, 10, 0.95  # full 4P 400Ah bank (2026-07-19; was 5.12 single-module interim)
K_RES_BOUNDS, D_DIRECT_BOUNDS, ALPHA = (0.5, 1.3), (2.5, 6.0), 0.2
TROUGH_DM_THRESHOLD = 30  # full-bank policy (was 42 on the single 100 Ah bank)
OM_URL = (f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
          "&hourly=temperature_2m,precipitation_probability,precipitation,"
          "shortwave_radiation,wind_speed_10m,weather_code"
          "&daily=temperature_2m_max,temperature_2m_min,shortwave_radiation_sum,"
          "precipitation_probability_max,precipitation_sum,cloud_cover_mean,weather_code"
          "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
          "&timezone=America%2FDenver&forecast_days=10")
MOUNTAIN = ZoneInfo("America/Denver")
DETAIL_MAX_BYTES = 64 * 1024
_TOKEN = None


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


def series(item, start, end):
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    d = oh_get(f"/persistence/items/{item}?starttime={start.strftime(fmt)}&endtime={end.strftime(fmt)}")
    return [(datetime.fromtimestamp(p["time"] / 1000), float(str(p["state"]).split()[0]))
            for p in d.get("data", [])]


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"k_res": 1.0, "d_direct": 4.0, "predictions": {},
                "pv_errors": [], "trough_errors": [], "dm_sent": {}}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


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
    try:
        import csv as _csv
        rows = list(_csv.DictReader(open(BACKFILL_CSV)))[-60:]
        for key, fc_col, m_col in (("hi", "fc_hi", "m_hi"), ("lo", "fc_lo", "m_lo")):
            errs = []
            for row in rows:
                try:
                    errs.append(float(row[fc_col]) - float(row[m_col]))
                except (KeyError, TypeError, ValueError):
                    continue
            if errs:
                seeds[key] = round(sum(errs) / len(errs), 2)
    except OSError:
        pass
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
    start = datetime.combine(d0 - timedelta(days=1), datetime.min.time()).replace(hour=20)
    end = datetime.combine(d0, datetime.min.time()).replace(hour=11)
    utc_off = timedelta(hours=6)  # MDT; coarse is fine for windowing
    pts = series("BMS_SOC", start + utc_off, end + utc_off)
    return min((v for _, v in pts), default=None)


OUTDOOR_TEMP_ITEM = "AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature"
RAIN_DAY_ITEM = "AmbientWeatherWS2902A_RainFallDay"


def measured_day_weather(day):
    """(rain_total_in, temp_hi_f, temp_lo_f) for one local calendar day.

    Rain uses max(RainFallDay) — the gauge's daily accumulator resets at
    midnight, so the day's maximum is its total.
    """
    utc_off = timedelta(hours=6)
    d0 = datetime.combine(day, datetime.min.time())
    window = (d0 + utc_off, d0 + timedelta(hours=24) + utc_off)
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


def build_forecast_payloads(snapshot, pv_per_day, now):
    """Return (legacy_hourly, legacy_daily, detail_v1) from one provider snapshot."""
    hourly = snapshot["hourly"]
    daily = snapshot["daily"]
    if now.tzinfo is None:
        now_local = now.replace(tzinfo=MOUNTAIN)
    else:
        now_local = now.astimezone(MOUNTAIN)
    pv_days = list(pv_per_day or [])

    now_iso = now_local.strftime("%Y-%m-%dT%H:00")
    try:
        start = hourly["time"].index(now_iso)
    except ValueError:
        start = 0
    legacy_hourly = []
    for index in range(start, min(start + 14, len(hourly["time"]))):
        legacy_hourly.append({
            "h": _hour_label(hourly["time"][index]),
            "t": _rounded(_series_value(hourly, "temperature_2m", index)),
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
            "hi": _rounded(_series_value(daily, "temperature_2m_max", index)),
            "lo": _rounded(_series_value(daily, "temperature_2m_min", index)),
            "p": _series_value(daily, "precipitation_probability_max", index) or 0,
            "a": round(_series_value(daily, "precipitation_sum", index) or 0, 2),
            "w": _series_value(daily, "weather_code", index),
            "pv": pv_days[index] if index < len(pv_days) else None,
        })

    hours_by_date = {day_string: [] for day_string in daily["time"][:day_count]}
    previous = None
    for index, local_timestamp in enumerate(hourly["time"]):
        aware = _offset_timestamp(local_timestamp, previous)
        previous = aware
        day_string = local_timestamp[:10]
        if day_string not in hours_by_date:
            continue
        hours_by_date[day_string].append({
            "at": aware.isoformat(timespec="seconds"),
            "tempF": _series_value(hourly, "temperature_2m", index),
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
                "highF": _series_value(daily, "temperature_2m_max", index),
                "lowF": _series_value(daily, "temperature_2m_min", index),
                "precipPct": _series_value(daily, "precipitation_probability_max", index),
                "precipSumIn": _series_value(daily, "precipitation_sum", index),
                "weatherCode": _series_value(daily, "weather_code", index),
                "pvKwh": pv_days[index] if index < len(pv_days) else None,
            },
            "hours": hours_by_date[day_string],
        })

    detail = {
        "version": 1,
        "generatedAt": now_local.isoformat(timespec="seconds"),
        "timezone": "America/Denver",
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


def build_json_items(snapshot=None, pv_per_day=None, now=None, put_state=None):
    """Materialize legacy JSON items plus additive ten-day detail from one fetch."""
    if snapshot is None:
        with urllib.request.urlopen(OM_URL, timeout=20) as response:
            snapshot = json.load(response)
    if pv_per_day is None:   # standalone JSON refresh: reuse the morning's PV estimates
        try:
            pv_per_day = load_state().get("pv_days")
        except Exception:
            pv_per_day = None
    payloads = build_forecast_payloads(snapshot, pv_per_day, now or datetime.now(MOUNTAIN))
    publish_forecast_payloads(payloads, put_state=put_state or oh_put_state)
    return payloads


def main():
    st = load_state()
    now = datetime.now()
    today = date.today()
    log = []

    # ---- Phase 1: score yesterday ----
    ykey = (today - timedelta(days=1)).isoformat()
    yp = st["predictions"].get(ykey)
    rain_actual, hi_actual, lo_actual = measured_day_weather(today - timedelta(days=1))
    if yp:
        utc_off = timedelta(hours=6)
        y0 = datetime.combine(today - timedelta(days=1), datetime.min.time())
        pv_pts = series("MPPT60_EnergyFromPV_Today", y0 + utc_off, y0 + timedelta(hours=24) + utc_off)
        pv_actual = max((v for _, v in pv_pts), default=None)
        if pv_actual and yp.get("pv"):
            err = (yp["pv"] - pv_actual) / pv_actual * 100
            st["pv_errors"] = (st["pv_errors"] + [abs(err)])[-7:]
            oh_put_state("Forecast_PV_Error_7d", round(sum(st["pv_errors"]) / len(st["pv_errors"]), 1))
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
        tr_actual = measured_trough(today)
        if tr_actual is not None and yp.get("trough") is not None:
            terr = yp["trough"] - tr_actual
            st["trough_errors"] = (st["trough_errors"] + [abs(terr)])[-7:]
            oh_put_state("Forecast_Trough_Error_7d", round(sum(st["trough_errors"]) / len(st["trough_errors"]), 1))
            log.append(f"trough scored: pred {yp['trough']:.0f} vs actual {tr_actual:.0f} (err {terr:+.1f} pts)")

        # ---- Phase 1b: forecast-vs-measured divergence (goal: learn where
        # Open-Meteo diverges from THIS site and adjust over time) ----
        if rain_actual is not None and yp.get("precip_in") is not None:
            perr = yp["precip_in"] - rain_actual
            st["precip_errors"] = (st.get("precip_errors", []) + [abs(perr)])[-7:]
            oh_put_state("Forecast_Precip_Error_7d", round(sum(st["precip_errors"]) / len(st["precip_errors"]), 2))
            log.append(f"precip scored: pred {yp['precip_in']:.2f} vs actual {rain_actual:.2f} in (err {perr:+.2f})")
        kalman = st.setdefault("kalman", kalman_seed())
        if hi_actual is not None and yp.get("hi") is not None:
            herr = yp["hi"] - hi_actual   # raw-forecast error: the filter learns truth
            st["temp_hi_errors"] = (st.get("temp_hi_errors", []) + [herr])[-7:]   # signed: feeds bias
            oh_put_state("Forecast_TempHigh_Error_7d", round(sum(abs(e) for e in st["temp_hi_errors"]) / len(st["temp_hi_errors"]), 1))
            oh_put_state("Forecast_TempHigh_Bias_7d", round(sum(st["temp_hi_errors"]) / len(st["temp_hi_errors"]), 1))
            b = kalman_update(kalman, "hi", herr)
            log.append(f"temp-hi scored: pred {yp['hi']:.0f} vs actual {hi_actual:.0f} (err {herr:+.1f}F, kalman bias {b:+.2f})")
        if lo_actual is not None and yp.get("lo") is not None:
            lerr = yp["lo"] - lo_actual
            st["temp_lo_errors"] = (st.get("temp_lo_errors", []) + [abs(lerr)])[-7:]
            oh_put_state("Forecast_TempLow_Error_7d", round(sum(st["temp_lo_errors"]) / len(st["temp_lo_errors"]), 1))
            b = kalman_update(kalman, "lo", lerr)
            log.append(f"temp-lo scored: pred {yp['lo']:.0f} vs actual {lo_actual:.0f} (err {lerr:+.1f}F, kalman bias {b:+.2f})")

    # ---- Phase 1c: day-3 horizon skill (how trustworthy is 3-day planning) ----
    horizon = st.setdefault("horizon", {})
    h3 = horizon.pop(ykey, None)
    if h3:
        if hi_actual is not None and h3.get("hi") is not None:
            e3 = h3["hi"] - hi_actual
            st["day3_hi_errors"] = (st.get("day3_hi_errors", []) + [abs(e3)])[-7:]
            oh_put_state("Forecast_Day3_High_Error_7d", round(sum(st["day3_hi_errors"]) / len(st["day3_hi_errors"]), 1))
            log.append(f"day3-hi scored: pred {h3['hi']:.0f} vs actual {hi_actual:.0f} (err {e3:+.1f}F)")
        if rain_actual is not None and h3.get("precip_in") is not None:
            e3p = h3["precip_in"] - rain_actual
            st["day3_precip_errors"] = (st.get("day3_precip_errors", []) + [abs(e3p)])[-7:]
            oh_put_state("Forecast_Day3_Precip_Error_7d", round(sum(st["day3_precip_errors"]) / len(st["day3_precip_errors"]), 2))
            log.append(f"day3-precip scored: pred {h3['precip_in']:.2f} vs actual {rain_actual:.2f} in (err {e3p:+.2f})")
    for stale_key in [k for k in horizon if k < (today - timedelta(days=7)).isoformat()]:
        horizon.pop(stale_key, None)

    # ---- Phase 3: fetch forecast, predict today ----
    with urllib.request.urlopen(OM_URL, timeout=20) as r:
        snapshot = json.load(r)
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
    oh_put_state("Forecast_HighCorrection_F", round(-b_hi, 1))
    oh_put_state("Forecast_LowCorrection_F", round(-b_lo, 1))
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
        oh_put_state(item, val)

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
        build_json_items(snapshot=snapshot, pv_per_day=pv_days, now=now)
    except Exception as e:
        log.append(f"json build failed: {e}")

    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(st, f, indent=1)
    line = (f"{now.isoformat(timespec='seconds')} pv={pv_pred} curtail={curtail} trough={trough_pred} "
            f"adv={advisory.split('|')[0]} k={st['k_res']:.3f} D={st['d_direct']:.2f} | " + "; ".join(log or ["first run, nothing to score"]))
    with open(os.path.join(STATE_DIR, "log"), "a") as f:
        f.write(line + "\n")
    print(line)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "json":
        build_json_items()
        print(datetime.now().isoformat(timespec="seconds") + " json refresh")
    else:
        main()
