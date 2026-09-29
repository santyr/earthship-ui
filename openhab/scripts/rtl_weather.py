#!/usr/bin/env python3
import subprocess
import json
import requests
import time
import logging
import math
from collections import defaultdict

# Optional project observer: failure never interrupts household station ingestion.
try:
    import importlib.util as _lg_import
    _lg_spec = _lg_import.spec_from_file_location('lightning_goats_weather', '/usr/local/lib/lightning-goats-weather/lightning_goats_weather.py')
    _lg_module = _lg_import.module_from_spec(_lg_spec)
    _lg_spec.loader.exec_module(_lg_module)
    _lg_record_packet = _lg_module.record_packet
except Exception:
    _lg_record_packet = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

FLASK_URL = "http://localhost:5000/weather"
WH65B_STATION_ID = 206  # our WS-2902 array (survey 2026-07-16)
HTTP_TIMEOUT = 3.0
MIN_SEND_INTERVAL_S = 1.5  # seconds between sends per sensor

session = requests.Session()
_last_sent = defaultdict(float)  # per-sensor rate limit

# Temporary operator-approved WH32B identity survey; expires even after restart.
_WH32B_ID_SURVEY_UNTIL = 1789173057  # 2026-09-12 00:30:57 UTC
_wh32b_survey_ids = set()


def _log_wh32b_id(data):
    if time.time() >= _WH32B_ID_SURVEY_UNTIL:
        return
    sid = data.get("id")
    if type(sid) is not int or not 0 <= sid <= 0xFFFFFFFF:
        return
    if sid in _wh32b_survey_ids or len(_wh32b_survey_ids) >= 16:
        return
    _wh32b_survey_ids.add(sid)
    logging.info("WH32B_ID_SURVEY id=%d", sid)


def _key(model, sid):
    return f"{model}:{sid if sid is not None else 'na'}"


def _should_send(model, sid):
    now = time.time()
    k = _key(model, sid)
    if now - _last_sent[k] >= MIN_SEND_INTERVAL_S:
        _last_sent[k] = now
        return True
    return False


def send_data_to_flask(data):
    """Send data to Flask using GET (as original script)."""
    try:
        response = session.get(FLASK_URL, params=data, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        logging.debug(f"Sent to Flask: {data}")
    except requests.RequestException as e:
        logging.error(f"Failed to send data: {e}")


def normalize_wh65b_packet(data):
    """Use this station's WH65B tip/wind factors for either decoder label.

    rtl_433 sometimes labels the same ID 206 WH65B frame as WH24. Its decoder
    then applies 0.3 instead of 0.254 mm per rain tip and 1.12 instead of
    0.51 for wind. Recover the integer tip count and reject ambiguous values;
    this function is called only after the station-ID filter.
    """
    model = data.get("model")
    if model not in ("Fineoffset-WH65B", "Fineoffset-WH24"):
        return None
    decoder_tip_mm = 0.3 if model == "Fineoffset-WH24" else 0.254
    try:
        decoded_mm = float(data["rain_mm"])
        wind_avg = float(data["wind_avg_m_s"])
        wind_max = float(data["wind_max_m_s"])
    except (TypeError, ValueError, OverflowError, KeyError):
        return None
    if (not all(math.isfinite(v) for v in (decoded_mm, wind_avg, wind_max))
            or decoded_mm < 0 or wind_avg < 0 or wind_max < 0):
        return None
    tips = round(decoded_mm / decoder_tip_mm)
    # rtl_433 JSON retains more precision than its display format; allow a
    # display-rounded 0.1-mm reading but never an ambiguous half-tip value.
    if not 0 <= tips <= 65535 or abs(decoded_mm - tips * decoder_tip_mm) > 0.06:
        return None
    wind_scale = 0.51 / 1.12 if model == "Fineoffset-WH24" else 1.0
    return tips * 0.254, wind_avg * wind_scale, wind_max * wind_scale


def main():
    # Note: Use -F json so we get the data, but we merged stderr to see errors
    rtl_433_command = [
        "rtl_433",
        "-Y", "autolevel",
        "-M", "utc",
        "-F", "json",
        "-f", "914980000",
        "-s", "250000"
    ]
    logging.info(f"Starting rtl_433: {' '.join(rtl_433_command)}")

    while True:
        process = None
        try:
            process = subprocess.Popen(
                rtl_433_command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Merges errors into the same stream we read
                text=True,
                bufsize=1
            )

            logging.info("rtl_433 running and listening...")

            assert process.stdout is not None
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue

                # IMPROVEMENT: Log error messages that aren't JSON
                if not line.startswith("{"):
                    logging.info(f"rtl_433 output: {line}")
                    continue

                try:
                    data = json.loads(line)
                    if _lg_record_packet is not None and isinstance(data, dict):
                        try:
                            _lg_record_packet('/var/lib/lightning-goats-weather/snapshot.db', data, WH65B_STATION_ID)
                        except Exception:
                            logging.warning('Lightning Goats weather observation unavailable')
                except json.JSONDecodeError:
                    logging.warning(f"Invalid JSON: {line}")
                    continue

                model = data.get("model")
                if not model:
                    continue

                # --- Outdoor WH65B/WH24 ---
                if model in ("Fineoffset-WH65B", "Fineoffset-WH24"):
                    # Station ID filter (2026-07-16): a neighbor WS-2902-family
                    # station in RF range was being merged in, flip-flopping the
                    # cumulative rain counter (97.16 <-> 114.76 in) and wiping
                    # the daily rain accumulator. Our array is id 206 (verified
                    # against lifetime rain total). NOTE: id changes on station
                    # battery replacement — re-survey with the ID log if data
                    # goes silent after a battery swap.
                    if data.get("id") != WH65B_STATION_ID:
                        logging.info(f"Ignoring foreign WH65B id={data.get('id')} (rain_mm={data.get('rain_mm')})")
                        continue
                    req = [
                        "temperature_C", "humidity", "wind_dir_deg",
                        "wind_avg_m_s", "wind_max_m_s",
                        "rain_mm", "light_lux", "uvi"
                    ]
                    if all(k in data for k in req):
                        normalized = normalize_wh65b_packet(data)
                        if normalized is None:
                            logging.warning("Rejecting ambiguous WH65B rain/wind units for id=%s model=%s",
                                            data["id"], model)
                            continue
                        rain_mm, wind_avg_m_s, wind_max_m_s = normalized
                        payload = {
                            "model": model,
                            "id": data["id"],
                            "tempf": round(data["temperature_C"] * 1.8 + 32, 2),
                            "humidity": round(float(data["humidity"]), 2),
                            "winddir": round(float(data["wind_dir_deg"])),
                            "windspeedmph": round(wind_avg_m_s * 2.23694, 2),
                            "windgustmph": round(wind_max_m_s * 2.23694, 2),
                            "totalrainin": rain_mm * 0.03937,
                            "solarradiation": round(min(data["light_lux"] / 126.7, 1200.0), 2),  # clamp to max ground-level irradiance
                            "uv": round(float(data["uvi"]), 2)
                        }
                        if "battery_ok" in data:
                            payload["battery_ok"] = data["battery_ok"]
                        sid = data.get("id")
                        if _should_send(model, sid):
                            send_data_to_flask(payload)
                    else:
                        logging.warning(f"Missing keys for {model}: {list(data.keys())}")

                # --- Indoor WH32B ---
                elif model == "Fineoffset-WH32B":
                    _log_wh32b_id(data)
                    req = ["temperature_C", "humidity", "id"]
                    if all(k in data for k in req):
                        sid = data["id"]
                        payload = {
                            "model": model,
                            "id": sid,
                            "tempinf": round(data["temperature_C"] * 1.8 + 32, 2),
                            "humidityin": round(float(data["humidity"]), 2)
                        }
                        if "pressure_hPa" in data:
                            payload["baromrelin"] = round(float(data["pressure_hPa"]) * 0.02953, 2)
                        if _should_send(model, sid):
                            send_data_to_flask(payload)
                    else:
                        logging.warning(f"Missing keys for WH32B: {list(data.keys())}")

                # --- Ambient WH31E ---
                elif model == "AmbientWeather-WH31E":
                    req = ["temperature_C", "humidity", "id"]
                    if all(k in data for k in req):
                        sid = data["id"]
                        payload = {
                            "model": model,
                            "id": sid,
                            "tempinf": round(data["temperature_C"] * 1.8 + 32, 2),
                            "humidityin": round(float(data["humidity"]), 2)
                        }
                        if "battery_ok" in data:
                            payload["battery_ok"] = data["battery_ok"]
                        if _should_send(model, sid):
                            send_data_to_flask(payload)
                    else:
                        logging.warning(f"Missing keys for WH31E: {list(data.keys())}")

                else:
                    logging.info(f"Unhandled model '{model}': {data}")

            # Once the loop exits, check why the process stopped
            rc = process.poll()
            if rc is not None and rc != 0:
                logging.error(f"rtl_433 exited with code {rc}")

        except FileNotFoundError:
            logging.error("rtl_433 not found in PATH. Please install it with 'sudo apt install rtl-433'")
            break
        except Exception as e:
            logging.exception(f"Error in main loop: {e}")
        finally:
            if process and process.poll() is None:
                logging.info("Terminating rtl_433...")
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    logging.warning("Killing rtl_433 (timeout)")
                    process.kill()

        logging.info("Restarting rtl_433 in 10 seconds...")
        time.sleep(10)


if __name__ == "__main__":
    main()
