#!/usr/bin/env python3
"""Backfill forecast-vs-measured training data for the Earthship ML roadmap.

Read-only everywhere: pulls archived Open-Meteo forecasts (Historical
Forecast API for issued values; Previous Runs API for day-3-lead values),
aggregates measured dailies from openHAB persistence, and writes a paired
dataset + data-quality report. Nothing is posted to openHAB.

Outputs (in ~/.local/state/forecast-intel/backfill/):
  dataset.csv   one row per local day, forecast + measured + lead-3 columns
  report.txt    per-column coverage, temp/radiation bias snapshot

Measured reconstruction notes:
- rain_in: daily diff of the lifetime accumulator RainFallTotal (negative
  diffs = counter reset -> clamped to the day's closing value, flagged).
- rad_kwh_m2: trapezoidal integral of the pyranometer (W/m2 -> kWh/m2/day).
- pv_kwh / trough: post-cutover regime only; included where data exists.
"""
import csv
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from forecast_intel import series, LAT, LON  # reuse auth'd persistence reader

OUT_DIR = os.path.expanduser("~/.local/state/forecast-intel/backfill")
START = date(2025, 7, 20)
END = date.today() - timedelta(days=1)
UTC_OFF = timedelta(hours=6)  # coarse MDT windowing, matches forecast_intel

TEMP_ITEM = "AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature"
RAD_ITEM = "AmbientWeatherWS2902A_SolarRadiation"
RAIN_TOTAL_ITEM = "AmbientWeatherWS2902A_RainFallTotal"
PV_ITEM = "MPPT60_EnergyFromPV_Today"
SOC_ITEM = "BMS_SOC"

HIST_URL = (
    "https://historical-forecast-api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
    "shortwave_radiation_sum,cloud_cover_mean"
    "&temperature_unit=fahrenheit&precipitation_unit=inch"
    "&timezone=America%2FDenver&start_date={start}&end_date={end}"
)
# Previous Runs API: hourly variables with _previous_day3 suffix; aggregated
# locally to daily max/min/sum for the lead-3 columns.
PREV_URL = (
    "https://previous-runs-api.open-meteo.com/v1/forecast"
    f"?latitude={LAT}&longitude={LON}"
    "&hourly=temperature_2m_previous_day3,precipitation_previous_day3"
    "&temperature_unit=fahrenheit&precipitation_unit=inch"
    "&timezone=America%2FDenver&start_date={start}&end_date={end}"
)


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def date_chunks(start, end, days):
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=days - 1), end)
        yield cur, stop
        cur = stop + timedelta(days=1)


def fetch_issued():
    rows = {}
    for c0, c1 in date_chunks(START, END, 92):
        data = fetch_json(HIST_URL.format(start=c0.isoformat(), end=c1.isoformat()))
        daily = data["daily"]
        for i, day in enumerate(daily["time"]):
            rows[day] = {
                "fc_hi": daily["temperature_2m_max"][i],
                "fc_lo": daily["temperature_2m_min"][i],
                "fc_precip_in": daily["precipitation_sum"][i],
                "fc_rad_kwh_m2": (daily["shortwave_radiation_sum"][i] / 3.6
                                  if daily["shortwave_radiation_sum"][i] is not None else None),
                "fc_cloud_pct": daily["cloud_cover_mean"][i],
            }
    return rows


def fetch_lead3():
    rows = {}
    for c0, c1 in date_chunks(START, END, 92):
        data = fetch_json(PREV_URL.format(start=c0.isoformat(), end=c1.isoformat()))
        hourly = data["hourly"]
        per_day = {}
        for i, ts in enumerate(hourly["time"]):
            day = ts[:10]
            t = hourly["temperature_2m_previous_day3"][i]
            p = hourly["precipitation_previous_day3"][i]
            bucket = per_day.setdefault(day, {"t": [], "p": []})
            if t is not None:
                bucket["t"].append(t)
            if p is not None:
                bucket["p"].append(p)
        for day, bucket in per_day.items():
            rows[day] = {
                "fc3_hi": max(bucket["t"]) if bucket["t"] else None,
                "fc3_precip_in": round(sum(bucket["p"]), 3) if bucket["p"] else None,
            }
    return rows


def day_window(day):
    d0 = datetime.combine(day, datetime.min.time())
    return d0 + UTC_OFF, d0 + timedelta(hours=24) + UTC_OFF


def month_series(item, start, end):
    """One persistence GET per ~31-day chunk; returns [(datetime, value)]."""
    points = []
    for c0, c1 in date_chunks(start, end, 31):
        w_start, _ = day_window(c0)
        _, w_end = day_window(c1)
        points.extend(series(item, w_start, w_end))
    return points


def bucket_daily(points):
    days = {}
    for ts, value in points:
        local = ts - UTC_OFF if ts.tzinfo is None else ts.astimezone(None) - UTC_OFF
        days.setdefault(local.date().isoformat(), []).append((ts, value))
    return days


def trapezoid_kwh(points):
    """Integrate (datetime, W/m2) -> kWh/m2."""
    if len(points) < 2:
        return None
    total = 0.0
    for (t0, v0), (t1, v1) in zip(points, points[1:]):
        dt_h = (t1 - t0).total_seconds() / 3600
        if 0 < dt_h <= 3:  # bridge small gaps only
            total += (v0 + v1) / 2 * dt_h
    return round(total / 1000, 2)


def measured_dailies():
    out = {}
    print("pulling persistence (chunked, this takes a minute)...", flush=True)
    temp_days = bucket_daily(month_series(TEMP_ITEM, START, END))
    rad_days = bucket_daily(month_series(RAD_ITEM, START, END))
    rain_days = bucket_daily(month_series(RAIN_TOTAL_ITEM, START, END))
    pv_days = bucket_daily(month_series(PV_ITEM, START, END))
    soc_days = bucket_daily(month_series(SOC_ITEM, START, END))

    rain_last = {d: pts[-1][1] for d, pts in sorted(rain_days.items())}
    prev_total = None
    rain_resets = []
    day = START
    while day <= END:
        key = day.isoformat()
        row = {}
        temps = [v for _, v in temp_days.get(key, [])]
        row["m_hi"] = round(max(temps), 1) if temps else None
        row["m_lo"] = round(min(temps), 1) if temps else None
        rads = sorted(rad_days.get(key, []))
        row["m_rad_kwh_m2"] = trapezoid_kwh(rads)
        total = rain_last.get(key)
        if total is not None and prev_total is not None:
            diff = round(total - prev_total, 3)
            if diff < -0.005:
                rain_resets.append(key)
                diff = max(total, 0.0)
            row["m_rain_in"] = max(diff, 0.0)
        else:
            row["m_rain_in"] = None
        if total is not None:
            prev_total = total
        pvs = [v for _, v in pv_days.get(key, [])]
        row["m_pv_kwh"] = round(max(pvs), 2) if pvs else None
        socs = [v for _, v in soc_days.get(key, [])]
        row["m_trough_soc"] = round(min(socs), 1) if socs else None
        out[key] = row
        day += timedelta(days=1)
    return out, rain_resets


def coverage(rows, col):
    have = sum(1 for r in rows if r.get(col) is not None)
    return have, round(have / len(rows) * 100)


def mean(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 2) if values else None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    issued = fetch_issued()
    print(f"issued forecasts: {len(issued)} days", flush=True)
    lead3 = fetch_lead3()
    print(f"lead-3 forecasts: {len(lead3)} days", flush=True)
    measured, rain_resets = measured_dailies()

    rows = []
    day = START
    while day <= END:
        key = day.isoformat()
        row = {"date": key}
        row.update(issued.get(key, {}))
        row.update(lead3.get(key, {}))
        row.update(measured.get(key, {}))
        rows.append(row)
        day += timedelta(days=1)

    cols = ["date", "fc_hi", "fc_lo", "fc_precip_in", "fc_rad_kwh_m2", "fc_cloud_pct",
            "fc3_hi", "fc3_precip_in", "m_hi", "m_lo", "m_rain_in", "m_rad_kwh_m2",
            "m_pv_kwh", "m_trough_soc"]
    with open(os.path.join(OUT_DIR, "dataset.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)

    paired_hi = [(r["fc_hi"], r["m_hi"]) for r in rows
                 if r.get("fc_hi") is not None and r.get("m_hi") is not None]
    paired_rad = [(r["fc_rad_kwh_m2"], r["m_rad_kwh_m2"]) for r in rows
                  if r.get("fc_rad_kwh_m2") is not None and r.get("m_rad_kwh_m2") is not None]
    paired_hi3 = [(r["fc3_hi"], r["m_hi"]) for r in rows
                  if r.get("fc3_hi") is not None and r.get("m_hi") is not None]
    report = [f"Backfill {START} .. {END}  ({len(rows)} days)", ""]
    for col in cols[1:]:
        have, pct = coverage(rows, col)
        report.append(f"{col:16} {have:4} days ({pct}%)")
    report += [
        "",
        f"paired hi (issued): {len(paired_hi)}  mean bias fc-m: "
        f"{mean([f - m for f, m in paired_hi])} F  mean |err|: {mean([abs(f - m) for f, m in paired_hi])} F",
        f"paired hi (lead-3): {len(paired_hi3)}  mean bias fc-m: "
        f"{mean([f - m for f, m in paired_hi3])} F  mean |err|: {mean([abs(f - m) for f, m in paired_hi3])} F",
        f"paired radiation:   {len(paired_rad)}  mean bias fc-m: "
        f"{mean([f - m for f, m in paired_rad])} kWh/m2  mean |err|: {mean([abs(f - m) for f, m in paired_rad])} kWh/m2",
        f"rain counter resets clamped: {rain_resets or 'none'}",
    ]
    text = "\n".join(report)
    with open(os.path.join(OUT_DIR, "report.txt"), "w") as f:
        f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
