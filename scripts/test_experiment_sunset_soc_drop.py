from datetime import date, datetime, timedelta, timezone
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location('sunset_experiment', Path(__file__).with_name('experiment-sunset-soc-drop.py'))
experiment = module_from_spec(spec); spec.loader.exec_module(experiment)


def test_sunset_selection_uses_only_original_available_same_day_context():
    sunset = datetime(2026, 9, 26, 0, 55, tzinfo=timezone.utc)
    origin = sunset+timedelta(hours=12)
    rows = [(sunset-timedelta(hours=12), sunset.isoformat()),
            (origin+timedelta(seconds=1), (sunset+timedelta(seconds=1)).isoformat())]
    assert experiment.sunset_at(rows, date(2026, 9, 25), origin) == rows[0][:1]+(sunset,)
    assert experiment.sunset_at(rows, date(2026, 9, 24), origin) is None
    with pytest.raises(ValueError): experiment.sunset_at(rows+rows, date(2026, 9, 25), origin)


def test_typed_postgresql_timestamp_preserves_offset_and_refuses_naive_value():
    sunset = datetime(2026, 9, 26, 0, 55, tzinfo=timezone.utc)
    persisted = sunset-timedelta(hours=12)
    assert experiment.sunset_at([(persisted, sunset)], date(2026, 9, 25), sunset) == (persisted, sunset)
    with pytest.raises(ValueError):
        experiment.sunset_at([(persisted, sunset.replace(tzinfo=None))], date(2026, 9, 25), sunset)


def test_counterfactual_preserves_dusk_cloud_penalty_and_rounding():
    record = {'dusk_soc_estimate_pct':78.411, 'tomorrow_cloud_drop_penalty_pct':2,
              'overnight_drop_final_pct':15.667, 'trough':63}
    assert experiment.counterfactual(record, [{'drop_pct':10}, {'drop_pct':12}, {'drop_pct':11}]) == (63, 65)
    assert record['trough'] == 63
    record['trough'] = 64
    with pytest.raises(ValueError): experiment.counterfactual(record, [{'drop_pct':11}]*3)


@pytest.mark.parametrize('drop', [-1, float('nan'), 101, True])
def test_bad_measured_drops_are_not_clamped_into_valid_training_inputs(drop):
    record = {'dusk_soc_estimate_pct':99, 'tomorrow_cloud_drop_penalty_pct':0,
              'overnight_drop_final_pct':15, 'trough':84}
    with pytest.raises(ValueError): experiment.counterfactual(record, [{'drop_pct':drop}]*3)


def late_fixture():
    morning = '2026-10-01T12:40:30.513835+00:00'
    record = {'temperature_issued_at': morning, 'dusk_soc_estimate_pct': 74.458,
              'tomorrow_cloud_drop_penalty_pct': 0, 'overnight_drop_final_pct': 22.333,
              'trough': 52, 'overnight_drop_sample_days': ['2026-09-30','2026-09-29','2026-09-28']}
    late = {'issuedAt': '2026-10-01T23:30:00.073215+00:00', 'morningIssuedAt': morning,
            'socAtIssuePct': 88., 'overnightDropPct': 22.333, 'overnightTroughSocPct': 66}
    profiles = [{'prediction_day': day, 'drop_pct': drop, 'as_of': morning,
                 'coverage': .999, 'canonical_coverage': .999, 'evidence_digest': str(index)*64}
                for index,(day,drop) in enumerate([('2026-09-29',17.),('2026-09-28',15.),('2026-09-27',14.)],1)]
    return record, profiles, late


def test_pre_dusk_counterfactual_preserves_source_soc_and_original_inputs():
    record, profiles, late = late_fixture()
    before = deepcopy((record, profiles, late))
    result = experiment.pre_dusk_counterfactual(record, profiles, late)
    assert result['baseline_pct'] == 66
    assert result['candidate_pct'] == 73
    assert result['candidate_drop_pct'] == 15.333
    assert result['soc_at_issue_pct'] == 88.
    assert result['future_outcome_used_as_input'] is False
    assert (record, profiles, late) == before


@pytest.mark.parametrize('damage', ['later_profile','wrong_day','poor_coverage','bad_digest',
                                  'morning_link','drop_link','baseline','bad_soc','late_clock',
                                  'duplicate_days','unordered_days'])
def test_pre_dusk_counterfactual_refuses_unqualified_or_substituted_origins(damage):
    record, profiles, late = late_fixture()
    if damage == 'later_profile': profiles[0]['as_of'] = late['issuedAt']
    elif damage == 'wrong_day': profiles[0]['prediction_day'] = '2026-09-30'
    elif damage == 'poor_coverage': profiles[0]['coverage'] = .99
    elif damage == 'bad_digest': profiles[0]['evidence_digest'] = 'not-bound'
    elif damage == 'morning_link': late['morningIssuedAt'] = '2026-10-01T12:41:00+00:00'
    elif damage == 'drop_link': late['overnightDropPct'] = 20.
    elif damage == 'baseline': late['overnightTroughSocPct'] = 65
    elif damage == 'bad_soc': late['socAtIssuePct'] = True
    elif damage == 'late_clock': late['issuedAt'] = late['morningIssuedAt']
    elif damage == 'duplicate_days':
        record['overnight_drop_sample_days'][1] = record['overnight_drop_sample_days'][0]
        profiles[1] = deepcopy(profiles[0])
    else:
        record['overnight_drop_sample_days'].reverse()
        profiles.reverse()
    with pytest.raises(ValueError):
        experiment.pre_dusk_counterfactual(record, profiles, late)


def test_pre_dusk_counterfactual_uses_positive_math_round_half_ties():
    record, profiles, late = late_fixture()
    for profile in profiles: profile['drop_pct'] = 15.5
    late['socAtIssuePct'] = 88.
    assert experiment.pre_dusk_counterfactual(record, profiles, late)['candidate_pct'] == 73


def phase_comparison_fixture():
    record, profiles, late = late_fixture()
    late['sunsetAt'] = '2026-10-02T00:45:00.073215+00:00'
    for profile in profiles:
        sunset = datetime.fromisoformat(profile['prediction_day']+'T19:00:00-06:00')
        profile.update(profile_version='pre-dusk-phase-soc-v1', lead_seconds=4500.,
            sunset_at=sunset.isoformat(), phase_start_at=(sunset-timedelta(minutes=75)).isoformat(),
            sunset_persisted_at=(sunset-timedelta(hours=12)).isoformat())
    return record, profiles, late


def test_phase_comparison_is_explicitly_bound_to_original_late_lead():
    record, profiles, late = phase_comparison_fixture()
    result = experiment.phase_matched_counterfactual(record, profiles, late)
    assert result['candidate_pct'] == 73 and result['phase_lead_seconds'] == 4500.
    assert result['input_phase_starts'] == [p['phase_start_at'] for p in profiles]
    assert result['profile_basis'] == 'pre-dusk-phase-soc-v1'


@pytest.mark.parametrize('damage', ['lead','version','start','late_sunset','sunset_day','future_context'])
def test_phase_comparison_refuses_mismatched_phase_and_sunset_context(damage):
    record, profiles, late = phase_comparison_fixture()
    if damage == 'lead': profiles[0]['lead_seconds'] += 1
    elif damage == 'version': profiles[0]['profile_version'] = 'sunset-soc-profile-v1'
    elif damage == 'start': profiles[0]['phase_start_at'] = profiles[0]['sunset_at']
    elif damage == 'late_sunset': late['sunsetAt'] = late['issuedAt']
    elif damage == 'sunset_day': profiles[0]['sunset_at'] = profiles[1]['sunset_at']
    else: profiles[0]['sunset_persisted_at'] = profiles[0]['sunset_at']
    with pytest.raises(ValueError): experiment.phase_matched_counterfactual(record, profiles, late)
