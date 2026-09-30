#!/usr/bin/env python3
"""Read-only as-issued sunset-drop counterfactual; no fitted or live correction."""

import argparse
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'openhab/scripts'), '/home/sat/Solar_PV/analytics/src']
from advisory_windows import trough_window
from sunset_soc_profile import measure
from pre_dusk_tuning_history import _unique_object, read_day_issues, MORNING_ITEM, IssueHistoryUnavailable

ZONE = ZoneInfo('America/Denver')


def sunset_at(rows, day, origin):
    matches = []
    previous = None
    for persisted, raw in rows:
        if (not isinstance(persisted, datetime) or persisted.utcoffset() is None
                or (previous is not None and persisted <= previous)
                or not (isinstance(raw, datetime)
                        or isinstance(raw, str) and 1 <= len(raw) <= 64)):
            raise ValueError('original ordered sunset archive required')
        previous = persisted
        # DateTime Items are typed PostgreSQL timestamps on this install;
        # strings are accepted only with explicit ISO offsets, never guessed
        # epoch units or host-local timezone attachment.
        sunset = raw if isinstance(raw, datetime) else datetime.fromisoformat(raw)
        if sunset.utcoffset() is None:
            raise ValueError('aware archived sunset required')
        if (sunset.astimezone(ZONE).date() == day and persisted <= origin
                and persisted <= sunset):
            matches.append((persisted, sunset))
    return matches[-1] if matches else None


def counterfactual(record, profiles):
    """Replace only three measured drop inputs; preserve all other components."""
    if len(profiles) != 3:
        raise ValueError('three exact prior-night profiles required')
    dusk = record['dusk_soc_estimate_pct']
    penalty = record['tomorrow_cloud_drop_penalty_pct']
    old = record['overnight_drop_final_pct']
    for value in (dusk, penalty, old):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('finite as-issued components required')
    if not 0 <= dusk <= 100 or penalty not in (0, 2) or not 1 <= old <= 52:
        raise ValueError('as-issued component range mismatch')
    baseline = round(max(12, min(99, dusk-old)))
    if baseline != record['trough']:
        raise ValueError('stored baseline component mismatch')
    observed = [max(1.0, profile['drop_pct']) for profile in profiles]
    if any(type(profile['drop_pct']) not in (int, float)
           or not math.isfinite(profile['drop_pct'])
           or not 0 <= profile['drop_pct'] <= 100 for profile in profiles):
        raise ValueError('invalid measured drop')
    candidate = round(max(12, min(99, dusk-sum(observed)/3-penalty)))
    return baseline, candidate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-day', type=date.fromisoformat, required=True)
    parser.add_argument('--end-day', type=date.fromisoformat, required=True,
                        help='exclusive; at most fourteen issue dates')
    args = parser.parse_args()
    if not 1 <= (args.end_day-args.start_day).days <= 14:
        raise ValueError('bounded issue interval required')
    now = datetime.now(timezone.utc)
    import forecast_intel
    import openhab_sanity_check as oh
    from earthship_energy.db import parse_openhab_jdbc_config
    from earthship_energy.materialize import load_epoch_config
    from earthship_energy.reader import fetch_freshness_observations
    from earthship_energy.trough_assessment import assess_trough_measurement
    import psycopg2
    from psycopg2 import sql
    raw = Path(forecast_intel.STATE_FILE).read_bytes()
    if len(raw) > 256*1024:
        raise ValueError('forecast state exceeds bound')
    state = json.loads(raw, object_pairs_hook=_unique_object)
    banks = [bank for bank in load_epoch_config() if bank.current_analytics]
    if len(banks) != 1 or banks[0].start_local_date is None:
        raise ValueError('unique physical bank required')
    bank = banks[0]
    epoch_start = datetime.combine(bank.start_local_date, time.min, ZONE)
    epoch_end = (datetime.combine(bank.end_local_date_exclusive, time.min, ZONE)
                 if bank.end_local_date_exclusive else None)
    settings = parse_openhab_jdbc_config('/home/sat/.config/hex/energy-power-reader.jdbc')
    if (settings.host, settings.port, settings.dbname, settings.user) != (
            '127.0.0.1', 5432, 'openhab', 'energy_power_reader'):
        raise ValueError('restricted local reader required')
    counts = Counter(); result = []; cache = {}
    with psycopg2.connect(**settings.connect_kwargs, connect_timeout=3,
            options='-c default_transaction_read_only=on') as db:
        db.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with db.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='2000ms'")
            cur.execute("SET LOCAL lock_timeout='1000ms'")
            tables = {}
            for item in ('Sun_Set_Start', 'BMS_SOC_Evidence_JSON'):
                cur.execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2', (item,))
                mapping = cur.fetchall()
                if len(mapping) != 1 or type(mapping[0][0]) is not int or mapping[0][0] < 0:
                    raise ValueError('unique source mapping required')
                tables[item] = 'item'+str(mapping[0][0]).zfill(4)
            first = datetime.combine(args.start_day-timedelta(days=5), time.min, ZONE)
            last = datetime.combine(args.end_day, time.min, ZONE)
            cur.execute(sql.SQL('SELECT time,value FROM public.{} WHERE time >= %s AND time < %s ORDER BY time LIMIT 513')
                .format(sql.Identifier(tables['Sun_Set_Start'])), (first, last))
            sunsets = cur.fetchall()
            if len(sunsets) > 512:
                raise ValueError('sunset archive exceeds bound')
            for offset in range((args.end_day-args.start_day).days):
                day = args.start_day+timedelta(days=offset)
                if not trough_window(day, 'America/Denver').is_complete(now):
                    counts['target_incomplete'] += 1; continue
                record = state['predictions'].get(day.isoformat())
                if not record or len(record.get('overnight_drop_sample_days', [])) != 3:
                    counts['origin_components_unavailable'] += 1; continue
                origin = datetime.fromisoformat(record['temperature_issued_at'])
                if origin.utcoffset() is None or origin.astimezone(ZONE).date() != day or origin > now:
                    raise ValueError('as-issued origin invalid')
                # This role does not have raw forecast-receipt table access.
                # Reuse the existing bounded authenticated original-JDBC REST
                # reader, not an admin credential or a new database grant.
                try:
                    receipts = read_day_issues(oh.get, item=MORNING_ITEM, day=day)
                except IssueHistoryUnavailable:
                    counts['original_issue_unavailable'] += 1; continue
                matched = []
                for entry in receipts:
                    receipt = entry['receipt']
                    if (receipt.get('version') == 1 and receipt.get('predictionDay') == day.isoformat()
                            and datetime.fromisoformat(receipt['issuedAt']) == origin
                            and receipt.get('overnightTroughSocPct') == record['trough']):
                        matched.append(receipt)
                if len(matched) != 1:
                    counts['original_issue_unavailable'] += 1; continue
                def observations(night):
                    boundary = sunset_at(sunsets, night, origin)
                    if boundary is None:
                        return None, None
                    persisted, sunset = boundary
                    window = trough_window(night, 'America/Denver')
                    if window.end > origin and night != day:
                        raise ValueError('future learning target')
                    key = (night, sunset)
                    if key not in cache:
                        cache[key] = fetch_freshness_observations(db, tables['BMS_SOC_Evidence_JSON'],
                            min(sunset, window.start)-timedelta(seconds=120), window.end,
                            row_limit=10001)
                    return boundary, cache[key]
                profiles = []
                sample_days = [date.fromisoformat(value) for value in record['overnight_drop_sample_days']]
                if (len(set(sample_days)) != 3 or sample_days != sorted(sample_days, reverse=True)
                        or any(not 1 <= (day-value).days <= 4 for value in sample_days)
                        or len(record['overnight_drop_samples_pct']) != 3):
                    raise ValueError('original sample date selection invalid')
                for ending_day, stored in zip(record['overnight_drop_sample_days'], record['overnight_drop_samples_pct']):
                    night = date.fromisoformat(ending_day)-timedelta(days=1)
                    boundary, rows = observations(night)
                    profile = measure(day=night, sunset=boundary[1], sunset_persisted_at=boundary[0],
                        as_of=origin, observations=rows, epoch_start=epoch_start, epoch_end=epoch_end) if boundary else None
                    if profile is None or max(1, 99-profile['trough_soc_pct']) != stored:
                        break
                    profiles.append(profile)
                if len(profiles) != 3:
                    counts['prior_profile_unavailable'] += 1; continue
                baseline, candidate = counterfactual(record, profiles)
                # The later actual outcome is used only for scoring, not inputs.
                boundary, rows = observations(day)
                if rows is None:
                    counts['target_sunset_unavailable'] += 1; continue
                actual = assess_trough_measurement(prediction_day=day, site_timezone='America/Denver',
                    assessed_at=now, observations=rows, epoch_start=epoch_start, epoch_end=epoch_end)
                if actual['status'] != 'measured':
                    counts['target_unqualified'] += 1; continue
                target_profile = measure(day=day, sunset=boundary[1], sunset_persisted_at=boundary[0],
                    as_of=now, observations=rows, epoch_start=epoch_start, epoch_end=epoch_end)
                result.append({'day':day.isoformat(), 'origin':origin.isoformat(),
                    'baseline_pct':baseline, 'sunset_drop_counterfactual_pct':candidate,
                    'actual_trough_pct':actual['min_soc_pct'], 'dusk_estimate_pct':record['dusk_soc_estimate_pct'],
                    'actual_sunset_soc_pct':target_profile['sunset_soc_pct'] if target_profile else None,
                    'actual_sunset_drop_pct':target_profile['drop_pct'] if target_profile else None,
                    'actual_sunset_coverage':target_profile['coverage'] if target_profile else None,
                    'prior_sunset_drops_pct':[p['drop_pct'] for p in profiles],
                    'input_digests':[p['evidence_digest'] for p in profiles],
                    'outcome_digest':actual['evidence_digest']})
    print(json.dumps({'status':'diagnostic_only', 'production_changed':False,
        'state_sha256':sha256(raw).hexdigest(), 'as_of':now.isoformat(),
        'counts':dict(counts), 'rows':result}, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('sunset-drop experiment unavailable; private diagnostics withheld') from None
