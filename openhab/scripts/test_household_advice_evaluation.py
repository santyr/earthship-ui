"""Thermal episodes retain confounders and score forecasts under known actions."""
from datetime import timedelta
from local_measurement_test_support import NOW
import importlib,pytest


def api():return importlib.import_module('household.advice.evaluation')


def episode():
    return dict(episode_id='a'*64,shade_id='shade-9',epoch='installation-1',start_earliest=NOW.isoformat(),
        start_latest=(NOW+timedelta(seconds=3)).isoformat(),stop_observed_at=(NOW+timedelta(seconds=8)).isoformat(),
        from_open_pct=0.,to_open_pct=37.5,intermediate_open_pct=[20.],event_refs=['b'*64],origin='unknown',thermal_benefit_verified=False)


def test_episodes_retain_unadvised_movements_and_only_asof_confounders():
    contexts=[dict(available_at=NOW.isoformat(),initial_air_f=70.,initial_mass_f=69.,outdoor_f=50.,solar_geometry_ref='c'*64,
       weather_ref='d'*64,ventilation_state='closed',concurrent_changes=[],sensor_epochs={'air':'1'},model_training_end=(NOW-timedelta(days=1)).isoformat()),
       dict(available_at=(NOW+timedelta(hours=1)).isoformat(),future_temperature_f=100.)]
    result=api().action_outcome_episodes([episode()],contexts,[],as_of=NOW+timedelta(hours=2))
    assert len(result)==1 and result[0]['action']['to_open_pct']==37.5
    assert 'future_temperature_f' not in result[0]['context']
    assert result[0]['recommended_action_required'] is False and result[0]['causal_benefit_qualified'] is False


def test_matched_later_windows_compare_position_aware_with_coarse_predictions():
    rows=[dict(decision_at=NOW.isoformat(),target_at=(NOW+timedelta(hours=1)).isoformat(),observed_available_at=(NOW+timedelta(hours=2)).isoformat(),
       training_end=(NOW-timedelta(days=1)).isoformat(),actual_f=72.,coarse_prediction_f=75.,position_prediction_f=73.,context_complete=True)]
    report=api().compare_known_action_forecasts(rows,as_of=NOW+timedelta(hours=3))
    assert report['coarse_mae_f']==3. and report['position_aware_mae_f']==1.
    assert report['independent_days']==1 and report['causal_benefit_qualified'] is False
    assert report['qualification']=='collecting'


def test_future_or_training_overlap_is_not_evaluation_evidence():
    rows=[dict(decision_at=NOW.isoformat(),target_at=(NOW+timedelta(hours=1)).isoformat(),observed_available_at=(NOW+timedelta(hours=2)).isoformat(),
       training_end=NOW.isoformat(),actual_f=72.,coarse_prediction_f=75.,position_prediction_f=73.,context_complete=True)]
    assert api().compare_known_action_forecasts(rows,as_of=NOW+timedelta(hours=3))['pair_count']==0
