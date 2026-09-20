from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
from test_forecast_intel import fi
from weather_temperature_evidence import TemperaturePolicy, temperature_receipt
from weather_temperature_reader import select_temperature_at

TARGET = datetime(2026, 9, 20, 18, tzinfo=timezone.utc)
CUTOVER = (TARGET - timedelta(days=2)).isoformat()


def initial():
    return {'hourly_temp_model': fi.hourly_model_seed(), 'hourly_temp_targets': {
        TARGET.isoformat(): {'raw': 74.0, 'captured_at': (TARGET - timedelta(days=1)).isoformat()}}}


def receipt(target=TARGET):
    return {'temperatureF': 70.0, 'receivedAt': target - timedelta(seconds=40),
            'storedAt': target - timedelta(seconds=30), 'validUntil': target + timedelta(seconds=80),
            'snapshotSha256': 'a' * 64, 'streamEpoch': '882078a7-c0f2-4079-a979-120a100c5e92'}


@pytest.fixture(autouse=True)
def no_legacy(monkeypatch):
    def reject(*_):
        pytest.fail('qualified mode must never query legacy numeric history')
    monkeypatch.setattr(fi, 'series', reject)


def score(state, reader, cutover=CUTOVER, now=TARGET + timedelta(minutes=30)):
    return fi.score_hourly_targets(state, now, qualified_reader=reader, evidence_cutover=cutover)


def test_qualified_learning_consumes_once_and_keeps_provenance_and_other_buckets():
    state = initial()
    previous = deepcopy(state['hourly_temp_model']['1'])
    assert score(state, lambda **_: receipt()) == 1
    assert state['hourly_temp_model']['12']['count'] == 1
    assert state['hourly_temp_model']['1'] == previous
    assert state['hourly_temp_evidence_receipts'][0]['snapshotSha256'] == 'a' * 64
    assert state['hourly_temp_evidence_receipts'][0]['raw'] == 74
    assert score(state, lambda **_: pytest.fail('already consumed')) == 0


@pytest.mark.parametrize('bad', [None, {}, {'temperatureF': float('nan')},
    {**receipt(), 'receivedAt': TARGET + timedelta(seconds=1)},
    {**receipt(), 'storedAt': TARGET + timedelta(seconds=1)},
    {**receipt(), 'validUntil': TARGET}, {**receipt(), 'temperatureF': True},
    {**receipt(), 'snapshotSha256': 'bad'},
    {**receipt(), 'receivedAt': TARGET.replace(tzinfo=None)}])
def test_unqualified_evidence_never_updates_or_consumes(bad):
    state = initial(); before = deepcopy(state)
    assert score(state, lambda **_: bad) == 0
    assert state == before


def test_reader_error_never_falls_back():
    def unavailable(**_): raise RuntimeError('unavailable')
    state = initial(); before = deepcopy(state)
    assert score(state, unavailable) == 0
    assert state == before


def test_atomic_save_reload_keeps_receipt_and_consumed_target(monkeypatch, tmp_path):
    monkeypatch.setattr(fi, 'STATE_DIR', str(tmp_path))
    monkeypatch.setattr(fi, 'STATE_FILE', str(tmp_path / 'state.json'))
    state = initial()
    assert score(state, lambda **_: receipt()) == 1
    fi.save_state(state)
    reloaded = fi.load_state()
    assert reloaded['hourly_temp_evidence_receipts'] == state['hourly_temp_evidence_receipts']
    assert reloaded['hourly_temp_model'] == state['hourly_temp_model']
    assert score(reloaded, lambda **_: pytest.fail('must not replay after reload')) == 0


def test_pre_cutover_capture_is_preserved_but_not_scored():
    state = initial(); before = deepcopy(state)
    assert score(state, lambda **_: pytest.fail('ineligible'), (TARGET - timedelta(hours=1)).isoformat()) == 0
    assert state == before


@pytest.mark.parametrize('cutover', [None, '2026-09-18T12:00:00', 'bad', (TARGET + timedelta(days=1)).isoformat()])
def test_invalid_cutover_refuses_before_mutation(cutover):
    state = initial(); before = deepcopy(state)
    with pytest.raises(ValueError): score(state, lambda **_: receipt(), cutover)
    assert state == before


def test_count_bound_and_old_ineligible_targets_do_not_starve_new_work():
    state = initial()
    for i in range(1, 26):
        key = (TARGET + timedelta(hours=i)).isoformat()
        state['hourly_temp_targets'][key] = {'raw': 74, 'captured_at': (TARGET - timedelta(days=1)).isoformat()}
    for i in range(1, 6):
        state['hourly_temp_targets'][(TARGET - timedelta(hours=i)).isoformat()] = {
            'raw': 74, 'captured_at': (TARGET - timedelta(days=3)).isoformat()}
    calls = []
    def reader(**kwargs):
        calls.append(kwargs['target']); return receipt(kwargs['target'])
    assert score(state, reader, now=TARGET + timedelta(hours=27)) == 24
    assert len(calls) == 24
    assert len(state['hourly_temp_targets']) == 7


@pytest.mark.parametrize('case,expected', [
    ('unchanged', 1), ('closer_future', 1), ('future_only', 0),
    ('expired', 0), ('invalid_barrier', 0), ('restart_unknown', 0),
    ('fresh_recovery', 1), ('foreign_id', 0),
])
def test_real_receipt_reader_to_scorer(case, expected):
    policy = TemperaturePolicy('Fineoffset-WH65B', 206, -40, 140, 120)
    epoch = '882078a7-c0f2-4079-a979-120a100c5e92'
    def row(seconds, value='70', sensor=206, restart=False):
        at = TARGET + timedelta(seconds=seconds)
        record = None if restart else temperature_receipt(
            {'model': policy.model, 'id': str(sensor), 'tempf': value},
            policy=policy, stream_epoch=epoch, received_at=at)
        envelope_epoch = 'f624fc92-61de-4a8b-b6f2-5f5948fe5b7f' if restart else epoch
        return at, json.dumps({'version': 1, 'streamEpoch': envelope_epoch, 'records': {'outdoor': record}})
    cases = {
        'unchanged': [row(-100), row(-40)],
        'closer_future': [row(-40), row(1, '90')],
        'future_only': [row(1, '90')],
        'expired': [row(-120)],
        'invalid_barrier': [row(-40), row(-20, 'invalid')],
        'restart_unknown': [row(-40), row(-20, restart=True)],
        'fresh_recovery': [row(-40, 'invalid'), row(-10)],
        'foreign_id': [row(-40, sensor=999)],
    }
    def reader(**kwargs):
        return select_temperature_at(cases[case], history_start=TARGET - timedelta(seconds=120),
            stream='outdoor', policy=policy, **kwargs)
    state = initial(); before = deepcopy(state)
    assert score(state, reader) == expected
    if expected:
        assert state['hourly_temp_evidence_receipts'][0]['measured'] == 70
        assert state['hourly_temp_model']['12']['count'] == 1
        assert score(state, reader) == 0
    else:
        assert state == before
