from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from sunset_soc_profile import measure, charge_profile
from test_qualified_soc_forecast import evidence
from advisory_windows import trough_window


DAY = date(2026, 9, 25)
ZONE = ZoneInfo('America/Denver')


def fixture(day=DAY):
    sunset = datetime.combine(day, datetime.min.time(), ZONE).replace(hour=19)
    sunset = sunset.astimezone(timezone.utc)
    window = trough_window(day, 'America/Denver')
    rows = [(at := sunset + timedelta(minutes=minute),
             evidence(at, soc=82 if minute == 360 else 96))
            for minute in range(int((window.end-sunset).total_seconds()/60))]
    return dict(day=day, sunset=sunset, sunset_persisted_at=sunset-timedelta(hours=12),
        as_of=window.end+timedelta(minutes=1), observations=rows,
        epoch_start=sunset-timedelta(days=60))


def test_measures_actual_sunset_start_without_99_percent_assumption():
    result = measure(**fixture())
    assert result['sunset_soc_pct'] == 96 and result['trough_soc_pct'] == 82
    assert result['drop_pct'] == 14 and result['coverage'] > .99
    assert len(result['evidence_digest']) == 64


@pytest.mark.parametrize('damage', ['missing_start', 'coverage', 'future_row',
    'future_sunset', 'wrong_day', 'epoch_start', 'epoch_end', 'duplicate', 'incomplete',
    'changed_target'])
def test_unqualified_or_future_inputs_are_not_repaired(damage):
    args = fixture(); rows = args['observations']
    if damage == 'missing_start': args['observations'] = rows[10:]
    elif damage == 'coverage': args['observations'] = rows[:100] + rows[300:]
    elif damage == 'future_row': rows.append((args['as_of']+timedelta(seconds=1), '{}'))
    elif damage == 'future_sunset': args['sunset_persisted_at'] = args['sunset']+timedelta(seconds=1)
    elif damage == 'wrong_day': args['day'] += timedelta(days=1)
    elif damage == 'epoch_start': args['epoch_start'] = args['sunset']+timedelta(seconds=1)
    elif damage == 'epoch_end': args['epoch_end'] = args['as_of']-timedelta(hours=1)
    elif damage == 'duplicate': rows.insert(1, rows[0])
    elif damage == 'incomplete': args['as_of'] -= timedelta(minutes=2)
    else:
        # A new minimum before the canonical target changes the target itself.
        at = args['sunset']+timedelta(minutes=20)
        rows[20] = (at, evidence(at, soc=70))
    assert measure(**args) is None


@pytest.mark.parametrize('day', [date(2026, 3, 7), date(2026, 10, 31)])
def test_dst_overnight_uses_elapsed_time_not_fixed_day_seconds(day):
    assert measure(**fixture(day))['coverage'] > .99


def test_stream_bound_and_naive_clock():
    args = fixture(); seen = []
    def stream():
        for index in range(10100):
            seen.append(index)
            yield args['sunset']+timedelta(microseconds=index), '{}'
    args['observations'] = stream()
    assert measure(**args) is None and len(seen) == 10001
    args['as_of'] = args['as_of'].replace(tzinfo=None)
    with pytest.raises(ValueError): measure(**args)


def charge_fixture(day=DAY):
    origin = datetime.combine(day, datetime.min.time(), ZONE).replace(hour=6, minute=40)
    origin = origin.astimezone(timezone.utc)
    sunset = datetime.combine(day, datetime.min.time(), ZONE).replace(hour=19).astimezone(timezone.utc)
    rows = [(at := origin+timedelta(minutes=minute),
             evidence(at, soc=79 if minute < 300 else 100 if minute < 600 else 97))
            for minute in range(-1, int((sunset-origin).total_seconds()/60)+1)]
    return dict(day=day, origin=origin, sunset=sunset,
        sunset_persisted_at=origin-timedelta(hours=6), as_of=sunset+timedelta(minutes=1),
        observations=rows, epoch_start=origin-timedelta(days=60))


def test_first_reported_full_and_afternoon_decline_are_separate_targets():
    result = charge_profile(**charge_fixture())
    assert result['status'] == 'reported_full'
    assert result['elapsed_to_full_seconds'] == 300*60
    assert result['post_full_decline_pct'] == 3 and result['sunset_soc_pct'] == 97
    assert result['censor_at'] is None and result['coverage'] > .99
    assert result['assessed_at'] == charge_fixture()['as_of'].isoformat()


def test_no_full_report_is_censored_not_an_invented_charge_time():
    args = charge_fixture()
    args['observations'] = [(at, evidence(at, soc=95)) for at, _ in args['observations']]
    result = charge_profile(**args)
    assert result['status'] == 'no_full_report' and result['first_reported_full_at'] is None
    assert result['elapsed_to_full_seconds'] is None and result['post_full_decline_pct'] is None
    assert result['censor_at'] == args['sunset'].isoformat()
    args['observations'] = [(at, evidence(at, soc=100)) for at, _ in args['observations']]
    result = charge_profile(**args)
    assert result['status'] == 'already_full_at_origin' and result['elapsed_to_full_seconds'] is None
    assert result['first_reported_full_at'] is None
    assert result['censor_at'] == args['origin'].isoformat()


def test_first_full_report_exactly_at_sunset_is_an_observed_endpoint():
    args = charge_fixture()
    args['observations'] = [(at, evidence(at, soc=100 if at == args['sunset'] else 95))
                            for at, _ in args['observations']]
    result = charge_profile(**args)
    assert result['status'] == 'reported_full'
    assert result['first_reported_full_at'] == args['sunset'].isoformat()
    assert result['elapsed_to_full_seconds'] == (args['sunset'] - args['origin']).total_seconds()
    assert result['post_full_decline_pct'] == 0 and result['censor_at'] is None


def test_charge_profile_has_a_hard_streaming_bound_and_ignores_post_sunset_full_reports():
    args = charge_fixture()
    seen = []
    row = args['observations'][0]
    def oversized():
        for index in range(20000):
            seen.append(index)
            yield row
    args['observations'] = oversized()
    assert charge_profile(**args) is None and len(seen) == 10001
    args = charge_fixture()
    args['observations'] = [(at, evidence(at, soc=95)) for at, _ in args['observations']]
    at = args['sunset'] + timedelta(seconds=30)
    args['observations'].append((at, evidence(at, soc=100)))
    result = charge_profile(**args)
    assert result['status'] == 'no_full_report'
    assert result['first_reported_full_at'] is None


@pytest.mark.parametrize('damage', ['missing_start', 'missing_end', 'gap', 'future_row',
    'future_sunset', 'duplicate', 'incomplete', 'bank', 'oversized'])
def test_charge_timing_and_censoring_require_source_qualification(damage):
    args = charge_fixture(); rows = args['observations']
    if damage == 'missing_start': args['observations'] = rows[2:]
    elif damage == 'missing_end': args['observations'] = rows[:-5]
    elif damage == 'gap': args['observations'] = rows[:250]+rows[350:]
    elif damage == 'future_row': rows.append((args['as_of']+timedelta(seconds=1), '{}'))
    elif damage == 'future_sunset': args['sunset_persisted_at'] = args['origin']+timedelta(seconds=1)
    elif damage == 'duplicate': rows.insert(1, rows[0])
    elif damage == 'incomplete': args['as_of'] = args['sunset']-timedelta(seconds=1)
    elif damage == 'bank': args['epoch_start'] = args['origin']+timedelta(seconds=1)
    else: rows[0] = (rows[0][0], 'x'*4097)
    assert charge_profile(**args) is None
