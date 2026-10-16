"""Compare as-issued captured DC scenarios, never potential yield to curtailed PV."""
from copy import deepcopy
from datetime import timedelta
import importlib,json
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from test_household_energy_forecast import fixture,originals
from test_household_pv_window import raw


def context(tmp_path,monkeypatch,originals,*,sparse=False):
    energy_api,args,plan=fixture(tmp_path,monkeypatch,originals);energy=energy_api.seal_energy_forecast(**args)
    issue=instant(energy['output']['array_pv']['origin']);target=issue+timedelta(hours=1);epoch=plan['inputs']['snapshot']['domains']['energy']['pv_output_power_w']['evidence']['source_epoch']
    from household_pv_window import build_hour_source
    offsets=range(0,3600,60) if not sparse else (0,)
    rows=[(issue+timedelta(seconds=s),raw(issue+timedelta(seconds=s),i+1,1000,epoch)) for i,s in enumerate(offsets)]
    policy=json.dumps(dict(version=1,policy='qualified_power_evidence_v1',item_name='Power_Evidence_JSON',cutover=(issue-timedelta(days=1)).isoformat()))
    source=build_hour_source(rows=rows,start=issue,end=target,requested_at=target+timedelta(minutes=5),received_at=target+timedelta(minutes=5,seconds=1),item_id=612,policy_raw=policy)
    api=importlib.import_module('household_pv_outcomes')
    return api,dict(energy_receipt=energy,plan_receipt=plan,hour_sources={'1':source},assessed_at=target+timedelta(minutes=6),runtime_manifest=api.outcome_runtime_manifest(),energy_runtime_manifest=energy_api.forecast_runtime_manifest())


def test_matched_controller_hour_scores_captured_forecast_and_persistence_not_potential(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals);before=canonical(args['energy_receipt']);value=api.seal_pv_outcomes(**args);row=value['output']['by_horizon']['1']
    assert row['status']=='scored' and row['actual_known_controller_dc_kwh']==pytest.approx(1)
    captured=args['energy_receipt']['output']['nominal_storage']['trajectory'][0]['cumulative_modeled_captured_pv_kwh']
    assert row['predictions_kwh']['constant_load_pv']==pytest.approx(captured)
    assert row['predictions_kwh']['current_pv']==pytest.approx(args['energy_receipt']['output']['current_flows']['pv_controller_output_w']/1000)
    assert row['errors_kwh']['constant_load_pv']==pytest.approx(captured-1)
    assert value['output']['by_horizon']['6']['status']=='not_mature'
    assert value['output']['potential_array_accuracy']=='unavailable_unmatched_meter_scope'
    assert value['output']['physical_calibration_qualified'] is False and value['output']['automatic_actuation'] is False
    assert canonical(args['energy_receipt'])==before
    assert api.replay_pv_outcomes(value,**{k:v for k,v in args.items() if k not in ('hour_sources','assessed_at')})==value


def test_sparse_hour_keeps_coverage_but_does_not_publish_accuracy(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals,sparse=True);row=api.seal_pv_outcomes(**args)['output']['by_horizon']['1']
    assert row['status']=='insufficient_coverage' and row['covered_seconds']==120
    assert row['actual_known_controller_dc_kwh']==pytest.approx(1/30)
    assert row['errors_kwh'] is None and row['predictions_kwh'] is None


def test_both_frozen_hourly_means_use_exact_same_observed_duration(tmp_path,monkeypatch,originals):
    from household_pv_window import build_hour_source
    api,args=context(tmp_path,monkeypatch,originals);source=args['hour_sources']['1'];start=instant(source['window_start']);end=instant(source['window_end'])
    # A final invalidation creates a ten-second gap. Neither model gets full-hour credit.
    rows=[(instant(at),value) for at,value in source['rows']]+[(end-timedelta(seconds=10),'invalid')]
    args['hour_sources']['1']=build_hour_source(rows=rows,start=start,end=end,requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),item_id=612,policy_raw=source['policy_raw'])
    value=api.seal_pv_outcomes(**args);row=value['output']['by_horizon']['1'];captured=args['energy_receipt']['output']['nominal_storage']['trajectory'][0]['cumulative_modeled_captured_pv_kwh']
    assert row['covered_seconds']==3590 and row['actual_known_controller_dc_kwh']==pytest.approx(3590/3600)
    assert row['predictions_kwh']['constant_load_pv']==pytest.approx(captured*3590/3600)
    assert row['predictions_kwh']['current_pv']==pytest.approx(args['energy_receipt']['output']['current_flows']['pv_controller_output_w']*3590/3600000)


@pytest.mark.parametrize('damage',['source','output','forecast','plan','runtime','immature','future_source'])
def test_resealed_changed_or_unavailable_originals_cannot_become_a_score(tmp_path,monkeypatch,originals,damage):
    api,args=context(tmp_path,monkeypatch,originals);score=api.seal_pv_outcomes(**args)
    if damage=='source':score['inputs']['hour_sources']['1']['rows'][0][1]='changed'
    elif damage=='output':score['output']['by_horizon']['1']['errors_kwh']['current_pv']=0
    elif damage=='forecast':args['energy_receipt']['output']['nominal_storage']['trajectory'][0]['cumulative_modeled_captured_pv_kwh']+=1
    elif damage=='plan':args['plan_receipt']['inputs']['now']=(instant(args['plan_receipt']['inputs']['now'])+timedelta(seconds=1)).isoformat()
    elif damage=='runtime':args['runtime_manifest']=dict(args['runtime_manifest']);args['runtime_manifest'][next(iter(args['runtime_manifest']))]='f'*64
    elif damage=='immature':score['inputs']['assessed_at']=(args['assessed_at']-timedelta(minutes=2)).isoformat()
    else:score['inputs']['hour_sources']['1']['received_at']=(args['assessed_at']+timedelta(seconds=1)).isoformat()
    score['receipt_sha256']=identity({k:v for k,v in score.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):api.replay_pv_outcomes(score,**{k:v for k,v in args.items() if k not in ('hour_sources','assessed_at')})


def test_report_deduplicates_originals_and_keeps_counts_and_days_explicit(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals);score=api.seal_pv_outcomes(**args)
    report=api.build_performance([score,score],cohort=score['output']['cohort'],generated_at=args['assessed_at'],next_mature_at=None)
    row=report['by_horizon']['1']['models']['constant_load_pv']
    assert row['count']==1 and row['unique_origin_days']==1
    assert row['mae_kwh']==pytest.approx(abs(score['output']['by_horizon']['1']['errors_kwh']['constant_load_pv']))
    assert report['by_horizon']['6']['models']['constant_load_pv']['count']==0
    assert report['by_horizon']['6']['models']['constant_load_pv']['mae_kwh'] is None
    assert report['graduated'] is False


def test_original_learned_load_scenario_is_compared_on_the_same_controller_hour(tmp_path,monkeypatch,originals):
    from test_household_profiled_forecast import supported_source
    from household_profiled_forecast import seal_profiled_forecast,profiled_runtime_manifest
    api,args=context(tmp_path,monkeypatch,originals);energy=args['energy_receipt'];issue=instant(energy['output']['array_pv']['origin']);source,lr=supported_source(issue)
    profile=seal_profiled_forecast(energy_receipt=energy,plan_receipt=args['plan_receipt'],load_source=source,now=instant(energy['inputs']['assessed_at']),runtime_manifest=profiled_runtime_manifest(),energy_runtime_manifest=args['energy_runtime_manifest'],load_runtime_manifest=lr)
    args.update(profiled_receipt=profile,profiled_runtime_manifest=profiled_runtime_manifest(),load_runtime_manifest=lr)
    score=api.seal_pv_outcomes(**args);row=score['output']['by_horizon']['1'];expected=profile['output']['profiled_storage']['trajectory'][0]['cumulative_modeled_captured_pv_kwh']
    assert row['predictions_kwh']['profiled_load_pv']==pytest.approx(expected)
    assert row['errors_kwh']['profiled_load_pv']==pytest.approx(expected-1)
    assert score['output']['prediction_context']['profiled_model_artifact_sha256']==source['artifact']['artifact_sha256']
    assert api.replay_pv_outcomes(score,**{k:v for k,v in args.items() if k not in ('hour_sources','assessed_at')})==score


def test_file_only_replay_requires_exact_external_originals_and_no_live_access(tmp_path,monkeypatch,originals,capsys):
    import socket
    api,args=context(tmp_path,monkeypatch,originals);score=api.seal_pv_outcomes(**args);paths={}
    for name,value in (('receipt',score),('energy',args['energy_receipt']),('plan',args['plan_receipt'])):
        path=tmp_path/(name+'.json');path.write_bytes(canonical(value));path.chmod(0o600);paths[name]=path
    monkeypatch.setattr(socket,'create_connection',lambda *a,**kw:pytest.fail('offline PV replay used network'))
    import household_capture
    monkeypatch.setattr(household_capture,'_connection',lambda *a,**kw:pytest.fail('offline PV replay read database'))
    command=[word for name,path in paths.items() for word in ('--'+name,str(path))]
    assert api.main(command)==0
    import json
    assert json.loads(capsys.readouterr().out)==score
    paths['energy'].write_bytes(b'{}')
    assert api.main(command)==1 and 'replay refused' in capsys.readouterr().err


@pytest.mark.parametrize('damage',['cohort_epoch','cohort_field','profiled_pin'])
def test_standalone_validation_refuses_resealed_provenance_mismatches(tmp_path,monkeypatch,originals,damage):
    api,args=context(tmp_path,monkeypatch,originals);score=api.seal_pv_outcomes(**args);out=score['output'];ctx=out['prediction_context']
    if damage=='cohort_epoch':ctx['cohort']['power_source_epoch']='00000000-0000-4000-8000-000000000003'
    elif damage=='cohort_field':ctx['cohort']['invented_source']='qualified'
    else:ctx['profiled_model_artifact_sha256']='f'*64
    out['cohort']=ctx['cohort'];out['cohort_id']=identity(ctx['cohort']);score['receipt_sha256']=identity({k:v for k,v in score.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):api.validate_score(score)
