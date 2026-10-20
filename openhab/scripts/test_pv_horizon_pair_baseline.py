"""Horizon expansion must share the exact served interval arithmetic."""
from datetime import timedelta,datetime
from math import fsum
import pytest
from historical_pv_horizon_assess import expand_horizon_pairs
from historical_pv_train import pair_baseline
from household_pv_model import integrate_array,ASSUMPTIONS,INTERVAL_BASELINE_RULE
from weather_learning.contracts import identity
from test_pv_pair_baseline import START,forcing
from test_daily_pv_potential import ARRAY


@pytest.mark.parametrize('offset,missing,elevation,terrain',[
    (0,None,30.,5.),(55*60,None,30.,5.),(55*60+15,None,30.,5.),
    (0,0,30.,5.),(0,1,30.,5.),(0,None,-1.,5.),(0,None,2.,0.),(0,None,30.,40.),
])
def test_expanded_horizon_pair_matches_live_served_interval(offset,missing,elevation,terrain):
    start=START+timedelta(seconds=offset);end=start+timedelta(minutes=5)
    forecast,positions,horizon,hours=forcing(start,missing=missing,elevation=elevation,terrain=terrain)
    served=integrate_array(array=ARRAY,assumptions=ASSUMPTIONS,hourly_forecast=forecast,positions=positions,
        origin=start,horizon_hours=1,timezone_name='America/Denver',horizon_profile=horizon)
    expected=fsum(s['potential_pv_kwh'] for s in served['steps'] if datetime.fromisoformat(s['end'])<=end)*12000
    row=dict(start=start.isoformat(),end=end.isoformat(),origin=(start-timedelta(hours=2)).isoformat(),baseline_w=expected,
        outcome_w=800.,azimuth_degrees=110.,lead_hours=2+5/60,forecast_sha256='a'*64,energy_source_sha256='b'*64,
        potential_proxy_eligible=True,baseline_rule=INTERVAL_BASELINE_RULE);row['pair_sha256']=identity(row)
    expanded=expand_horizon_pairs([row],runs=[(start-timedelta(hours=2),'a'*64,hours,'recorded')],
        positions={p['at']:p for p in positions},array=ARRAY,horizon=horizon)
    assert len(expanded)==1
    assert expanded[0]['baseline_w']==pytest.approx(expected,rel=1e-12,abs=1e-9)
    assert expanded[0]['baseline_rule']==INTERVAL_BASELINE_RULE


def test_expansion_withholds_missing_point_weather_endpoint():
    forecast,positions,horizon,hours=forcing(START);end=START+timedelta(minutes=5)
    row=dict(start=START.isoformat(),end=end.isoformat(),origin=(START-timedelta(hours=2)).isoformat(),baseline_w=1.,forecast_sha256='a'*64)
    del hours[forecast[0]['at']]
    assert expand_horizon_pairs([row],runs=[(START-timedelta(hours=2),'a'*64,hours,'recorded')],
        positions={p['at']:p for p in positions},array=ARRAY,horizon=horizon)==[]


@pytest.mark.parametrize('schema',['earthship-historical-pv-calibration-data/v2','earthship-pv-horizon-data/v2'])
def test_shared_baseline_validator_accepts_new_explicit_pair_families(schema):
    from historical_pv_train import validate_pair_dataset
    data=dict(schema=schema,baseline_rule=INTERVAL_BASELINE_RULE,pairs=[dict(baseline_rule=INTERVAL_BASELINE_RULE)])
    data['dataset_sha256']=identity(data)
    assert validate_pair_dataset(data,data['dataset_sha256']) is data
    data['pairs'][0]['baseline_rule']='old_next_hour_arithmetic';data['dataset_sha256']=identity({k:v for k,v in data.items() if k!='dataset_sha256'})
    with pytest.raises(ValueError,match='baseline'):validate_pair_dataset(data,data['dataset_sha256'])


def test_horizon_v1_stays_original_only_not_reinterpreted_for_new_fitting():
    from historical_pv_train import validate_pair_dataset
    data=dict(schema='earthship-pv-horizon-data/v1',baseline_rule=INTERVAL_BASELINE_RULE,pairs=[]);data['dataset_sha256']=identity(data)
    with pytest.raises(ValueError,match='baseline'):validate_pair_dataset(data,data['dataset_sha256'])
