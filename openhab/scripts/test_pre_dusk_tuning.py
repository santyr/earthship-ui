"""Strict as-issued comparison against one completed source-bound night."""

from copy import deepcopy
from datetime import date, datetime, timedelta
from hashlib import sha256
import json

import pytest

from advisory_windows import trough_window
from pre_dusk_tuning import PairUnavailable, score_pair, verify_issue_soc


DAY = date(2026, 9, 29)
WINDOW = trough_window(DAY, 'America/Denver')
MORNING = {
    'version': 1, 'predictionDay': DAY.isoformat(),
    'issuedAt': '2026-09-29T06:40:00-06:00',
    'overnightTroughSocPct': 53,
}
LATE = {
    'version': 1, 'basis': 'atomic_soc_pre_dusk_v1',
    'predictionDay': DAY.isoformat(), 'issuedAt': '2026-09-29T17:30:00-06:00',
    'sunsetAt': '2026-09-29T18:48:23-06:00',
    'morningIssuedAt': MORNING['issuedAt'],
    'socRecordedAt': '2026-09-29T17:29:45-06:00',
    'socStreamEpoch': '123e4567-e89b-42d3-a456-426614174000',
    'socEvidenceSha256': 'b' * 64,
    'socAtIssuePct': 99, 'overnightDropPct': 18,
    'overnightTroughSocPct': 81,
}
OUTCOME = {
    'assessment_version': 'atomic-soc-trough-v1',
    'source': 'BMS_SOC_Evidence_JSON', 'site_timezone': 'America/Denver',
    'prediction_day': DAY.isoformat(), 'status': 'measured',
    'assessed_at': '2026-09-30T11:10:00-06:00',
    'window_start': WINDOW.start.isoformat(),
    'window_end': WINDOW.end.isoformat(),
    'min_soc_pct': 84, 'observed_min_soc_pct': 84, 'coverage': 0.999,
    'evidence_digest': 'a' * 64,
}


def source_evidence():
    at = datetime.fromisoformat(LATE['socRecordedAt'])
    stamp = lambda value: int(value.timestamp() * 1000)
    return json.dumps({'version': 1, 'streamEpoch': LATE['socStreamEpoch'],
        'recordedAt': stamp(at), 'status': 'valid', 'reason': 'ok',
        'observedAt': stamp(at), 'scaleObservedAt': stamp(at),
        'validUntil': stamp(at + timedelta(seconds=120)), 'soc': 99})


def test_pre_dusk_issue_matches_original_persisted_soc_receipt():
    raw = source_evidence()
    late = {**LATE, 'socEvidenceSha256': sha256(raw.encode()).hexdigest()}
    stored = datetime.fromisoformat(LATE['socRecordedAt']) + timedelta(seconds=2)
    assert verify_issue_soc(late, raw, stored.isoformat()) is True
    tampered = json.loads(raw)
    tampered['soc'] = 98
    with pytest.raises(PairUnavailable):
        verify_issue_soc(late, json.dumps(tampered), stored.isoformat())
    with pytest.raises(PairUnavailable):
        verify_issue_soc(late, raw, (datetime.fromisoformat(LATE['issuedAt']) + timedelta(seconds=1)).isoformat())
    with pytest.raises(PairUnavailable):
        verify_issue_soc({**late, 'socStreamEpoch': '123e4567-e89b-42d3-a456-426614174001'}, raw, stored.isoformat())
    with pytest.raises(PairUnavailable):
        verify_issue_soc({**late, 'socAtIssuePct': True}, raw, stored.isoformat())
    with pytest.raises(PairUnavailable):
        verify_issue_soc({**late, 'issuedAt': '2026-09-29T17:33:00-06:00'}, raw, stored.isoformat())


def test_scores_same_target_issues_and_measured_night_without_causal_claim():
    result = score_pair(MORNING, LATE, OUTCOME)
    assert result['morning_signed_error_pp'] == -31
    assert result['pre_dusk_signed_error_pp'] == -3
    assert result['absolute_error_improvement_pp'] == 28
    assert result['target_start'] == WINDOW.start.isoformat()
    assert result['target_end'] == WINDOW.end.isoformat()
    assert result['causal_reward_proven'] is False


@pytest.mark.parametrize('which,key,value', [
    ('morning', 'version', True),
    ('morning', 'predictionDay', '2026-09-28'),
    ('morning', 'overnightTroughSocPct', None),
    ('late', 'version', True),
    ('late', 'morningIssuedAt', '2026-09-28T06:40:00-06:00'),
    ('late', 'socRecordedAt', '2026-09-29T17:27:00-06:00'),
    ('late', 'socStreamEpoch', 'unqualified'),
    ('late', 'socEvidenceSha256', 'unqualified'),
    ('late', 'overnightTroughSocPct', 80),
    ('outcome', 'status', 'pending'),
    ('outcome', 'coverage', 0.899),
    ('outcome', 'observed_min_soc_pct', 85),
    ('outcome', 'prediction_day', '2026-09-28'),
    ('outcome', 'window_end', '2026-09-30T10:00:00-06:00'),
    ('outcome', 'evidence_digest', 'unqualified'),
])
def test_refuses_mismatched_or_unqualified_pair(which, key, value):
    rows = {'morning': deepcopy(MORNING), 'late': deepcopy(LATE),
            'outcome': deepcopy(OUTCOME)}
    rows[which][key] = value
    with pytest.raises(PairUnavailable):
        score_pair(rows['morning'], rows['late'], rows['outcome'])
