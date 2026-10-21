"""Physical component inputs must not reuse proxy or electrical response weights."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import importlib,json
import pytest
from native_solar_fixtures import T,SITE,HORIZON,snapshot,geometry
from weather_learning.native_forecast import make_native_component_forecast
from weather_learning.contracts import identity

ROOT=Path(__file__).resolve().parents[4]
POLICY=json.loads((ROOT/'docs/operations/weathernext3-capabilities/thermal-solar-protocol.json').read_text())
PROTOCOL=json.loads((ROOT/'docs/operations/weathernext3-capabilities/evaluation-protocol.json').read_text())
ORIGIN=T+timedelta(hours=1)
def api():return importlib.import_module('weather_learning.thermal_solar_experiment')
def state(**kwargs):return dict(air_f=70.,north_wall_f=72.,indoor_shade_closed=0.,outdoor_shade_present=0.,vent_open=1.,passive_fit_allowed=True,**kwargs)
def features(**kwargs):
    args=dict(forcing=make_native_component_forecast(snapshot(hours=8),origin=ORIGIN,horizon_hours=1,available_by=ORIGIN,site=SITE),
        positions=geometry(count=36),origin_state=state(),origin=ORIGIN,horizon_hours=1,horizon_profile=HORIZON,policy=POLICY)
    args.update(kwargs);return api().component_features(**args)


def test_component_features_preserve_horizontal_units_without_an_electrical_gain():
    r=features()
    assert r['features']==pytest.approx([1.,-1/12,1/12,.3,.2,-1/12])
    assert r['native_supported'] is True
    assert r['prediction_target']=='measured_indoor_air_temperature_change_F'
    assert r['uses_pv_electrical_correction'] is False and r['physical_calibration_qualified'] is False


def test_terrain_blocks_beam_but_keeps_diffuse_and_nominal_shade_prior():
    horizon=[dict(azimuth_degrees=i*7.5,elevation_degrees=35.) for i in range(48)]
    s=state();s['indoor_shade_closed']=1.
    r=features(horizon_profile=horizon,origin_state=s)
    assert r['features'][3]==0 and r['features'][4]==pytest.approx(.07)


def test_total_only_benchmark_has_a_distinct_feature_contract_and_named_fallback():
    a=features();b=features(force_total_only=True)
    assert b['method']!=a['method'] and b['features'][3]!=pytest.approx(a['features'][3])
    assert b['features'][3]+b['features'][4]==pytest.approx(.5)
    f=make_native_component_forecast(snapshot(direct_j=None),origin=ORIGIN,horizon_hours=1,available_by=ORIGIN,site=SITE)
    r=features(forcing=f)
    assert r['features']==pytest.approx(b['features']) and r['native_supported'] is False


def sample_rows():
    rows={}
    for i in range(13):rows[(ORIGIN+timedelta(minutes=5*i)).isoformat()]=dict(state(),at=(ORIGIN+timedelta(minutes=5*i)).isoformat())
    return rows


def test_recorded_future_action_is_only_an_exclusion_and_does_not_enter_features():
    samples=sample_rows();target=ORIGIN+timedelta(hours=1)
    assert api().eligible_window(samples,origin=ORIGIN,target=target,barriers=(),late_intervals=())==(True,None)
    samples[(ORIGIN+timedelta(minutes=30)).isoformat()]['vent_open']=0.
    assert api().eligible_window(samples,origin=ORIGIN,target=target,barriers=(),late_intervals=())==(False,'changed_actions')
    assert features()['features']==pytest.approx([1.,-1/12,1/12,.3,.2,-1/12])


@pytest.mark.parametrize('damage',['missing','passive','late','barrier'])
def test_incomplete_or_retroactively_known_actions_cannot_count_as_matched_support(damage):
    samples=sample_rows();barriers=();late=()
    at=ORIGIN+timedelta(minutes=30)
    if damage=='missing':del samples[at.isoformat()]
    if damage=='passive':samples[at.isoformat()]['passive_fit_allowed']=False
    if damage=='late':late=((ORIGIN-timedelta(hours=1),ORIGIN+timedelta(hours=1)),)
    if damage=='barrier':barriers=(at,)
    assert api().eligible_window(samples,origin=ORIGIN,target=ORIGIN+timedelta(hours=1),barriers=barriers,late_intervals=late)[0] is False


def response_rows():
    result=[]
    for day in range(7):
        for i in range(20):
            origin=T+timedelta(days=day,minutes=15*i);target=origin+timedelta(hours=1)
            features=[1.,(-3+i%6)/10,(i%5)/10,(i%7)/20,(i%3)/20,(i%4-2)/10]
            change=sum(a*b for a,b in zip(features,[.1,.3,.2,5.,3.,.4]))
            row=dict(origin=origin.isoformat(),target_at=target.isoformat(),lead_hours=1,origin_air_f=70.,outcome_f=70+change,
                native_features=features,total_features=[*features[:3],features[3]*.7,features[4]*1.4,features[5]],native_supported=True,
                origin_actions=[0.,1.,0.],forecast_sha256=identity(('forecast',day)),measurement_sha256=identity(('measurement',day,i)),
                cohort_sha256='c'*64,available_at=(target+timedelta(days=20)).isoformat(),feature_policy_sha256=identity(POLICY))
            row['pair_sha256']=identity(row);result.append(row)
    return result


def fit(values=None,**kwargs):
    args=dict(method='native',cutoff=T+timedelta(days=4),fitted_at=T+timedelta(days=30),policy=POLICY,protocol=PROTOCOL)
    args.update(kwargs);return api().fit_response(response_rows() if values is None else values,**args)


def test_distinct_response_model_fits_measured_air_without_reusing_proxy_weights():
    model=fit();r=response_rows()[3]
    assert model['prediction_target']=='measured_indoor_air_temperature_change_F'
    assert api().predict_response(model,features=r['native_features'],origin_air_f=70.,policy=POLICY)==pytest.approx(r['outcome_f'],abs=.15)
    assert all(lo<=v<=hi for lo,v,hi in zip(POLICY['coefficient_lower'],model['coefficients'],POLICY['coefficient_upper']))
    assert model['physical_calibration_qualified'] is False and model['release_authorized'] is False
    total=fit(method='total')
    assert total['method']!=model['method'] and total['model_sha256']!=model['model_sha256']


def test_response_fit_and_inner_choice_exclude_targets_after_the_cutoff():
    rows=response_rows();a=fit(rows)
    for r in rows:
        if r['target_at']>=(T+timedelta(days=4)).isoformat():
            r['outcome_f']=90.;r['pair_sha256']=identity({k:v for k,v in r.items() if k!='pair_sha256'})
    b=fit(rows)
    assert a==b and a['training_end']<(T+timedelta(days=4)).isoformat()


def test_sparse_response_training_cannot_produce_a_qualified_model():
    assert fit(response_rows()[:20]) is None
    rows=response_rows();rows[-1]['cohort_sha256']='d'*64
    rows[-1]['pair_sha256']=identity({k:v for k,v in rows[-1].items() if k!='pair_sha256'})
    with pytest.raises(ValueError):fit(rows)


def test_fitted_response_cannot_be_rehashed_to_change_target_or_coefficient_bounds():
    model=fit();model['coefficients'][3]=1000;model['model_sha256']=identity({k:v for k,v in model.items() if k!='model_sha256'})
    with pytest.raises(ValueError):api().predict_response(model,features=[1,0,0,.1,.1,0],origin_air_f=70,policy=POLICY)


def test_response_assessment_keeps_forecasts_for_one_measured_target_together():
    rows=response_rows();a=api().assess_response(rows,timezone_name='UTC',policy=POLICY,protocol=PROTOCOL)
    doubled=[]
    for r in rows:
        second=deepcopy(r);second['forecast_sha256']=identity(('alternate',r['forecast_sha256']));second['pair_sha256']=identity({k:v for k,v in second.items() if k!='pair_sha256'});doubled.extend([r,second])
    b=api().assess_response(doubled,timezone_name='UTC',policy=POLICY,protocol=PROTOCOL)
    x=a['horizons']['1'];y=b['horizons']['1']
    assert x['support']['targets']==y['support']['targets']==60
    assert y['support']['forecast_pairs']==120
    assert y['fallback_inclusive']['native']['mae_c']==pytest.approx(x['fallback_inclusive']['native']['mae_c'],abs=1e-10)
    assert b['automatic_promotion'] is False and b['prospective_score'] is False
    assert all(m['training_end']<m['cutoff'] for m in b['models'])


def test_real_response_fit_records_its_actual_completion_clock():
    from datetime import datetime,timezone
    before=datetime.now(timezone.utc)
    model=fit(fitted_at=None)
    after=datetime.now(timezone.utc)
    assert before<=datetime.fromisoformat(model['fitted_at'])<=after


@pytest.mark.parametrize('changes',[{'training_end':(T+timedelta(days=5)).isoformat()},{'physical_calibration_qualified':True}])
def test_rehashed_response_model_cannot_claim_future_training_or_physical_qualification(changes):
    model=fit();model.update(changes);model['model_sha256']=identity({k:v for k,v in model.items() if k!='model_sha256'})
    with pytest.raises(ValueError):api().predict_response(model,features=[1,0,0,.1,.1,0],origin_air_f=70,policy=POLICY)
