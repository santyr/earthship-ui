"""Frozen marginal kernels preserve availability, source cohorts and atom zeros."""
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import importlib.util,json,math
import pytest
from learning_fixtures import T

POLICY=json.loads(Path('docs/operations/weathernext3-capabilities/marginal-calibration-protocol.json').read_text())


def api():
    assert importlib.util.find_spec('weather_learning.probabilistic'), 'Task7 bounded marginal kernels missing'
    from weather_learning import probabilistic
    return probabilistic


def frame(day=0,hour=0,kind='temperature',**kwargs):
    m=api();origin=T+timedelta(days=day,hours=9+hour*4);end=origin+timedelta(hours=1)
    baseline=10. if kind=='temperature' else 0. if hour==0 else float(hour*(100 if kind=='solar_proxy' else 2))
    args=dict(kind=kind,origin=origin.isoformat(),initialized_at=(origin-timedelta(hours=9)).isoformat(),
        target_start=(end if kind=='temperature' else origin).isoformat(),target_end=end.isoformat(),baseline=baseline,
        incumbent=None,incumbent_sha256=None,p10=baseline-2 if kind=='temperature' else None,p50=None,p90=baseline+2 if kind=='temperature' else None,
        source_ready_at=(origin-timedelta(hours=1)).isoformat(),actual_source_available_at=(origin-timedelta(hours=1)).isoformat(),
        availability_basis='recorded_ingestion_availability',forecast_sha256=f'{day*4+hour:064x}',grid_sha256='a'*64,cohort_sha256='b'*64,timezone='America/Denver')
    args.update(kwargs);return m.ForecastInput(**args)


def pairs(kind='temperature',days=20):
    m=api();values=[]
    for d in range(days):
        for h in range(4):
            f=frame(d,h,kind);at=T+timedelta(days=d,hours=10+h*4)
            y=12+.2*math.sin(h) if kind=='temperature' else 0. if h==0 else f.baseline*.7+2 if kind=='solar_proxy' else f.baseline*.5+.2
            values.append(m.CalibrationPair(forecast=f,value=y,outcome_ready_at=(at+timedelta(minutes=2)).isoformat(),
                actual_outcome_available_at=(at+timedelta(minutes=2)).isoformat(),receipt_sha256=f'{1000+d*4+h:064x}'))
    return values


def fit(values=None,family='temperature_normal',**kwargs):
    args=dict(rows=pairs() if values is None else values,family=family,cutoff=T+timedelta(days=15),
        completed_at=T+timedelta(days=15,minutes=1),policy=POLICY,ridge=.1)
    args.update(kwargs);return api().fit_marginal(**args)


def test_past_only_training_ignores_future_outcome_changes_and_retains_membership():
    original=pairs();a=fit(original);changed=[replace(p,value=50.) if p.forecast.origin>= (T+timedelta(days=15)).isoformat() else p for p in original]
    b=fit(changed)
    assert a.to_dict()==b.to_dict()
    assert a.to_dict()['support']==dict(pairs=60,targets=60,local_dates=15)
    assert len(a.to_dict()['training_pair_sha256s'])==60
    assert a.to_dict()['actual_completed_at']<frame(15).origin


def test_temperature_location_scale_is_bounded_and_model_median_is_not_native():
    model=fit();prediction=api().predict_marginal(model,frame(15),policy=POLICY).to_dict()
    assert prediction['distribution']=='normal'
    assert prediction['mean']==pytest.approx(12,abs=.3)
    assert .25<=prediction['parameters']['sigma']<=20
    assert prediction['raw_native']['p50'] is None
    assert prediction['median_source']=='local_model_generated'
    assert prediction['local_coverage_qualified'] is False and prediction['issued'] is False
    assert prediction['quantiles']==sorted(prediction['quantiles'])


def test_native_zero_width_is_a_predictor_not_division_by_ensemble_variance():
    rows=[replace(p,forecast=replace(p.forecast,p10=10.,p90=10.)) for p in pairs()]
    model=fit(rows);prediction=api().predict_marginal(model,frame(15,p10=10.,p90=10.),policy=POLICY).to_dict()
    assert all(math.isfinite(q) for q in prediction['quantiles'])
    assert prediction['quantiles'][-1]>prediction['quantiles'][0]
    assert prediction['raw_native']['p10']==prediction['raw_native']['p90']==10


def test_missing_or_crossing_native_statistics_refuse_scale_family_without_sorting():
    assert fit([replace(p,forecast=replace(p.forecast,p10=None,p90=None)) for p in pairs()]) is None
    assert fit([replace(p,forecast=replace(p.forecast,p10=12.,p90=8.)) for p in pairs()]) is None
    model=fit();assert api().predict_marginal(model,frame(15,p10=12,p90=8),policy=POLICY) is None


def test_empirical_benchmark_remains_usable_without_native_statistics_and_avoids_certainty():
    rows=[replace(p,forecast=replace(p.forecast,p10=None,p90=None),value=10.) for p in pairs()]
    model=fit(rows,family='empirical')
    value=api().predict_marginal(model,frame(15,p10=None,p90=None),policy=POLICY).to_dict()
    assert value['distribution']=='empirical_residual_quantiles'
    assert value['quantiles'][0]<=9.75 and value['quantiles'][-1]>=10.25
    assert value['raw_native']['p50'] is None and value['median_source']=='local_model_generated'


@pytest.mark.parametrize('kind',['solar_proxy','wind'])
def test_nonnegative_family_has_explicit_zero_atom_and_positive_tail(kind):
    model=fit(pairs(kind),family='nonnegative')
    value=api().predict_marginal(model,frame(15,0,kind),policy=POLICY).to_dict()
    assert value['distribution']=='zero_atom_plus_positive_log1p_normal'
    assert .005<=value['parameters']['zero_probability']<=.995
    assert all(0<=q for q in value['quantiles'])
    assert value['quantiles']==sorted(value['quantiles'])
    assert api().prediction_cdf(value,0)==pytest.approx(value['parameters']['zero_probability'])
    assert api().prediction_cdf(value,-1)==0
    assert value['mean']>=0


def test_all_zero_positive_target_does_not_invent_a_supported_positive_component():
    assert fit([replace(p,value=0.) for p in pairs('wind')],family='nonnegative') is None


def test_model_and_prediction_are_immutable_and_scoring_does_not_refit():
    model=fit();saved=model.to_dict();saved['parameters'][0]=99
    assert model.to_dict()['parameters'][0]!=99
    with pytest.raises(AttributeError):model.parameters=[]
    prediction=api().predict_marginal(model,frame(15),policy=POLICY)
    first=prediction.to_dict();first['quantiles'][0]=99
    assert prediction.to_dict()['quantiles'][0]!=99
    y=prediction.to_dict()['quantiles'][0]
    scored=api().score_marginal(prediction,y)
    assert scored['covered_80'] is True
    assert scored['wis'] is not None and scored['crps'] is not None
    assert model.to_dict()['parameters']!=saved['parameters']


def test_recorded_availability_and_model_readiness_cannot_be_backdated():
    with pytest.raises(ValueError,match='availability'):
        frame(actual_source_available_at=(T+timedelta(days=1)).isoformat())
    model=fit(completed_at=T+timedelta(days=16))
    assert api().predict_marginal(model,frame(15),policy=POLICY) is None
    rows=[replace(p,outcome_ready_at=(T+timedelta(days=30)).isoformat(),actual_outcome_available_at=(T+timedelta(days=30)).isoformat()) for p in pairs()]
    assert fit(rows) is None


def test_future_cohort_and_changed_observation_do_not_pool_or_inflate_support():
    values=pairs();other=replace(values[0],forecast=replace(values[0].forecast,cohort_sha256='c'*64))
    with pytest.raises(ValueError,match='cohort'):fit([*values,other])
    with pytest.raises(ValueError,match='conflicting'):fit([*values,replace(values[0],value=13.)])
    duplicate=replace(values[0],forecast=replace(values[0].forecast,forecast_sha256='d'*64))
    a=fit(values);b=fit([*values,duplicate])
    assert a.to_dict()['support']['targets']==b.to_dict()['support']['targets']
    assert a.to_dict()['parameters']==pytest.approx(b.to_dict()['parameters'],abs=1e-6)


def test_adaptive_state_is_past_only_bounded_and_has_cold_and_expired_fallbacks():
    m=api();state=m.fit_adaptive(pairs(),cutoff=T+timedelta(days=15),completed_at=T+timedelta(days=15,minutes=1),half_life_hours=24,policy=POLICY)
    active=m.adaptive_point(state,frame(15),policy=POLICY)
    assert 10<active['value']<=16 and active['candidate_used'] is True
    assert m.fit_adaptive(pairs(days=2),cutoff=T+timedelta(days=15),completed_at=T+timedelta(days=15,minutes=1),half_life_hours=24,policy=POLICY) is None
    fallback=m.adaptive_point(state,frame(20,incumbent=12.5,incumbent_sha256='e'*64),policy=POLICY)
    assert fallback['value']==12.5 and fallback['candidate_used'] is False
    cold=m.adaptive_point(None,frame(15),policy=POLICY)
    assert cold['value']==10 and cold['candidate_used'] is False


def test_retrospective_ready_clocks_never_qualify_as_a_live_fitted_artifact():
    model=fit(retrospective=True,completed_at=T+timedelta(days=40))
    assert api().predict_marginal(model,frame(15),policy=POLICY) is None
    assert api().predict_marginal(model,frame(15),policy=POLICY,retrospective=True) is not None
    assert model.to_dict()['retrospective_only'] is True


def test_saved_model_source_mismatch_is_rejected_without_relabeling_weights():
    m=api();value=fit().to_dict();value.pop('model_sha256');value['numerical_producer_sha256']='f'*64
    changed=m._freeze(m.CalibrationModel,value,'model_sha256')
    with pytest.raises(ValueError,match='numerical'):
        m.predict_marginal(changed,frame(15),policy=POLICY)


def test_outside_declared_training_domain_is_rejected():
    values=pairs();values[0]=replace(values[0],value=100.)
    with pytest.raises(ValueError,match='domain'):fit(values)


def test_positive_marginal_inverse_cdf_matches_zero_atom_and_continuous_tail():
    model=fit(pairs('wind'),family='nonnegative')
    for h in (0,1,3):
        prediction=api().predict_marginal(model,frame(15,h,'wind'),policy=POLICY).to_dict()
        for p,q in zip(prediction['quantile_levels'],prediction['quantiles']):
            cdf=api().prediction_cdf(prediction,q)
            assert cdf>=p-1e-7 if q==0 else cdf==pytest.approx(p,abs=1e-7)


def test_empirical_quantiles_expose_a_point_median_without_claiming_a_distribution_mean():
    value=api().predict_marginal(fit(family='empirical'),frame(15),policy=POLICY).to_dict()
    assert value['mean'] is None
    assert value['point_estimate']==value['quantiles'][2]
    assert value['point_estimate_kind']=='model_median'


def test_multiple_original_versions_at_one_origin_do_not_double_its_target_weight():
    first=pairs()[0]
    earlier=replace(first,forecast=replace(first.forecast,origin=(T+timedelta(hours=8)).isoformat(),forecast_sha256='d'*64))
    alternate=replace(first,forecast=replace(first.forecast,forecast_sha256='e'*64))
    assert api()._weights([first,earlier,alternate])==pytest.approx([.25,.5,.25])


@pytest.mark.parametrize('operation',['fit_adaptive','predict_marginal','adaptive_point'])
def test_retrospective_permission_requires_a_boolean_not_a_truthy_string(operation):
    m=api()
    with pytest.raises(ValueError,match='boolean|context'):
        if operation=='fit_adaptive':
            m.fit_adaptive(pairs(),cutoff=T+timedelta(days=15),half_life_hours=24,policy=POLICY,retrospective='false')
        elif operation=='predict_marginal':m.predict_marginal(fit(retrospective=True),frame(15),policy=POLICY,retrospective='false')
        else:
            model=m.fit_adaptive(pairs(),cutoff=T+timedelta(days=15),half_life_hours=24,policy=POLICY,retrospective=True)
            m.adaptive_point(model,frame(15),policy=POLICY,retrospective='false')
