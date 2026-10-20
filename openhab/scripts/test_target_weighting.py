"""Forecast density must not manufacture measured-target support or prior mass."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
import pytest
from weather_learning.contracts import identity
from weather_learning.tests.learning_fixtures import T, REVISION, pair
from test_weather_site_calibration import rows as site_rows
from test_weather_site_response import rows as weather_rows


def rehash(row):
    row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
    return row


def pv_rows(n=24):
    rows=[]
    for i in range(n):
        start=T+timedelta(days=i//8,hours=15+i%8)
        rows.append(rehash(dict(origin=(start-timedelta(hours=2)).isoformat(),start=start.isoformat(),end=(start+timedelta(hours=1)).isoformat(),baseline_w=100.,outcome_w=80.,azimuth_degrees=180.,lead_hours=2,forecast_sha256='a'*64,energy_source_sha256=identity(dict(target=start.isoformat())),potential_proxy_eligible=True)))
    return rows


def additional_origins(rows,only=None):
    out=deepcopy(rows)
    for i,r in enumerate(rows):
        if only is not None and i not in only:continue
        new=deepcopy(r);new['origin']=(__import__('datetime').datetime.fromisoformat(r['origin'])-timedelta(minutes=10)).isoformat()
        out.append(rehash(new))
    return out


def test_directional_prior_24_vs_48_distinct_forecasts_is_target_invariant():
    from weather_learning.pv_directional_calibration import fit_directional
    context=dict(cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=9))
    original=fit_directional(pv_rows(),**context);dense=fit_directional(additional_origins(pv_rows()),**context)
    assert original['sectors']['180']['gain']==pytest.approx(.9)
    assert dense['sectors']['180']['gain']==pytest.approx(.9)
    assert dense['support']['forecast_pairs']==48
    assert dense['support']['unique_measured_targets']==24
    assert dense['support']['temporal_blocks'] is None
    assert dense['support']['dependence']=='dependence_not_estimated'
    assert fit_directional(additional_origins(pv_rows(12)),**context)['sectors']['180']['supported'] is False


def test_scalar_pv_unequal_density_does_not_change_target_objective():
    from weather_learning.pv_calibration import fit_gain
    data=pv_rows(2);data[0]['outcome_w']=50.;rehash(data[0])
    context=dict(cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=9))
    assert fit_gain(data,**context)['gain']==pytest.approx(fit_gain(additional_origins(data,{0}),**context)['gain'])


def test_weather_prior_and_calendar_are_target_based():
    from weather_learning.weather_response import fit_gain
    data=weather_rows();context=dict(kind='wind_m_s',cutoff=T+timedelta(days=365),trained_at=T+timedelta(days=366))
    a=fit_gain(data,**context);b=fit_gain(additional_origins(data),**context)
    assert a['gain']==pytest.approx(b['gain'])
    assert b['support']['unique_measured_targets']==10
    assert b['timezone']=='America/Denver'
    assert b['support']['local_target_dates']==10


def test_site_ridge_weights_centers_scales_intercept_and_regularization():
    from weather_learning.site_calibration import fit_residual
    data=site_rows(3)
    for i,row in enumerate(data):row['outcome']+=i*.7;rehash(row)
    context=dict(kind='outdoor_temperature_c',cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=9),correction_limit=6.)
    a=fit_residual(data,**context);b=fit_residual(additional_origins(data,{0,1,2}),**context)
    for key in ('centers','scales','coefficients','intercept'):assert b[key]==pytest.approx(a[key])
    assert b['support']['unique_measured_targets']==9


@pytest.mark.parametrize('algorithm',['fit_bias','fit_residual'])
def test_native_temperature_target_density_invariant(algorithm):
    from weather_learning import training
    data=[pair(i,mean_c=10+i,actual_c=10+i+i*.3) for i in range(4)]
    dense=data+[replace(data[0],forecast=replace(data[0].forecast,issued_at=T+timedelta(minutes=40),issue_digest='f'*64))]
    fit=getattr(training,algorithm);context=dict(cutoff=T+timedelta(days=8),code_revision=REVISION)
    a=fit(data,**context);b=fit(dense,**context)
    for key in ('feature_centers','feature_scales','coefficients','intercept_c'):assert b[key]==pytest.approx(a[key],abs=1e-10)
    assert b['support']['unique_measured_targets']==4
    training.validate_artifact(b)


@pytest.mark.parametrize('family',['pv','weather','site'])
@pytest.mark.parametrize('change',['value','receipt'])
def test_conflicting_truth_for_same_target_is_rejected(family,change):
    if family=='pv':
        from weather_learning.pv_calibration import fit_gain as fit
        data=pv_rows(2);key='outcome_w';context={}
    elif family=='weather':
        from weather_learning.weather_response import fit_gain as fit
        data=weather_rows();key='outcome';context=dict(kind='wind_m_s')
    else:
        from weather_learning.site_calibration import fit_residual as fit
        data=site_rows(2);key='outcome';context=dict(kind='outdoor_temperature_c',correction_limit=6.)
    dense=additional_origins(data,{0})
    if change=='value':dense[-1][key]+=1
    elif family=='site':dense[-1]['label']['snapshotSha256']='f'*64
    else:dense[-1]['energy_source_sha256' if family=='pv' else 'measurement_sha256']='f'*64
    rehash(dense[-1])
    with pytest.raises(ValueError,match='conflicting.*target'):
        fit(dense,cutoff=T+timedelta(days=365),trained_at=T+timedelta(days=366),**context)


@pytest.mark.parametrize('family',['pv','weather','site'])
def test_exact_duplicates_and_mixed_known_epochs_do_not_manufacture_support(family):
    if family=='pv':
        from weather_learning.weights import pv_weights as weights
        rows=pv_rows(2)
    elif family=='weather':
        from weather_learning.weights import weather_weights as weights
        rows=weather_rows()
    else:
        from weather_learning.weights import site_weights as weights
        rows=site_rows(2)
    with pytest.raises(ValueError,match='duplicate'):weights(rows+[rows[0]])
    rows[0]['sensor_epoch']='epoch-one';rows[1]['sensor_epoch']='epoch-two'
    with pytest.raises(ValueError,match='epochs'):weights(rows)


@pytest.mark.parametrize('stamps,days',[
    (['2026-03-08T08:30:00+00:00','2026-03-08T09:30:00+00:00'],1),
    (['2026-11-01T07:30:00+00:00','2026-11-01T08:30:00+00:00'],1),
    (['2026-06-01T23:30:00-06:00','2026-06-02T05:45:00+00:00'],1),
    (['2026-06-02T05:30:00+00:00','2026-06-02T06:30:00+00:00'],2),
])
def test_weather_and_irradiance_support_calendar_is_denver(stamps,days):
    from datetime import datetime
    from weather_learning.weights import weather_weights,site_weights
    rows=[];site=[]
    for i,stamp in enumerate(stamps):
        start=datetime.fromisoformat(stamp);row=deepcopy(weather_rows()[0])
        row.update(origin=(start-timedelta(hours=1)).isoformat(),target_start=stamp,target_end=(start+timedelta(hours=1)).isoformat());rows.append(rehash(row))
        r=deepcopy(site_rows(1)[0]);r.update(kind='irradiance_w_m2',origin=row['origin'],target_at=stamp);site.append(rehash(r))
    assert weather_weights(rows)[1]['local_target_dates']==days
    assert site_weights(site)[1]['local_target_dates']==days


def test_equivalent_timestamp_spellings_share_target_mass():
    from weather_learning.weights import weather_weights
    rows=weather_rows();other=deepcopy(rows[0]);other['target_start']='2026-09-30T19:00:00-06:00';other['target_end']='2026-09-30T20:00:00-06:00';other['origin']='2026-09-30T17:00:00-06:00';rehash(other)
    weights,support=weather_weights([rows[0],other])
    assert weights==[.5,.5] and support['unique_measured_targets']==1


@pytest.mark.parametrize('kind',['wind_m_s','rain_24h_mm'])
def test_weather_holdout_metrics_weight_targets_and_keep_rain_utc24h(kind):
    from weather_learning.weather_response import fit_gain,evaluate_gain
    from datetime import datetime
    rows=weather_rows()
    for i,row in enumerate(rows):
        row['kind']=kind;row['outcome']=1.+i*.1
        if kind=='rain_24h_mm':row['target_end']=(datetime.fromisoformat(row['target_start'])+timedelta(hours=24)).isoformat()
        rehash(row)
    cutoff=datetime.fromisoformat(rows[4]['origin']);context=dict(kind=kind,cutoff=cutoff,trained_at=cutoff)
    model=fit_gain(rows,**context);end=cutoff+timedelta(days=10)
    a=evaluate_gain(model,rows,start=cutoff,end=end)
    b=evaluate_gain(model,additional_origins(rows,{6,7}),start=cutoff,end=end)
    for key in ('baseline','candidate'):
        for metric in ('mae','rmse','bias'):assert b[key][metric]==pytest.approx(a[key][metric])
    assert b['support']['unique_measured_targets']==a['support']['unique_measured_targets']


@pytest.mark.parametrize('family',['pv_scalar','pv_directional','weather','site'])
def test_old_models_predict_original_coefficients_but_do_not_noop_new_fits(family):
    if family.startswith('pv'):
        from weather_learning import pv_calibration as scalar,pv_directional_calibration as directional,pv_refresh
        module=scalar if family=='pv_scalar' else directional;fit=module.fit_gain if module is scalar else module.fit_directional
        rows=pv_rows();context=dict(cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=9))
        current=fit(rows,**context);old=deepcopy(current);old['schema']=current['schema'].replace('/v3','/v2');old.pop('support')
        if module is scalar:old['gain']=.87654321
        else:
            for sector in old['sectors'].values():sector.pop('support')
            old['sectors']['180']['gain']=.87654321
        old['model_sha256']=identity({k:v for k,v in old.items() if k!='model_sha256'})
        refresh=pv_refresh.effective_if_changed if module is scalar else pv_refresh.directional_if_changed
        value,executed=refresh(old,rows,**context)
        assert executed and value['schema'].endswith('/v3')
        prediction=scalar.calibrated_power(old,1234.,origin=context['trained_at']) if module is scalar else directional.project_power(old,1234.,azimuth_degrees=180.,origin=context['trained_at'])
        assert prediction==1234.*.87654321
    else:
        from weather_learning import training_cache,site_calibration,weather_response
        weather=family=='weather';rows=weather_rows() if weather else site_rows(3)
        context=dict(kind='wind_m_s' if weather else 'outdoor_temperature_c',cutoff=T+timedelta(days=365),trained_at=T+timedelta(days=366))
        if not weather:context['correction_limit']=6.
        fit=weather_response.fit_gain if weather else site_calibration.fit_residual
        current=fit(rows,**context);old=deepcopy(current);old['schema']=current['schema'].replace('/v2','/v1');old.pop('support')
        if weather:
            old.pop('prior_targets');old.pop('timezone');old['rule']='bounded_gain_with_unchanged_physics_prior_v1';old['gain']=.87654321
        else:old['rule']='standardized_ridge_residual_v1';old['intercept']=1.23456789
        old['model_sha256']=identity({k:v for k,v in old.items() if k!='model_sha256'})
        refresh=training_cache.gain_if_changed if weather else training_cache.residual_if_changed
        value,executed=refresh(old,rows,**context)
        assert executed and value['schema'].endswith('/v2')
        if weather:assert weather_response.predict_gain(old,1234.,origin=context['trained_at'])==1234.*.87654321
        else:
            assert site_calibration.predict(old,dict(zip(old['feature_names'],old['centers'])),baseline=10.,origin=context['trained_at'])==10.+1.23456789
    unchanged,executed=refresh(current,rows,**context)
    assert not executed and unchanged==current


@pytest.mark.parametrize('algorithm',['fit_bias','fit_residual'])
def test_legacy_typed_temperature_coefficients_replay_unchanged(algorithm):
    from weather_learning import training
    from weather_learning.tests.learning_fixtures import EPOCH
    current=getattr(training,algorithm)([pair(i) for i in range(4)],cutoff=T+timedelta(days=8),code_revision=REVISION)
    old=deepcopy(current);old['schema']='earthship-weathernext-temperature-model/v1';old.pop('support');old['intercept_c']=1.23456789
    old['artifact_sha256']=identity({k:v for k,v in old.items() if k!='artifact_sha256'})
    expected=training._predict(old,pair(10).forecast,sensor_epoch=EPOCH)
    assert training.predict(old,pair(10).forecast,sensor_epoch=EPOCH)==expected


def test_pv_comparisons_do_not_select_24_pairs_from_12_targets():
    from weather_learning.pv_calibration import fit_gain,assess_gain
    from weather_learning.pv_directional_calibration import fit_directional,assess_directional
    from weather_learning.pv_refresh import compare_incumbent
    training=pv_rows(24);cutoff=T+timedelta(days=4)
    holdout=[]
    for row in pv_rows(12):
        row=deepcopy(row)
        from datetime import datetime
        for key in ('origin','start','end'):row[key]=(datetime.fromisoformat(row[key])+timedelta(days=5)).isoformat()
        holdout.append(rehash(row))
    dense=additional_origins(holdout)
    context=dict(holdout_start=cutoff,holdout_end=T+timedelta(days=12))
    for fit,assess in ((fit_gain,assess_gain),(fit_directional,assess_directional)):
        model=fit(training,cutoff=cutoff,trained_at=cutoff)
        a=assess(model,holdout,**context);b=assess(model,dense,**context)
        assert b['pairs']==24 and b['support']['unique_measured_targets']==12
        assert b['selected'] is False
        assert b['baseline_mae_w']==pytest.approx(a['baseline_mae_w'])
        assert b['candidate_mae_w']==pytest.approx(a['candidate_mae_w'])
    model=fit_directional(training,cutoff=cutoff,trained_at=cutoff)
    result=compare_incumbent(model,model,dense,**context)
    assert result['support']['unique_measured_targets']==12 and result['selected'] is False


def test_irradiance_report_uses_local_month_and_target_weighted_loss():
    from datetime import datetime
    from weather_learning import site_calibration,irradiance_learning
    training=site_rows(3)
    for row in training:row['kind']='irradiance_w_m2';rehash(row)
    cutoff=T+timedelta(days=4)
    model=site_calibration.fit_residual(training,kind='irradiance_w_m2',cutoff=cutoff,trained_at=cutoff,correction_limit=6.)
    holdout=[]
    for i,stamp in enumerate(('2026-02-01T05:30:00+00:00','2026-02-01T06:30:00+00:00')):
        target=datetime.fromisoformat(stamp);row=deepcopy(training[i])
        row.update(origin=(target-timedelta(hours=1)).isoformat(),target_at=stamp,outcome=15.+i,
            features=dict(google_c=10.,lead_days=1.,azimuth_degrees=180.),label=dict(quality='legacy_numeric_without_sensor_receipts'))
        holdout.append(rehash(row))
    # Freeze the additional feature in a legitimate fresh model.
    for row in training:row['features']['azimuth_degrees']=180.;rehash(row)
    model=site_calibration.fit_residual(training,kind='irradiance_w_m2',cutoff=cutoff,trained_at=cutoff,correction_limit=6.)
    context=dict(holdout_start=cutoff,holdout_end=T+timedelta(days=40))
    a=irradiance_learning.assess_irradiance(model,holdout,**context)
    b=irradiance_learning.assess_irradiance(model,additional_origins(holdout,{0}),**context)
    assert b['support']['unique_measured_targets']==2 and b['support']['local_target_dates']==1
    assert set(b['by_month'])=={'2026-01'}
    for key in ('baseline','candidate'):
        for metric in ('mae','rmse','bias'):assert a[key][metric]==pytest.approx(b[key][metric])


def test_new_pv_source_requires_original_weights_runtime(tmp_path):
    import json
    from test_weather_pv_calibration_source import source
    from weather_learning.contracts import canonical
    load,path,now=source(tmp_path);receipt=json.loads(path.read_bytes())
    receipt['runtime_manifest'].pop('openhab/scripts/weather_learning/weights.py')
    receipt['receipt_sha256']=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'});path.write_bytes(canonical(receipt))
    with pytest.raises(ValueError,match='numerical runtime'):load(path,origin=now,system_raw=b'{}',horizon_raw=b'{}')


def test_typed_target_offset_spelling_cannot_add_target_support():
    from datetime import timezone
    from weather_learning.training import fit_bias,validate_artifact
    sample=pair(0)
    shifted=sample.outcome.target_at.astimezone(timezone(timedelta(hours=-7)))
    other=replace(sample,forecast=replace(sample.forecast,issued_at=T+timedelta(minutes=40),issue_digest='f'*64,target_at=shifted),
        outcome=replace(sample.outcome,target_at=shifted))
    model=fit_bias([sample,other],cutoff=T+timedelta(days=8),code_revision=REVISION)
    assert model['support']['unique_measured_targets']==1
    validate_artifact(model)
