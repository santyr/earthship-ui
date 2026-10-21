"""Chronological, matched, date-weighted atmospheric feature experiments."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import importlib,json
import pytest
from learning_fixtures import T
from weather_learning.contracts import identity,instant

POLICY=json.loads(Path('docs/operations/weathernext3-capabilities/atmospheric-ablation-protocol.json').read_text())
PROTOCOL=json.loads(Path('docs/operations/weathernext3-capabilities/evaluation-protocol.json').read_text())


def seal(row):row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'});return row

def rows(kind='temperature',days=60):
    values=[]
    for day in range(days):
        for h,dew in enumerate([-1.,1.,-2.,2.]):
            origin=T+timedelta(days=day,hours=h*4);target=origin+timedelta(hours=1)
            baseline=10. if kind=='temperature' else 70. if kind=='thermal' else 3.+h
            outcome=baseline+2*dew if kind!='wind' else baseline*.5+.5
            row=dict(schema='earthship-atmospheric-ablation-pair/v1',kind=kind,origin=origin.isoformat(),target_at=target.isoformat(),lead_hours=1.,baseline=baseline,outcome=outcome,
                base_features=[10.,1.,0.,1.,0.,1.,0.] if kind=='temperature' else [1.,0.,0.,0.,0.,0.] if kind=='thermal' else [__import__('math').log1p(baseline)],
                groups=dict(dewpoint=[dew],pressure=[1010.],wind_direction=None,cloud_layers=None),feature_sha256=identity({'feature':day,'h':h}),
                forecast_sha256=identity({'source':day}),measurement_sha256=identity({'label':day,'h':h}),outcome_available_at=(target+timedelta(days=120)).isoformat(),
                source_ready_at=(origin-timedelta(hours=1)).isoformat(),source_available_at=(T+timedelta(days=120)).isoformat(),cohort_sha256='c'*64,
                source_class='historical_assumed_availability',parent_pair_sha256=identity({'parent':day,'h':h}),automatic_actuation=False)
            values.append(seal(row))
    return values


def api():return importlib.import_module('weather_learning.atmospheric_ablation')
def fit(values=None,**kwargs):
    args=dict(rows=rows() if values is None else values,family='residual',group='dewpoint',cutoff=T+timedelta(days=30),policy=POLICY,protocol=PROTOCOL,timezone_name='UTC')
    args.update(kwargs);return api().fit_ablation(**args)


def test_training_centers_and_coefficients_exclude_future_targets():
    original=rows();model=fit(original);changed=deepcopy(original)
    for r in changed:
        if instant(r['target_at'])>=T+timedelta(days=30):r['outcome']=60.;r['groups']['dewpoint']=[60.];seal(r)
    other=fit(changed)
    for key in ('centers','scales','coefficients','intercept','training_pair_sha256s','ridge'):assert model[key]==other[key]
    assert instant(model['training_end'])<instant(model['cutoff'])<=instant(model['completed_at'])
    assert model['release_authorized'] is False and model['training_assumption']=='retrospective_target_end_order'


def test_repeated_forecasts_do_not_inflate_measured_target_support_or_weight():
    original=rows(days=20);a=fit(original)
    duplicate=deepcopy(original[40]);duplicate['parent_pair_sha256']='d'*64;duplicate['forecast_sha256']='e'*64;seal(duplicate)
    b=fit([*original,duplicate])
    assert a['support']['targets']==b['support']['targets']
    assert a['centers']==pytest.approx(b['centers']) and a['coefficients']==pytest.approx(b['coefficients'])


def test_recorded_measurements_not_available_at_the_cutoff_cannot_be_trained():
    original=rows(days=20)
    for r in original:r['source_class']='recorded_ingestion_availability';r['source_available_at']=r['source_ready_at'];seal(r)
    assert fit(original) is None


def test_outer_comparison_has_matched_support_and_no_automatic_promotion():
    report=api().assess_ablation(rows(),policy=POLICY,protocol=PROTOCOL,timezone_name='UTC')
    group=report['cohorts'][0]['comparisons']['dewpoint']
    assert group['matched']['support']['targets']>=24
    assert group['matched']['candidate']['mae']<group['matched']['baseline']['mae']*.1
    assert group['candidate_meets_score_gate'] is True and group['release_authorized'] is False
    assert group['paired_day_blocks']['independence_qualified'] is False
    for p in report['predictions']:
        if p['candidate_model_sha256'] is None:continue
        model=next(m for m in report['models'] if m['model_sha256']==p['candidate_model_sha256'])
        assert instant(model['cutoff'])+timedelta(minutes=10)<=instant(p['origin'])
        assert all(instant(r['target_at'])<instant(model['cutoff']) for r in rows() if r['pair_sha256'] in set(model['training_pair_sha256s']))


def test_absent_direction_and_cloud_evidence_remain_named_and_unfitted():
    report=api().assess_ablation(rows(days=20),policy=POLICY,protocol=PROTOCOL,timezone_name='UTC')
    for key in ('wind_direction','cloud_layers'):
        group=report['cohorts'][0]['comparisons'][key]
        assert group['disposition']=='insufficient_evidence' and group['eligible_feature_pairs']==0
        assert group['withheld']['native_feature_group_unavailable']>0
        assert group['matched']['support']['targets']==0


def test_wind_log_challenger_is_bounded_and_distinct_from_gain_only():
    values=rows(kind='wind');gain=fit(values,family='wind_gain',group=None);model=fit(values,family='wind_log',group=None)
    assert gain['method']!=model['method']
    for r in values[124:]:
        predicted=api().predict_ablation(model,r,policy=POLICY)
        assert 0<=predicted<=200
    report=api().assess_ablation(values,policy=POLICY,protocol=PROTOCOL,timezone_name='UTC')
    assert 'wind_challenger' in report['cohorts'][0]['comparisons']


def test_rehashed_future_training_or_wrong_feature_policy_is_refused():
    model=fit();model['training_end']=model['cutoff'];model['model_sha256']=identity({k:v for k,v in model.items() if k!='model_sha256'})
    with pytest.raises(ValueError):api().predict_ablation(model,rows()[150],policy=POLICY)
    model=fit();bad=deepcopy(POLICY);bad['candidates']['temperature_correction_limit_c']=100
    with pytest.raises(ValueError):api().predict_ablation(model,rows()[150],policy=bad)


def test_conflicting_target_or_mixed_cohort_cannot_enter_a_single_fit():
    original=rows(days=20);bad=deepcopy(original[0]);bad['forecast_sha256']='f'*64;bad['outcome']+=1;seal(bad)
    with pytest.raises(ValueError):fit([*original,bad])
    bad=deepcopy(original);bad[0]['cohort_sha256']='b'*64;seal(bad[0])
    with pytest.raises(ValueError):fit(bad)


def test_public_prediction_cannot_apply_later_fitted_weights_to_an_earlier_origin():
    model=fit()
    with pytest.raises(ValueError):api().predict_ablation(model,rows()[0],policy=POLICY)


def test_recorded_model_cannot_rehash_future_measurement_readiness_into_a_valid_model():
    values=rows(days=40)
    for r in values:
        r['source_class']='recorded_ingestion_availability';r['source_available_at']=r['source_ready_at'];r['outcome_available_at']=(instant(r['target_at'])+timedelta(minutes=1)).isoformat();seal(r)
    model=fit(values);assert model is not None
    model['actual_training_availability_end']=(instant(model['cutoff'])+timedelta(days=1)).isoformat();model['model_sha256']=identity({k:v for k,v in model.items() if k!='model_sha256'})
    with pytest.raises(ValueError):api().predict_ablation(model,values[-1],policy=POLICY)


def test_report_retains_the_exact_cohort_descriptor_and_target_units():
    context=dict(kind='temperature',source_class='historical_assumed_availability',measurement_quality=dict(provenance='synthetic_test'),native_grids=['a'*64],lead_stratum='1-24h')
    pin=identity(context);values=rows(days=20)
    for row in values:row['cohort_sha256']=pin;seal(row)
    report=api().assess_ablation(values,policy=POLICY,protocol=PROTOCOL,timezone_name='UTC',cohort_contexts={pin:context})
    assert report['cohorts'][0]['context']==context and report['cohorts'][0]['unit']=='degC'
    with pytest.raises(ValueError):api().assess_ablation(values,policy=POLICY,protocol=PROTOCOL,timezone_name='UTC',cohort_contexts={pin:dict(context,lead_stratum='invented')})
