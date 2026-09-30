from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from sunset_soc_profile import measure
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
