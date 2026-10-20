from datetime import timedelta
from copy import deepcopy
import pytest
from weather_learning.tests.learning_fixtures import T
from weather_learning.contracts import identity


def test_balanced_decision_can_choose_a_small_mass_tradeoff_on_the_same_pairs():
    from weather_learning.thermal_conditioning_comparison import select_balanced
    rows=[]
    for i in range(3):
        rows.append(dict(origin=(T+timedelta(days=i)).isoformat(),target_at=(T+timedelta(days=i,hours=1)).isoformat(),lead_hours=1,action_stratum='stable',actual=[70.,70.],
            predictions={'six_hourly_physics':[71.8,71.8],'six_hourly_local_irradiance':[70.9,71.98],'incomplete_direct':[70.,70.] if i==0 else None}))
    result=select_balanced(rows)
    assert result['selected_method']=='six_hourly_local_irradiance'
    assert result['metrics']['six_hourly_physics']['balanced_mae_c']==pytest.approx(1.)
    assert result['metrics']['six_hourly_local_irradiance']['balanced_mae_c']==pytest.approx(.8)
    assert result['metrics']['six_hourly_local_irradiance']['mass_mae_c']>result['metrics']['six_hourly_physics']['mass_mae_c']
    assert 'incomplete_direct' in result['excluded_incomplete_methods']
    assert result['automatic_actuation'] is False


def test_outdoor_correction_anchors_first_hour_and_preserves_raw_solar():
    from weather_learning.thermal_conditioning_comparison import correct_outdoor_hours
    from weather_learning.site_calibration import fit_residual
    from test_weather_site_calibration import rows
    samples=rows()
    names=['google_c','lead_days','hour_sin','hour_cos','season_sin','season_cos','origin_bias_decay_c']
    for row in samples:
        row['features']={key:row['features'].get(key,0.) for key in names};row.pop('pair_sha256');row['pair_sha256']=identity(row)
    model=fit_residual(samples,kind='outdoor_temperature_c',cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=20),correction_limit=6.)
    origin=T+timedelta(days=10,hours=9);target=origin+timedelta(hours=1)
    hours={origin.isoformat():{'station_head_temperature_2m':10.,'surface_solar_radiation_downwards_1hr':0.},target.isoformat():{'station_head_temperature_2m':11.,'surface_solar_radiation_downwards_1hr':500.}}
    before=deepcopy(hours);result=correct_outdoor_hours(hours,model=model,origin=origin,outdoor_c=12.,timezone_name='America/Denver',horizon_hours=1)
    assert result[origin.isoformat()]['station_head_temperature_2m']==12.
    assert result[target.isoformat()]['station_head_temperature_2m']==pytest.approx(13.)
    assert result[target.isoformat()]['surface_solar_radiation_downwards_1hr']==500.
    assert hours==before and model['trained_at']==(T+timedelta(days=20)).isoformat()
    with pytest.raises(ValueError,match='earlier'):correct_outdoor_hours(hours,model=model,origin=T+timedelta(days=7),outdoor_c=12.,timezone_name='America/Denver',horizon_hours=1)
