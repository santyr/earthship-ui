"""Native-phase qualification versions; synthetic classifier gates are not release evidence."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json
import pytest
from test_thermal_sensor_epoch_training import capture,sensor_artifact
from test_thermal_sensor_epoch_history import EPOCHS
from thermal_model.forcing_capture import _canonical
import thermal_model.training_inputs as inputs
from thermal_model.training_sources import build_training_sources
import thermal_model.graduation_decision as decision
import thermal_model.graduation_evidence as source_evidence


def training_case_v2():
    record=capture();frozen=inputs.restore_training_inputs_v2(record)
    manifest={**record['dataset_manifest'],'temperature_evidence':record['temperature_evidence']}
    artifact=SimpleNamespace(schema='earthship-thermal-model/v6',data_manifest=manifest,trained_from=record['start'],trained_through=record['end'])
    return artifact,build_training_sources(frozen.samples,frozen.series_reader)


def test_native_source_qualification_accepts_collector_sessions_in_one_phase():
    artifact,source=training_case_v2()
    result=decision.verify_sensor_training_sources(source,artifact,EPOCHS)
    assert result['schema']=='earthship-thermal-training-source-assessment/v2'
    assert result['sensor_epoch_semantics']=='declared_hardware_phase'
    assert result['sample_count']==4
    assert all(row['epoch']==EPOCHS[role] and row['qualified']==4 for role,row in result['roles'].items())
    with pytest.raises(ValueError):decision.verify_training_sources(source,artifact,EPOCHS)


@pytest.mark.parametrize('damage',['phase','receipt','latent','legacy_root','legacy_model','future','missing','frozen_phase'])
def test_native_source_qualification_cannot_repair_invalid_originals(damage):
    artifact,source=training_case_v2();epochs=dict(EPOCHS)
    if damage=='phase':source['temperature_grids']['air'][0][1]['sensorEpoch']=EPOCHS['mass']
    elif damage=='receipt':source['temperature_grids']['air'][0][1]['temperatureF']+=1
    elif damage=='latent':source['samples'][1]['mass_f']+=1
    elif damage=='legacy_root':source['schema']='earthship-thermal-training-sources/v1'
    elif damage=='legacy_model':artifact.schema='earthship-thermal-model/v5'
    elif damage=='future':source['temperature_grids']['air'][0][1]['storedAt']='2027-01-01T00:00:00+00:00'
    elif damage=='missing':source['temperature_grids']['mass'][0][1]=None
    else:epochs['air']=EPOCHS['mass']
    with pytest.raises(ValueError):decision.verify_sensor_training_sources(source,artifact,epochs)


def classifier_v2(monkeypatch,*,skill=True):
    from test_thermal_graduation_decision import classifier_case
    from test_thermal_sensor_epoch_origins import sensor_inputs
    from thermal_model.origin_capture import build_sensor_origin_capture
    from thermal_model.graduation_policy import derive_policy
    _,args=classifier_case(monkeypatch,skill=skill)
    registered=decision.read_registered_policy(None);old=registered['policy'];artifact=sensor_artifact()
    candidate={**old['candidate'],'artifact_sha256':sha256(_canonical(asdict(artifact))).hexdigest(),'sensor_epochs':dict(EPOCHS)}
    policy=derive_policy(development=old['development'],declared_at=old['declared_at'],intervals=old['intervals'],candidate=candidate,regimes=old['regimes'])
    record=build_sensor_origin_capture(**sensor_inputs())
    monkeypatch.setattr(decision,'read_sensor_registered_policy',lambda _:dict(policy=policy,registration_sha256='c'*64))
    monkeypatch.setattr(decision,'read_origin_capture',lambda _:record)
    monkeypatch.setattr(decision,'verify_sensor_training_sources',lambda *_:dict(schema='earthship-thermal-training-source-assessment/v2',sensor_epoch_semantics='declared_hardware_phase',sample_count=4))
    now=args['now']
    def score(_record,**kwargs):
        hours=kwargs['horizon_hours']
        return dict(schema='earthship-thermal-source-scored-pair/v2',scored_pair=dict(issue_at=(now-timedelta(hours=hours+1)).isoformat(),target_at=(now-timedelta(hours=1)).isoformat(),horizon_hours=hours,artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],sensor_epochs=dict(EPOCHS)),original_capture_sha256='e'*64)
    monkeypatch.setattr(decision,'_score_origin_record',score)
    args['artifact']=artifact
    return args


def test_sensor_qualification_routes_actual_gate_contract_without_advice_authority(monkeypatch):
    args=classifier_v2(monkeypatch)
    report=decision.qualify_sensor_candidate(**args)
    assert report['schema']=='earthship-thermal-qualification-report/v4'
    assert report['sensor_epoch_semantics']=='declared_hardware_phase'
    assert report['forecast_qualified'] is True
    assert report['advisory_qualified'] is False and report['automatic_actuation_authorized'] is False
    assert report['policy']['thresholds']['24']['min_independent_days']==35
    assert report['policy']['required_skill_upper_bound_f']==0
    assert decision.validate_sensor_qualification_report(report)==report
    with pytest.raises(ValueError):decision.validate_qualification_report(report)
    assert decision.qualify_candidate(**args)['forecast_qualified'] is False


@pytest.mark.parametrize('failure',['skill','fit','sources','legacy_origin','legacy_pair'])
def test_sensor_qualification_failed_gate_never_graduates(monkeypatch,failure):
    args=classifier_v2(monkeypatch,skill=failure!='skill')
    if failure=='fit':monkeypatch.setattr(decision,'read_fit_evidence',lambda *_:dict(fit_gates_passed=False,active_parameter_count=12))
    elif failure=='sources':
        def refuse(*_):raise ValueError('invalid original source')
        monkeypatch.setattr(decision,'verify_sensor_training_sources',refuse)
    elif failure=='legacy_origin':
        from test_thermal_origin_capture import capture_inputs
        from thermal_model.origin_capture import build_origin_capture
        old=build_origin_capture(**capture_inputs());monkeypatch.setattr(decision,'read_origin_capture',lambda _:old)
    elif failure=='legacy_pair':
        original=decision._score_origin_record
        def legacy(*args,**kwargs):return {**original(*args,**kwargs),'schema':'earthship-thermal-source-scored-pair/v1'}
        monkeypatch.setattr(decision,'_score_origin_record',legacy)
    report=decision.qualify_sensor_candidate(**args)
    assert report['forecast_qualified'] is False and report['recommended_stage']!='forecast_active'


def test_sensor_report_cannot_be_relabelled_or_given_manual_authority():
    kwargs=dict(registration_path=None,artifact=None,fit_evidence_path=None,training_sources=None,runtime_bundle_path=None,original_pairs=[],now=datetime(2026,10,8,tzinfo=timezone.utc))
    original=decision.qualify_sensor_candidate(**kwargs)
    for field,value in [('sensor_epoch_semantics','collector_session'),('forecast_qualified',True),('schema','earthship-thermal-qualification-report/v3')]:
        report=deepcopy(original);report[field]=value
        report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest()
        with pytest.raises(ValueError):decision.validate_sensor_qualification_report(report)


def test_native_release_reference_loader_is_explicit_and_rereads_sources(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);artifact=sensor_artifact()
    def file(name,value):
        path=tmp_path/name;path.write_bytes(_canonical(value));path.chmod(0o600);return str(path)
    references=dict(schema='earthship-thermal-release-inputs/v2',registration_path=str(tmp_path/'registration'),artifact_path=file('artifact.json',asdict(artifact)),fit_evidence_path=str(tmp_path/'fit'),training_sources_path=file('sources.json',{}),runtime_bundle_path=str(tmp_path/'runtime'),pairs_path=file('pairs.json',[]))
    path=Path(file('references.json',references));calls=[]
    def qualify(**kwargs):calls.append(kwargs);return {'forecast_qualified':False}
    monkeypatch.setattr(decision,'qualify_sensor_candidate',qualify)
    loader=decision.load_sensor_qualification_inputs(path);now=datetime(2026,10,8,tzinfo=timezone.utc)
    assert loader(now)=={'forecast_qualified':False}
    assert loader(now)=={'forecast_qualified':False} and len(calls)==2
    assert all(call['artifact'].schema=='earthship-thermal-model/v6' and call['now']==now for call in calls)
    with pytest.raises(ValueError):decision.load_qualification_inputs(path)


def test_qualification_cli_v2_missing_evidence_writes_honest_report(tmp_path,capsys):
    from test_thermal_graduation_decision import cli_module
    tmp_path.chmod(0o700);command=cli_module()
    assert command.main(['--receipt-version','2','--report-directory',str(tmp_path)])==1
    output=json.loads(capsys.readouterr().out)
    assert output['forecast_qualified'] is False and output['recommended_stage']=='unavailable'
    report=json.loads(next(tmp_path.glob('qualification-*.json')).read_text())
    assert report['schema']=='earthship-thermal-qualification-report/v4'
    assert 'qualified_training_sources' in next(tmp_path.glob('qualification-*.md')).read_text()


def test_sensor_preregistration_replays_native_source_pair_semantics(tmp_path):
    from test_thermal_sensor_epoch_origins import sensor_case
    from thermal_model.graduation_policy import RECORD_FIELDS
    import thermal_model.policy_registration as registration
    tmp_path.chmod(0o700);data=sensor_case(tmp_path)
    result=source_evidence.score_qualified_origin(**data)
    policy=dict(candidate=dict(sensor_epochs=EPOCHS),development=[{key:result['scored_pair'][key] for key in RECORD_FIELDS}])
    packet={key:(str(data[key]) if key=='origin_path' else data[key]) for key in registration.SOURCE_FIELDS}
    origins=registration._score_sources([packet],policy,data['assessed_at'],version=2)
    assert origins[str(data['origin_path'])]['schema']=='earthship-thermal-origin-capture/v3'


def test_native_preregistration_refuses_legacy_development_source(tmp_path):
    from test_thermal_graduation_evidence import case
    from thermal_model.graduation_policy import RECORD_FIELDS
    import thermal_model.policy_registration as registration
    data=case(tmp_path)
    result=source_evidence.score_qualified_origin(**data)
    policy=dict(candidate=dict(sensor_epochs=result['scored_pair']['sensor_epochs']),development=[{key:result['scored_pair'][key] for key in RECORD_FIELDS}])
    packet={key:(str(data[key]) if key=='origin_path' else data[key]) for key in registration.SOURCE_FIELDS}
    with pytest.raises(ValueError):registration._score_sources([packet],policy,data['assessed_at'],version=2)


def test_native_registration_receipt_is_private_typed_and_grants_no_release(tmp_path,monkeypatch):
    # Source replay is independently covered above; this exercises seal/copy/read.
    import thermal_model.policy_registration as registration
    from thermal_model.graduation_policy import derive_policy
    from test_thermal_graduation_policy import inputs as policy_inputs
    from test_thermal_sensor_epoch_origins import sensor_inputs
    from thermal_model.origin_capture import build_sensor_origin_capture
    from test_thermal_policy_registration import shift
    tmp_path.chmod(0o700);args=policy_inputs();args['candidate']['sensor_epochs']=EPOCHS
    policy=derive_policy(**args)
    source=build_sensor_origin_capture(**sensor_inputs())
    delta=datetime.fromisoformat(policy['development'][0]['issue_at'])-datetime.fromisoformat(source['issued_at'])
    source=shift(source,delta);source['sha256']={key:sha256(_canonical(source[key])).hexdigest() for key in source['sha256']}
    monkeypatch.setattr(registration,'_clock',lambda:datetime(2026,7,17,12,tzinfo=timezone.utc))
    def replay(packets,policy,registered,*,root=None,version=1):
        assert version==2
        name='private-native-source' if root is None else str(root/packets[0]['origin_path'])
        return {name:source}
    monkeypatch.setattr(registration,'_score_sources',replay)
    packet=dict(origin_path='private-native-source',publication={},horizon_hours=1,outcome={},recent_cycle_grid=[])
    path=registration.register_sensor_policy(tmp_path,policy,[packet])
    receipt=registration.read_sensor_registered_policy(path)
    assert receipt['schema']=='earthship-thermal-policy-registration/v2'
    assert receipt['sensor_epoch_semantics']=='declared_hardware_phase'
    assert receipt['release_authorized'] is False and path.stat().st_mode&0o777==0o600
    with pytest.raises(ValueError):registration.read_registered_policy(path)
