"""Separate pre-dusk estimate never mutates the morning issue or sends DMs."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from uuid import UUID

import pytest

from forecast_pre_dusk import (RECEIPT_ITEM, VALUE_ITEM, Withheld,
                               already_issued, estimate, run)
from pre_dusk_tuning import verify_issue_soc


NOW = datetime(2026, 9, 29, 23, 33, 23, tzinfo=timezone.utc)
SUNSET = '2026-09-29T18:48:23-06:00'


def evidence(at=NOW - timedelta(seconds=20), *, soc=100, status='valid'):
    stamp = lambda instant: int(instant.timestamp() * 1000)
    return json.dumps({
        'version': 1, 'streamEpoch': str(UUID(int=1)),
        'recordedAt': stamp(at), 'status': status,
        'reason': 'ok' if status == 'valid' else 'input_stale',
        'observedAt': stamp(at) if status == 'valid' else None,
        'scaleObservedAt': stamp(at) if status == 'valid' else None,
        'validUntil': stamp(at + timedelta(seconds=120)) if status == 'valid' else None,
        'soc': soc if status == 'valid' else None,
    })


def morning(**changes):
    return {
        'temperature_issued_at': '2026-09-29T12:40:17+00:00',
        'overnight_drop_samples_pct': [19, 15, 15],
        'overnight_drop_sample_days': ['2026-09-28', '2026-09-27', '2026-09-26'],
        'overnight_drop_final_pct': 18.333,
        **changes,
    }


def test_separate_receipt_uses_fresh_atomic_soc_and_frozen_drop():
    result = estimate(NOW, SUNSET, evidence(), morning())
    assert result == {
        'version': 1, 'basis': 'atomic_soc_pre_dusk_v1',
        'predictionDay': '2026-09-29',
        'issuedAt': NOW.isoformat(),
        'sunsetAt': '2026-09-30T00:48:23+00:00',
        'morningIssuedAt': '2026-09-29T12:40:17+00:00',
        'socRecordedAt': (NOW - timedelta(seconds=20)).isoformat(),
        'socStreamEpoch': str(UUID(int=1)),
        'socEvidenceSha256': sha256(evidence().encode('utf-8')).hexdigest(),
        'socAtIssuePct': 100, 'overnightDropPct': 18.333,
        'overnightTroughSocPct': 82,
    }


def test_rounding_matches_display_at_half_point():
    assert estimate(NOW, SUNSET, evidence(soc=99),
                    morning(overnight_drop_final_pct=18.5))['overnightTroughSocPct'] == 81


def test_issued_provenance_matches_original_persisted_atomic_receipt():
    raw = evidence()
    issued = estimate(NOW, SUNSET, raw, morning())
    assert verify_issue_soc(issued, raw, (NOW - timedelta(seconds=10)).isoformat()) is True


@pytest.mark.parametrize('kwargs', [
    {'now': NOW - timedelta(minutes=16)},
    {'now': NOW + timedelta(minutes=16)},
    {'sunset_state': '2026-09-28T18:48:23-06:00'},
    {'soc_raw': evidence(NOW - timedelta(minutes=3))},
    {'soc_raw': evidence(status='unavailable')},
    {'morning_record': morning(overnight_drop_samples_pct=[])},
    {'morning_record': morning(temperature_issued_at='2026-09-28T12:40:17+00:00')},
])
def test_missing_or_out_of_window_inputs_withhold(kwargs):
    args = {'now': NOW, 'sunset_state': SUNSET, 'soc_raw': evidence(),
            'morning_record': morning()}
    args.update(kwargs)
    with pytest.raises(Withheld):
        estimate(args['now'], args['sunset_state'], args['soc_raw'], args['morning_record'])


def test_worker_commits_value_before_receipt_and_skips_same_day(tmp_path):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'predictions': {'2026-09-29': morning()}}))
    items = {'Sun_Set_Start': SUNSET, RECEIPT_ITEM: 'NULL',
             'BMS_SOC_Evidence_JSON': evidence()}
    writes = []

    def get(path):
        return {'state': items[path.removeprefix('/items/')]}

    def put(name, value):
        writes.append((name, value))
        items[name] = str(value)

    assert run(NOW, get=get, put=put, state_path=state) == 'issued'
    assert [name for name, _ in writes] == [VALUE_ITEM, RECEIPT_ITEM]
    assert json.loads(writes[1][1])['overnightTroughSocPct'] == 82
    assert already_issued(items[RECEIPT_ITEM], '2026-09-29')
    assert run(NOW, get=get, put=put, state_path=state) == 'already_issued'
    assert len(writes) == 2


def test_receipt_is_not_written_after_value_failure(tmp_path):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'predictions': {'2026-09-29': morning()}}))
    items = {'Sun_Set_Start': SUNSET, RECEIPT_ITEM: 'NULL',
             'BMS_SOC_Evidence_JSON': evidence()}
    attempted = []

    def put(name, value):
        attempted.append(name)
        raise OSError('disconnected')

    with pytest.raises(OSError):
        run(NOW, get=lambda path: {'state': items[path.removeprefix('/items/')]},
            put=put, state_path=state)
    assert attempted == [VALUE_ITEM]


@pytest.mark.parametrize('days', [
    ['2026-09-28', '2026-09-28', '2026-09-26'],
    ['2026-09-27', '2026-09-28', '2026-09-26'],
    ['2026-09-29', '2026-09-28', '2026-09-27'],
    ['2026-09-20', '2026-09-19', '2026-09-18'],
    ['not-a-day', '2026-09-27', '2026-09-26'],
])
def test_pre_dusk_requires_distinct_recent_historical_drop_nights(days):
    with pytest.raises(Withheld, match='overnight-drop history'):
        estimate(
            NOW,
            SUNSET,
            evidence(),
            morning(overnight_drop_sample_days=days),
        )


def test_pre_dusk_requires_one_night_identity_per_drop_sample():
    with pytest.raises(Withheld, match='overnight-drop history'):
        estimate(
            NOW,
            SUNSET,
            evidence(),
            morning(overnight_drop_sample_days=['2026-09-28', '2026-09-27']),
        )


@pytest.mark.parametrize('delay,reason', [
    (timedelta(seconds=101), 'fresh atomic SoC'),
    (timedelta(minutes=16), 'outside pre-dusk issue window'),
])
def test_live_issue_clock_rejects_inputs_that_expire_during_io(tmp_path, monkeypatch, delay, reason):
    import forecast_pre_dusk as module
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'predictions': {'2026-09-29': morning()}}))
    clock = {'at': NOW}
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock['at'].astimezone(tz) if tz else clock['at'].replace(tzinfo=None)
    monkeypatch.setattr(module, 'datetime', Clock)
    # The production clock supplies datetime instances; retain that type check.
    clock['at'] = Clock.fromisoformat(NOW.isoformat())
    items = {'Sun_Set_Start': SUNSET, RECEIPT_ITEM: 'NULL',
             'BMS_SOC_Evidence_JSON': evidence()}
    writes = []
    def get(path):
        name = path.removeprefix('/items/')
        if name == 'BMS_SOC_Evidence_JSON':
            clock['at'] += delay
        return {'state': items[name]}
    with pytest.raises(Withheld, match=reason):
        module.run(get=get, put=lambda *args: writes.append(args), state_path=state)
    assert writes == []


def test_stale_soc_attempt_can_retry_with_fresh_evidence_in_the_same_window(tmp_path):
    state = tmp_path / 'state.json'
    original = {'predictions': {'2026-09-29': morning()}}
    state.write_text(json.dumps(original))
    items = {'Sun_Set_Start': SUNSET, RECEIPT_ITEM: 'NULL',
             'BMS_SOC_Evidence_JSON': evidence(NOW - timedelta(minutes=3))}
    writes = []
    def get(path):
        return {'state': items[path.removeprefix('/items/')]}
    def put(name, value):
        writes.append((name, value))
        items[name] = str(value)
    with pytest.raises(Withheld, match='fresh atomic SoC'):
        run(NOW, get=get, put=put, state_path=state)
    assert writes == []
    retry_at = NOW + timedelta(minutes=10)
    items['BMS_SOC_Evidence_JSON'] = evidence(retry_at - timedelta(seconds=20))
    assert run(retry_at, get=get, put=put, state_path=state) == 'issued'
    assert run(retry_at, get=get, put=put, state_path=state) == 'already_issued'
    receipt = json.loads(items[RECEIPT_ITEM])
    assert receipt['issuedAt'] == retry_at.isoformat()
    assert receipt['sunsetAt'] == '2026-09-30T00:48:23+00:00'
    assert len(writes) == 2 and json.loads(state.read_text()) == original


@pytest.mark.parametrize('lead,accepted', [(90, False), (89.999, True), (60, True), (59.999, False)])
def test_exact_sunset_lead_boundaries_preserve_unshifted_receipt(lead, accepted):
    at = datetime.fromisoformat(SUNSET) - timedelta(minutes=lead)
    if accepted:
        receipt = estimate(at, SUNSET, evidence(at - timedelta(seconds=20)), morning())
        assert receipt['sunsetAt'] == '2026-09-30T00:48:23+00:00'
    else:
        with pytest.raises(Withheld, match='outside pre-dusk issue window'):
            estimate(at, SUNSET, evidence(at - timedelta(seconds=20)), morning())


def test_restart_retains_same_day_idempotency_in_the_external_receipt(tmp_path):
    import importlib.util
    import forecast_pre_dusk as current
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'predictions': {'2026-09-29': morning()}}))
    items = {'Sun_Set_Start': SUNSET, RECEIPT_ITEM: 'NULL', 'BMS_SOC_Evidence_JSON': evidence()}
    writes = []
    def get(path):
        return {'state': items[path.removeprefix('/items/')]}
    def put(name, value):
        writes.append((name, value)); items[name] = str(value)
    assert current.run(NOW, get=get, put=put, state_path=state) == 'issued'
    spec = importlib.util.spec_from_file_location('restarted_pre_dusk', current.__file__)
    restarted = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(restarted)
    assert restarted.run(NOW + timedelta(minutes=10), get=get, put=put, state_path=state) == 'already_issued'
    assert len(writes) == 2


def test_changed_sunset_is_read_again_at_the_next_opportunity(tmp_path):
    state = tmp_path / 'state.json'
    state.write_text(json.dumps({'predictions': {'2026-09-29': morning()}}))
    delayed = (datetime.fromisoformat(SUNSET) + timedelta(hours=1)).isoformat()
    items = {'Sun_Set_Start': delayed, RECEIPT_ITEM: 'NULL', 'BMS_SOC_Evidence_JSON': evidence()}
    writes = []
    get = lambda path: {'state': items[path.removeprefix('/items/')]}
    assert run(NOW, get=get, put=lambda *args: writes.append(args), state_path=state) == 'outside_window'
    assert writes == []
    retry_at = NOW + timedelta(minutes=10)
    items.update(Sun_Set_Start=SUNSET, BMS_SOC_Evidence_JSON=evidence(retry_at - timedelta(seconds=20)))
    assert run(retry_at, get=get, put=lambda *args: writes.append(args), state_path=state) == 'issued'
    assert json.loads(writes[-1][1])['sunsetAt'] == datetime.fromisoformat(SUNSET).astimezone(timezone.utc).isoformat()


def test_real_flock_contention_defers_then_allows_next_attempt(tmp_path):
    import fcntl
    import subprocess
    import sys
    lock = tmp_path / 'consumers.lock'
    marker = tmp_path / 'worker-ran'
    command = ['/usr/bin/flock', '--wait', '0', '--conflict-exit-code=75', str(lock),
               sys.executable, '-c', 'from pathlib import Path; import sys; Path(sys.argv[1]).write_text("ran")', str(marker)]
    with lock.open('w') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        assert subprocess.run(command, timeout=3).returncode == 75
        assert not marker.exists()
    assert subprocess.run(command, timeout=3).returncode == 0
    assert marker.read_text() == 'ran'


@pytest.mark.parametrize('sunset', [
    '2026-06-22T02:28:17.403+00:00',  # Native summer comparison, Denver daylight time.
    '2026-12-21T23:43:54.479+00:00',  # Native winter comparison, Denver standard time.
])
def test_real_calendar_preserves_retry_opportunities_after_a_missed_first_trigger(sunset):
    import os
    import re
    import subprocess
    from pathlib import Path
    timer = Path(__file__).resolve().parents[1] / 'systemd/user/forecast-pre-dusk.timer'
    text = timer.read_text()
    calendar = next(line.split('=', 1)[1] for line in text.splitlines() if line.startswith('OnCalendar='))
    assert 'Persistent=true' in text
    event = datetime.fromisoformat(sunset)
    opening = event - timedelta(minutes=90)
    result = subprocess.check_output([
        'systemd-analyze', 'calendar', '--iterations=4',
        '--base-time=' + opening.strftime('%Y-%m-%d %H:%M:%S UTC'), calendar,
    ], env=dict(os.environ, TZ='UTC'), text=True, timeout=5)
    stamps = re.findall(r'(?:Next elapse|Iteration #\d+): \w+ (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) UTC', result)
    opportunities = [datetime.strptime(s, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc) for s in stamps]
    inside = [at for at in opportunities if 60 <= (event-at).total_seconds()/60 < 90]
    assert len(inside) == 3
    assert inside[1:] == [inside[0]+timedelta(minutes=10), inside[0]+timedelta(minutes=20)]
    assert opportunities[-1] > event - timedelta(minutes=60)
