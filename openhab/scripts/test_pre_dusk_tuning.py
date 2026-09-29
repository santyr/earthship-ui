"""Strict as-issued comparison against one completed source-bound night."""

from copy import deepcopy
from datetime import date

import pytest

from advisory_windows import trough_window
from pre_dusk_tuning import PairUnavailable, score_pair


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
