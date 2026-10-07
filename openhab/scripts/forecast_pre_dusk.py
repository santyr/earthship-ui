#!/usr/bin/env python3
"""One date-bound pre-dusk SoC estimate; morning forecast/scoring stay unchanged.

The timer may check several times each afternoon. Only a fresh atomic BMS SoC
within 60–90 minutes of today's Astro sunset can publish one separate receipt.
No command, calibration update, or DM is sent by this worker.
"""

from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

from earthship_energy.bms_evidence import parse_evidence
from qualified_soc_forecast import current_valid_soc
from forecast_intel import STATE_FILE, oh_get, oh_put_state


ZONE = ZoneInfo('America/Denver')
RECEIPT_ITEM = 'Forecast_PreDusk_Trough_Receipt_JSON'
VALUE_ITEM = 'Predicted_SoC_Trough_PreDusk'
BASIS = 'atomic_soc_pre_dusk_v1'
MAX_STATE_BYTES = 256 * 1024


class Withheld(ValueError):
    """No valid estimate may be published from this input set."""


def _time(value):
    if not isinstance(value, str) or len(value) > 64:
        raise Withheld('missing or invalid timestamp')
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise Withheld('missing or invalid timestamp') from error
    if result.utcoffset() is None:
        raise Withheld('timestamp lacks offset')
    return result.astimezone(timezone.utc)


def load_morning_record(path, day):
    try:
        raw = Path(path).read_bytes()
        if len(raw) > MAX_STATE_BYTES:
            raise Withheld('morning state exceeds size bound')
        state = json.loads(raw)
        record = state['predictions'][day]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        raise Withheld('morning forecast record unavailable') from error
    if not isinstance(record, dict):
        raise Withheld('morning forecast record invalid')
    return record


def estimate(now, sunset_state, soc_raw, morning):
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise Withheld('aware issue clock required')
    now = now.astimezone(timezone.utc)
    day = now.astimezone(ZONE).date().isoformat()
    sunset = _time(sunset_state)
    if sunset.astimezone(ZONE).date().isoformat() != day:
        raise Withheld('sunset is not for today')
    minutes = (sunset - now).total_seconds() / 60
    if not 60 <= minutes < 90:
        raise Withheld('outside pre-dusk issue window')
    if not isinstance(morning, dict):
        raise Withheld('morning forecast record unavailable')
    morning_at = _time(morning.get('temperature_issued_at'))
    if morning_at.astimezone(ZONE).date().isoformat() != day or morning_at >= now:
        raise Withheld('morning forecast is not an earlier same-day issue')
    samples = morning.get('overnight_drop_samples_pct')
    sample_days = morning.get('overnight_drop_sample_days')
    drop = morning.get('overnight_drop_final_pct')
    if (not isinstance(samples, list) or len(samples) < 2 or len(samples) > 3
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   or not 0 <= value <= 50 for value in samples)
            or not isinstance(sample_days, list) or len(sample_days) != len(samples)
            or type(drop) not in (int, float) or not math.isfinite(drop)
            or not 1 <= drop <= 50):
        raise Withheld('qualified overnight-drop history unavailable')
    try:
        parsed_days = tuple(date.fromisoformat(value) for value in sample_days)
    except (TypeError, ValueError):
        raise Withheld('qualified overnight-drop history unavailable')
    prediction_day = now.astimezone(ZONE).date()
    if (
        len(set(parsed_days)) != len(parsed_days)
        or tuple(sorted(parsed_days, reverse=True)) != parsed_days
        or any(
            not prediction_day - timedelta(days=4) <= sample_day < prediction_day
            for sample_day in parsed_days
        )
    ):
        raise Withheld('qualified overnight-drop history unavailable')
    soc = current_valid_soc(soc_raw, now)
    if soc is None:
        raise Withheld('fresh atomic SoC unavailable')
    record = parse_evidence(soc_raw, now)
    if record is None or record.status != 'valid':
        raise Withheld('atomic SoC receipt invalid')
    # Match the UI's Math.round for a positive percentage, including .5 ties.
    trough = math.floor(max(12, min(99, soc - drop)) + 0.5)
    return {
        'version': 1, 'basis': BASIS, 'predictionDay': day,
        'issuedAt': now.isoformat(), 'sunsetAt': sunset.isoformat(),
        'morningIssuedAt': morning_at.isoformat(),
        'socRecordedAt': record.recorded_at.isoformat(),
        'socStreamEpoch': record.stream_epoch,
        'socEvidenceSha256': sha256(soc_raw.encode('utf-8')).hexdigest(),
        'socAtIssuePct': soc, 'overnightDropPct': round(drop, 3),
        'overnightTroughSocPct': trough,
    }


def already_issued(raw, day):
    try:
        value = json.loads(raw)
        return (isinstance(value, dict) and value.get('version') == 1
                and value.get('basis') == BASIS and value.get('predictionDay') == day
                and type(value.get('overnightTroughSocPct')) is int)
    except (TypeError, ValueError):
        return False


def run(now=None, *, get=oh_get, put=oh_put_state, state_path=STATE_FILE):
    injected_clock = now is not None
    now = datetime.now(timezone.utc) if not injected_clock else now
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise Withheld('aware issue clock required')
    day = now.astimezone(ZONE).date().isoformat()
    sunset = get('/items/Sun_Set_Start')['state']
    sunset_at = _time(sunset)
    minutes = (sunset_at - now).total_seconds() / 60
    if sunset_at.astimezone(ZONE).date().isoformat() != day or not 60 <= minutes < 90:
        return 'outside_window'
    if already_issued(get(f'/items/{RECEIPT_ITEM}')['state'], day):
        return 'already_issued'
    morning = load_morning_record(state_path, day)
    soc_raw = get('/items/BMS_SOC_Evidence_JSON')['state']
    # Recheck the clock after I/O. A receipt cannot be issued with an SoC that
    # expired during a slow read, nor outside the selected sunset window.
    issued_at = now if injected_clock else datetime.now(timezone.utc)
    receipt = estimate(issued_at, sunset, soc_raw, morning)
    put(VALUE_ITEM, receipt['overnightTroughSocPct'])
    put(RECEIPT_ITEM, json.dumps(receipt, separators=(',', ':')))
    return 'issued'


def main():
    try:
        status = run()
    except Withheld as error:
        print(f'pre-dusk trough withheld: {error}', file=sys.stderr)
        return 2
    except Exception:
        # Do not echo token-bearing HTTP or private-path diagnostics.
        print('pre-dusk trough unavailable: I/O failure', file=sys.stderr)
        return 2
    print(f'pre-dusk trough: {status}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
