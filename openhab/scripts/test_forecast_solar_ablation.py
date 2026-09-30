from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from forecast_solar_ablation import compare

START = datetime(2026, 9, 1, 14, 45, tzinfo=timezone.utc)


def pairs():
    rows = []
    for day in range(20):
        origin = START + timedelta(days=day)
        daylight = 14 - day / 10
        rows.append({'origin': origin, 'target': origin + timedelta(hours=24),
                     'forecast_f': 70.0, 'actual_f': 70 + (daylight - 13) * 2,
                     'daylight_hours': daylight, 'season': 'SUMMER',
                     'outcome_stored_at': origin + timedelta(hours=24),
                     'forecast_sha256': 'a' * 64, 'solar_sha256': 'b' * 64,
                     'outcome_sha256': 'c' * 64})
    return rows


def test_daylight_relationship_learned_on_training_only_beats_bias():
    rows = pairs(); before = deepcopy(rows)
    report = compare(rows, split_at=START + timedelta(days=15))
    assert report['status'] == 'shadow_comparison'
    assert report['train_days'] == 15 and report['test_days'] == 5
    assert report['variants']['daylight']['mae_f'] < report['variants']['bias']['mae_f']
    assert report['variants']['season'] == report['variants']['bias']
    assert report['production_changed'] is False and report['seasonal_skill_proven'] is False
    assert rows == before


def test_test_labels_do_not_affect_frozen_predictions():
    rows = pairs(); split = START + timedelta(days=15)
    original = compare(rows, split_at=split)
    for row in rows[15:]: row['actual_f'] += 10
    changed = compare(rows, split_at=split)
    for variant in original['variants']:
        assert changed['variants'][variant]['bias_f'] == pytest.approx(
            original['variants'][variant]['bias_f'] - 10)


def test_unseen_season_cannot_invent_a_coefficient():
    rows = pairs()
    for row in rows[15:]: row['season'] = 'AUTUMN'
    report = compare(rows, split_at=START + timedelta(days=15))
    assert report['unseen_test_seasons'] == ['AUTUMN']
    assert report['variants']['season'] == report['variants']['bias']


def test_unmatured_training_target_is_excluded_and_small_comparisons_withheld():
    rows = pairs()
    report = compare(rows, split_at=START + timedelta(days=10, hours=-1))
    assert report['train_days'] == 9
    assert report['status'] == 'withheld_insufficient_pairs'
    assert report['variants'] == {}
    assert report['minimum_train_days'] == 10
    assert report['raw_test_baseline']['count'] == 10


@pytest.mark.parametrize('damage', ['future_receipt', 'naive', 'overlap', 'nonfinite',
                                   'bool', 'digest', 'extra', 'reordered', 'wrong_horizon'])
def test_invalid_pairs_refused(damage):
    rows = pairs()
    if damage == 'future_receipt': rows[0]['outcome_stored_at'] += timedelta(seconds=1)
    elif damage == 'naive': rows[0]['origin'] = rows[0]['origin'].replace(tzinfo=None)
    elif damage == 'overlap': rows[1] = deepcopy(rows[0])
    elif damage == 'nonfinite': rows[0]['daylight_hours'] = float('nan')
    elif damage == 'bool': rows[0]['forecast_f'] = True
    elif damage == 'digest': rows[0]['solar_sha256'] = 'bad'
    elif damage == 'extra': rows[0]['private_input'] = 'not permitted'
    elif damage == 'reordered': rows = list(reversed(rows))
    else: rows[0]['target'] += timedelta(hours=1)
    with pytest.raises(ValueError): compare(rows, split_at=START + timedelta(days=15))
