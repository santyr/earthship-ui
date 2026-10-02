from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from sunset_soc_profile import measure, charge_profile, pre_dusk_phase_profile
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


def phase_fixture(day=DAY, lead_seconds=4500):
    args = fixture(day)
    phase = args['sunset']-timedelta(seconds=lead_seconds)
    rows = [(at := phase+timedelta(minutes=minute), evidence(at,
             soc=98 if at < args['sunset'] else 82 if minute == 435 else 96))
            for minute in range(-1, int((trough_window(day, 'America/Denver').end-phase).total_seconds()/60))]
    args.update(lead_seconds=lead_seconds, observations=rows)
    return args


def test_pre_dusk_phase_uses_true_sunset_and_includes_earlier_discharge():
    args = phase_fixture()
    result = pre_dusk_phase_profile(**args)
    assert result['profile_version'] == 'pre-dusk-phase-soc-v1'
    assert result['sunset_at'] == args['sunset'].isoformat()
    assert result['phase_start_at'] == (args['sunset']-timedelta(minutes=75)).isoformat()
    assert result['phase_soc_pct'] == 98 and result['sunset_soc_pct'] == 96
    assert result['trough_soc_pct'] == 82 and result['drop_pct'] == 16
    assert result['pre_sunset_decline_pct'] == 2
    assert result['sunset_to_trough_drop_pct'] == 14
    assert result['coverage'] > .995 and result['canonical_coverage'] > .995
    assert len(result['evidence_digest']) == 64
    assert pre_dusk_phase_profile(**args) == result


@pytest.mark.parametrize('damage', ['missing_phase', 'missing_sunset', 'coverage',
    'changed_target', 'duplicate', 'future_row', 'future_context', 'incomplete',
    'bank_start', 'bank_end'])
def test_matched_phase_requires_source_and_complete_unchanged_target(damage):
    args = phase_fixture(); rows = args['observations']
    if damage == 'missing_phase': args['observations'] = rows[3:]
    elif damage == 'missing_sunset': args['observations'] = rows[:74]+rows[79:]
    elif damage == 'coverage': args['observations'] = rows[:150]+rows[170:]
    elif damage == 'changed_target':
        at, _ = rows[20]; rows[20] = (at, evidence(at, soc=70))
    elif damage == 'duplicate': rows.insert(1, rows[0])
    elif damage == 'future_row': rows.append((args['as_of']+timedelta(seconds=1), '{}'))
    elif damage == 'future_context': args['sunset_persisted_at'] = args['sunset']
    elif damage == 'incomplete': args['as_of'] = trough_window(DAY, 'America/Denver').end-timedelta(seconds=1)
    elif damage == 'bank_start': args['epoch_start'] = args['sunset']-timedelta(seconds=1)
    else: args['epoch_end'] = args['as_of']-timedelta(hours=1)
    assert pre_dusk_phase_profile(**args) is None


@pytest.mark.parametrize('lead', [3599, 5400, True, float('nan')])
def test_matched_phase_does_not_accept_an_arbitrary_shifted_sunset(lead):
    args = phase_fixture(); args['lead_seconds'] = lead
    with pytest.raises(ValueError): pre_dusk_phase_profile(**args)


@pytest.mark.parametrize('day', [date(2026, 3, 7), date(2026, 10, 31)])
def test_matched_phase_dst_window_uses_actual_elapsed_time(day):
    assert pre_dusk_phase_profile(**phase_fixture(day))['coverage'] > .995


def test_matched_phase_does_not_hide_canonical_gaps_in_a_longer_window():
    args = phase_fixture()
    args['observations'] = args['observations'][:200]+args['observations'][206:]
    sunset_args = {key:value for key,value in args.items() if key != 'lead_seconds'}
    less_strict = measure(**sunset_args)
    assert less_strict is not None and less_strict['canonical_coverage'] < .995
    assert pre_dusk_phase_profile(**args) is None


def test_matched_phase_digest_binds_lead_and_raw_rows_and_bounds_stream():
    args = phase_fixture()
    original = pre_dusk_phase_profile(**args)
    args['lead_seconds'] -= 1
    shifted = pre_dusk_phase_profile(**args)
    assert shifted['evidence_digest'] != original['evidence_digest']
    at, _ = args['observations'][2]
    args['observations'][2] = (at, evidence(at, soc=97))
    assert pre_dusk_phase_profile(**args)['evidence_digest'] != shifted['evidence_digest']
    seen = []
    row = args['observations'][0]
    def stream():
        for index in range(20000):
            seen.append(index)
            yield row
    args['observations'] = stream()
    assert pre_dusk_phase_profile(**args) is None and len(seen) == 10001
