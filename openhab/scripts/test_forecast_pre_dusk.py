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
