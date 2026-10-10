"""Combined release decision must derive gates, never accept an active flag."""
from datetime import datetime,timezone
from hashlib import sha256

import pytest

from thermal_model.forcing_capture import _canonical


def module():
    import thermal_graduation_decision
    return thermal_graduation_decision


def test_missing_raw_training_evidence_and_registration_cannot_authorize_forecast():
    decision=module()
    report=decision.qualify_candidate(registration_path=None,artifact=None,fit_evidence_path=None,
        training_sources=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,7,tzinfo=timezone.utc))
    assert report['recommended_stage']=='unavailable'
    assert report['forecast_qualified'] is False
    assert report['advisory_qualified'] is False
    assert report['automatic_actuation_authorized'] is False
    assert report['gates']['preregistered_policy'] is False
    assert report['gates']['qualified_training_sources'] is False
    assert report['gates']['frozen_runtime'] is False
    assert report['gates']['measured_fit'] is False


def test_qualification_report_rejects_a_manual_active_override():
    decision=module()
    report=decision.qualify_candidate(registration_path=None,artifact=None,fit_evidence_path=None,
        training_sources=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,7,tzinfo=timezone.utc))
    report['forecast_qualified']=True;report['recommended_stage']='forecast_active'
    report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest()
    with pytest.raises(ValueError):decision.validate_qualification_report(report)


def test_human_report_shows_every_closed_gate_and_original_intervals():
    decision=module()
    report=decision.qualify_candidate(registration_path=None,artifact=None,fit_evidence_path=None,
        training_sources=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,7,tzinfo=timezone.utc))
    text=decision.render_qualification_report(report)
    assert 'unavailable' in text
    assert 'preregistered_policy' in text
    assert 'qualified_training_sources' in text
    assert 'measured_fit' in text
    assert 'Automatic actuation: disabled' in text


def training_case():
    from copy import deepcopy
    from types import SimpleNamespace
    from datetime import timedelta
    from thermal_model.dataset import dataset_manifest,_observe_latent_mass,_canonical_sample
    from thermal_model.temperature_history import QualifiedTemperatureHistory,STREAMS
    from thermal_model.schema import THERMAL_ITEMS
    from test_thermal_pipeline import training_samples
    from test_thermal_origin_capture import EPOCH
    samples=training_samples();start=samples[0].at;end=samples[-1].at+timedelta(minutes=5)
    raw={row.at:row for row in samples};grids={}
    def grid(stream,targets,assessed):
        role=next(role for role,identity in STREAMS.items() if identity[0]==stream)
        field={'air':'air_f','mass':'mass_f','outdoor':'outdoor_f'}[role]
        rows=[[at.isoformat(),dict(temperatureF=getattr(raw[at],field),
            receivedAt=(at-timedelta(seconds=30)).isoformat(),storedAt=at.isoformat(),
            validUntil=(at+timedelta(seconds=90)).isoformat(),streamEpoch=EPOCH,snapshotSha256='a'*64)] for at in targets]
        grids[role]=rows
        return [(at,receipt) for at,(_,receipt) in zip(targets,rows)]
    reader=QualifiedTemperatureHistory(lambda *_:[],grid,cutover=start,assessed_at=end)
    for role in STREAMS:reader(THERMAL_ITEMS[role],start,end)
    observed=_observe_latent_mass(samples);manifest=dataset_manifest(observed,[],[])
    manifest['temperature_evidence']=reader.evidence_manifest()
    source=dict(schema='earthship-thermal-training-sources/v1',
        samples=[_canonical_sample(row,'observed') for row in observed],temperature_grids=grids)
    return SimpleNamespace(data_manifest=manifest,trained_from=manifest['start'],trained_through=manifest['end']),source,{role:EPOCH for role in STREAMS}


def test_raw_training_samples_and_receipts_reproduce_frozen_input_digest():
    decision=module();artifact,source,epochs=training_case()
    result=decision.verify_training_sources(source,artifact,epochs)
    assert result['sample_count']==4
    assert result['training_inputs_sha256']==artifact.data_manifest['canonical_rows_sha256']
    assert all(role['qualified']==4 for role in result['roles'].values())


@pytest.mark.parametrize('damage',['receipt','epoch','missing','future','latent','repeated_target','summary_only'])
def test_raw_source_edits_cannot_be_replaced_by_support_summaries(damage):
    decision=module();artifact,source,epochs=training_case()
    if damage=='receipt':source['temperature_grids']['air'][0][1]['temperatureF']+=1
    elif damage=='epoch':epochs['mass']='064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    elif damage=='missing':source['temperature_grids']['air'][0][1]=None
    elif damage=='future':source['temperature_grids']['air'][0][1]['storedAt']='2027-01-01T00:00:00+00:00'
    elif damage=='latent':source['samples'][1]['mass_f']+=1
    elif damage=='repeated_target':source['temperature_grids']['air'][1][0]=source['temperature_grids']['air'][0][0]
    elif damage=='summary_only':source.pop('temperature_grids')
    with pytest.raises(ValueError):decision.verify_training_sources(source,artifact,epochs)


def classifier_case(monkeypatch,*,skill=True,fit=True):
    """Controlled component boundaries; not release evidence for a real model."""
    from copy import deepcopy
    from datetime import timedelta
    from dataclasses import asdict
    from thermal_model.graduation_policy import derive_policy
    from test_thermal_graduation_policy import inputs
    from test_thermal_origin_capture import capture_inputs,NOW
    from thermal_model.origin_capture import build_origin_capture
    import thermal_model.pipeline as pipeline
    decision=module();data=capture_inputs();artifact=data['artifact']
    record=build_origin_capture(**data)
    args=inputs();args['candidate'].update(artifact_sha256=sha256(_canonical(asdict(artifact))).hexdigest(),
        runtime_sha256=record['sha256']['runtime'],trained_through=artifact.trained_through,created_at=artifact.created_at)
    args['declared_at']='2026-08-14T00:00:00+00:00'
    args['intervals'].update(holdout_start='2026-08-15T00:00:00+00:00',holdout_end='2026-10-01T00:00:00+00:00',
        prospective_start='2026-08-15T00:00:00+00:00')
    policy=derive_policy(**args)
    monkeypatch.setattr(decision,'read_registered_policy',lambda *_:dict(policy=policy,registration_sha256='c'*64))
    monkeypatch.setattr(decision,'read_runtime_bundle',lambda *_:dict(runtime=record['runtime']))
    monkeypatch.setattr(decision,'read_fit_evidence',lambda *_:dict(fit_gates_passed=fit,active_parameter_count=12))
    monkeypatch.setattr(decision,'verify_training_sources',lambda *_:dict(sample_count=17568,training_inputs_sha256='a'*64))
    monkeypatch.setattr(decision,'read_origin_capture',lambda *_:record)
    monkeypatch.setattr(decision,'_forcing',lambda *_:'d'*64)
    row=dict(artifact_sha256=policy['candidate']['artifact_sha256'],runtime_sha256=policy['candidate']['runtime_sha256'],
        sensor_epochs=policy['candidate']['sensor_epochs'])
    assessment = NOW+timedelta(days=60)
    def score(*_args, **kwargs):
        hours = kwargs['horizon_hours']
        scored = {**row, 'issue_at': (assessment-timedelta(hours=hours+1)).isoformat(),
            'target_at': (assessment-timedelta(hours=1)).isoformat(), 'horizon_hours': hours}
        return dict(scored_pair=scored, original_capture_sha256='e'*64)
    monkeypatch.setattr(decision,'_score_origin_record',score)
    monkeypatch.setattr(decision,'assess_predictive_skill',lambda *_args,**kwargs:dict(statistical_forecast_gates_passed=skill))
    packet=dict(origin_path='private-original',publication={},horizon_hours=1,outcome={},recent_cycle_grid=[])
    return decision,dict(registration_path='private-registration',artifact=artifact,fit_evidence_path='private-fit',
        training_sources={},runtime_bundle_path='private-runtime',original_pairs=[{**packet, 'horizon_hours': hours} for hours in (1,6,12,24)],now=assessment)


def test_forecast_pass_is_independent_of_unqualified_action_advice(monkeypatch):
    decision,args=classifier_case(monkeypatch)
    report=decision.qualify_candidate(**args)
    assert report['forecast_qualified'] is True
    assert report['recommended_stage']=='forecast_active'
    assert report['advisory_qualified'] is False
    assert report['automatic_actuation_authorized'] is False


@pytest.mark.parametrize('failure',['baseline_loss','fit','raw_sources','runtime','epoch','edited_publication'])
def test_each_failed_component_closes_forecast_qualification(monkeypatch,failure):
    decision,args=classifier_case(monkeypatch,skill=failure!='baseline_loss',fit=failure!='fit')
    def refuse(*_args,**kwargs):raise ValueError('original source refusal')
    if failure=='raw_sources':monkeypatch.setattr(decision,'verify_training_sources',refuse)
    elif failure=='runtime':monkeypatch.setattr(decision,'read_runtime_bundle',refuse)
    elif failure=='epoch':args['original_pairs'][0]['origin_path']=[]
    elif failure=='edited_publication':monkeypatch.setattr(decision,'_score_origin_record',refuse)
    report=decision.qualify_candidate(**args)
    assert report['forecast_qualified'] is False
    assert report['recommended_stage'] in ('shadow','unavailable')


def test_report_retains_every_declared_threshold_and_frozen_runtime(monkeypatch):
    decision,args=classifier_case(monkeypatch)
    report=decision.qualify_candidate(**args)
    assert report['policy']['thresholds']['24']['min_independent_days']==35
    assert report['policy']['required_skill_upper_bound_f']==0
    assert report['runtime']['runtime']['source_manifest']
    assert report['policy']['candidate']==report['candidate']
    assert 'max_mae_f' in decision.render_qualification_report(report)


def forcing_case():
    from datetime import timedelta
    from test_thermal_origin_capture import NOW
    times=[NOW+timedelta(hours=index) for index in range(25)]
    return dict(issued_at=NOW.isoformat(),raw_forecast={'hourly':{
        'time':[at.isoformat() for at in times],'temperature_2m':[50]*25,
        'shortwave_radiation':[100]*25,'wind_speed_10m':[1]*25,'weather_code':[0]*25}},
        forecast_rows=[dict(at=at.isoformat(),tempF=50,radiationWm2=100,windMph=1,weatherCode=0,mode='warm') for at in times],
        output={'forecast':{'trajectory':[{'at':at.isoformat()} for at in times]}})


def test_original_weather_snapshot_and_forcing_cover_the_actual_issued_trajectory():
    decision=module();record=forcing_case()
    assert decision._forcing(record)==sha256(_canonical(record['raw_forecast'])).hexdigest()


@pytest.mark.parametrize('damage',['empty','not_hourly','length','nonfinite','short_forcing'])
def test_missing_or_malformed_original_forcing_cannot_supply_source_gate(damage):
    decision=module();record=forcing_case()
    if damage=='empty':record['raw_forecast']={}
    elif damage=='not_hourly':record['raw_forecast']={'hourly':{'fake':True}}
    elif damage=='length':record['raw_forecast']['hourly']['temperature_2m'].pop()
    elif damage=='nonfinite':record['raw_forecast']['hourly']['shortwave_radiation'][0]=float('inf')
    elif damage=='short_forcing':record['forecast_rows'].pop()
    with pytest.raises(ValueError):decision._forcing(record)


def cli_module():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).with_name('qualify-thermal-graduation.py')
    spec=importlib.util.spec_from_file_location('qualification_cli',path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


def test_cli_missing_evidence_writes_matching_private_closed_gate_reports(tmp_path,capsys):
    import json
    cli=cli_module();tmp_path.chmod(0o700)
    assert cli.main(['--report-directory',str(tmp_path)])==1
    response=json.loads(capsys.readouterr().out)
    assert response['recommended_stage']=='unavailable'
    files=list(tmp_path.glob('qualification-*'));assert len(files)==2
    data=json.loads(next(path for path in files if path.suffix=='.json').read_text())
    assert data['report_sha256']==response['report_sha256']
    text=next(path for path in files if path.suffix=='.md').read_text()
    assert text==module().render_qualification_report(data)
    assert all(path.stat().st_mode & 0o777==0o600 for path in files)
    assert cli.write_report(tmp_path,data)==response['reports']


def test_cli_refuses_unsafe_inputs_without_exposing_source_content(tmp_path,capsys):
    cli=cli_module();tmp_path.chmod(0o700)
    secret=tmp_path/'private-input.json';secret.write_text('{"private":"do-not-expose"}')
    secret.chmod(0o644)
    assert cli.main(['--report-directory',str(tmp_path),'--artifact',str(secret)])==2
    output=capsys.readouterr()
    assert 'do-not-expose' not in output.err+output.out
    assert list(tmp_path.glob('qualification-*'))==[]


def test_release_input_reference_loader_recomputes_from_owned_source_files(tmp_path,monkeypatch):
    import json
    from dataclasses import asdict
    from test_thermal_artifacts import valid_artifact
    decision=module();tmp_path.chmod(0o700)
    artifact=tmp_path/'artifact.json';artifact.write_text(json.dumps(asdict(valid_artifact())));artifact.chmod(0o600)
    training=tmp_path/'training.json';training.write_text('{}');training.chmod(0o600)
    pairs=tmp_path/'pairs.json';pairs.write_text('[]');pairs.chmod(0o600)
    references=dict(schema='earthship-thermal-release-inputs/v1',registration_path=str(tmp_path/'registration.json'),
        artifact_path=str(artifact),fit_evidence_path=str(tmp_path/'fit.json'),training_sources_path=str(training),
        runtime_bundle_path=str(tmp_path/'runtime'),pairs_path=str(pairs))
    source=tmp_path/'release-inputs.json';source.write_text(json.dumps(references));source.chmod(0o600)
    calls=[]
    def qualify(**kwargs):calls.append(kwargs);return {'forecast_qualified':False}
    monkeypatch.setattr(decision,'qualify_candidate',qualify)
    loader=decision.load_qualification_inputs(source)
    at=datetime(2026,10,7,tzinfo=timezone.utc)
    assert loader(at)=={'forecast_qualified':False}
    assert loader(at)=={'forecast_qualified':False}
    assert len(calls)==2 and all(call['now']==at for call in calls)
    assert calls[0]['artifact'].schema==valid_artifact().schema


def test_release_reference_file_cannot_supply_manual_active_or_cached_pass_flags(tmp_path):
    import json
    decision=module();tmp_path.chmod(0o700)
    path=tmp_path/'release-inputs.json';path.write_text(json.dumps({'active':True,'forecast_qualified':True}));path.chmod(0o600)
    with pytest.raises(ValueError):decision.load_qualification_inputs(path)


def test_recent_prospective_regression_closes_current_candidate_gate(monkeypatch):
    """Real statistical evaluator; mocked source/fit boundaries are not release evidence."""
    from test_thermal_graduation_statistics import extended_operational_history
    from datetime import timedelta
    real_evaluator=module().assess_predictive_skill
    decision,args=classifier_case(monkeypatch)
    policy=decision.read_registered_policy(None)['policy']
    _,rows,now=extended_operational_history(recent_loss=True)
    offset=timedelta(days=19)
    for row in rows:
        for field in ('issue_at','target_at'):row[field]=(datetime.fromisoformat(row[field])+offset).isoformat()
        row.update(artifact_sha256=policy['candidate']['artifact_sha256'],runtime_sha256=policy['candidate']['runtime_sha256'],sensor_epochs=policy['candidate']['sensor_epochs'])
    args['now']=now+offset-timedelta(minutes=1)
    template=args['original_pairs'][0]
    args['original_pairs']=[{**template,'publication':{'index':index},'horizon_hours':row['horizon_hours']} for index,row in enumerate(rows)]
    monkeypatch.setattr(decision,'_score_origin_record',lambda *a,**kw:dict(scored_pair=rows[kw['publication']['index']],original_capture_sha256='e'*64))
    # Exercise whichever evaluator production imports, without the fixture's stub.
    monkeypatch.setattr(decision,'assess_predictive_skill',real_evaluator)
    report=decision.qualify_candidate(**args)
    assert report['forecast_qualified'] is False
    assert report['gates']['predictive_skill'] is False
    assert report['recommended_stage']=='shadow'
    assert report['schema']=='earthship-thermal-qualification-report/v3'
    assert report['statistics']['historical_assessment']['statistical_forecast_gates_passed'] is True
    assert report['statistics']['recent_prospective']['24']['gates']['persistence_skill'] is False
