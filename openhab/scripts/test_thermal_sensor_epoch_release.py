"""Native publication v3 and original capture v4; no real release claim."""
from copy import deepcopy
from datetime import timedelta
from dataclasses import asdict
from hashlib import sha256
import json
import pytest
from test_thermal_sensor_epoch_qualification import classifier_v2
from test_thermal_sensor_epoch_origins import sensor_inputs
from test_thermal_sensor_epoch_history import EPOCHS
from test_thermal_release import shift,forecast_rows
from test_thermal_schema import valid_shadow_payload
from thermal_model.forcing_capture import _canonical
import thermal_model.graduation_decision as decision
import thermal_model.origin_capture as origins
import thermal_model.release as release


def native_release_inputs(monkeypatch,*,skill=True):
    args=classifier_v2(monkeypatch,skill=skill);report=decision.qualify_sensor_candidate(**args)
    shadow=shift(valid_shadow_payload());artifact=args['artifact']
    shadow['model']=dict(createdAt=artifact.created_at,trainedThrough=artifact.trained_through,codeRevision=artifact.code_revision)
    return dict(shadow=shadow,qualification_loader=lambda _:deepcopy(report),now=args['now'],artifact_sha256=report['candidate']['artifact_sha256'],runtime_sha256=report['candidate']['runtime_sha256'],sensor_epochs=EPOCHS,forecast_rows=forecast_rows())


def test_native_release_is_explicit_v3_and_withholds_advice(monkeypatch,tmp_path):
    data=native_release_inputs(monkeypatch);output=release.build_sensor_release_output(**data)
    assert output['version']==3 and output['status']=='forecast_active'
    assert output['release']['schema']=='earthship-thermal-release/v2'
    assert output['release']['sensorEpochSemantics']=='declared_hardware_phase'
    assert output['release']['sensorEpochs']==EPOCHS
    assert output['release']['advisoryQualified'] is False and output['release']['automaticActuation'] is False
    assert output['schedule']['candidate'] is None
    with pytest.raises(ValueError):release.validate_release_output(output)
    release.write_sensor_release_output(tmp_path/'output.json',output)
    assert json.loads((tmp_path/'output.json').read_text())==output


@pytest.mark.parametrize('damage',['legacy_report','wrong_phase','stale','manual_report','legacy_semantics'])
def test_native_release_never_activates_incompatible_evidence(monkeypatch,damage):
    data=native_release_inputs(monkeypatch)
    if damage=='legacy_report':
        report=data['qualification_loader'](data['now']);report['schema']='earthship-thermal-qualification-report/v3';report.pop('sensor_epoch_semantics')
        report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest()
        data['qualification_loader']=lambda _:report
    elif damage=='wrong_phase':data['sensor_epochs']={**EPOCHS,'air':EPOCHS['mass']}
    elif damage=='stale':data['now']+=timedelta(hours=1)
    elif damage=='manual_report':data['qualification_loader']=data['qualification_loader'](data['now'])
    else:
        report=data['qualification_loader'](data['now']);report['sensor_epoch_semantics']='collector_session'
        report['report_sha256']=sha256(_canonical({key:value for key,value in report.items() if key!='report_sha256'})).hexdigest();data['qualification_loader']=lambda _:report
    output=release.build_sensor_release_output(**data)
    assert output['version']==3 and output['status']=='unavailable' and output['forecast']['trajectory']==[]


def test_failed_native_skill_remains_shadow(monkeypatch):
    output=release.build_sensor_release_output(**native_release_inputs(monkeypatch,skill=False))
    assert output['version']==3 and output['status']=='shadow' and output['release']['forecastQualified'] is False


def test_native_release_origin_v4_retains_typed_publication_and_phase(tmp_path,monkeypatch):
    from test_thermal_policy_registration import shift as shift_origin
    data=native_release_inputs(monkeypatch);output=release.build_sensor_release_output(**data)
    source=sensor_inputs();issue=source['output']['generatedAt']
    from datetime import datetime
    delta=data['now']-datetime.fromisoformat(issue)
    artifact=source.pop('artifact');source=shift_origin(json.loads(_canonical(source)),delta);source['artifact']=artifact
    source['output']=output;source['rows']=data['forecast_rows']
    record=origins.build_sensor_release_origin_capture(**source)
    assert record['schema']=='earthship-thermal-origin-capture/v4' and record['source_epochs']==EPOCHS
    tmp_path.chmod(0o700);path=origins.write_sensor_release_origin_capture(tmp_path,record)
    assert origins.read_observed_origin_capture(path)==record
    with pytest.raises(ValueError):origins.read_release_origin_capture(path)
    assert path.name.endswith('-origin-v4.json.gz')


def runtime_case(tmp_path,monkeypatch):
    import thermal_intel
    from types import SimpleNamespace
    from test_thermal_policy_registration import shift as shift_origin
    from datetime import datetime
    data=native_release_inputs(monkeypatch);now=data['now'];original=sensor_inputs()
    delta=now-datetime.fromisoformat(original['output']['generatedAt'])
    proof=shift_origin(json.loads(_canonical(original['origin_temperatures'])),delta)
    current=shift_origin(json.loads(_canonical(original['current'])),delta)
    report=data['qualification_loader'](now)
    monkeypatch.setattr(thermal_intel.forecast_intel,'load_site_settings',lambda:None)
    def observed(at,*,origin_observer=None,receipt_version=1):
        assert receipt_version==2 and origin_observer is not None
        origin_observer(deepcopy(proof));return deepcopy(current)
    monkeypatch.setattr(thermal_intel,'_current_states',observed)
    monkeypatch.setattr(thermal_intel.forecast_intel,'fetch_forecast',lambda:{})
    monkeypatch.setattr(thermal_intel,'_forecast_rows',lambda *_:deepcopy(data['forecast_rows']))
    def predict(**kwargs):
        kwargs['artifact_observer'](original['artifact']);return deepcopy(data['shadow'])
    monkeypatch.setattr(thermal_intel,'run_shadow',predict)
    monkeypatch.setattr(thermal_intel,'_release_runtime_binding',lambda:deepcopy(report['runtime']['runtime']))
    monkeypatch.setattr(decision,'load_sensor_qualification_inputs',lambda _:lambda _:deepcopy(report))
    args=SimpleNamespace(evidence_inputs=tmp_path/'inputs.json',output=tmp_path/'release.json',publish=True,receipt_version=2)
    return thermal_intel,args,data


def test_explicit_native_release_runtime_delivers_valid_v3_once(tmp_path,monkeypatch):
    thermal,args,data=runtime_case(tmp_path,monkeypatch);sent=[]
    assert thermal._release(args,data['now'],put_state=lambda *values:sent.append(values),decision_clock=lambda:data['now'],qualification_clock=lambda:data['now'])==0
    assert len(sent)==1
    output=json.loads(sent[0][1])
    assert output==json.loads(args.output.read_text()) and output['version']==3 and output['status']=='forecast_active'
    assert output['release']['sensorEpochs']==EPOCHS


def test_native_release_runtime_missing_source_delivers_unavailable(tmp_path,monkeypatch):
    thermal,args,data=runtime_case(tmp_path,monkeypatch);sent=[]
    def refuse(_):raise ValueError('missing original native evidence')
    monkeypatch.setattr(decision,'load_sensor_qualification_inputs',refuse)
    assert thermal._release(args,data['now'],put_state=lambda *values:sent.append(values),decision_clock=lambda:data['now'],qualification_clock=lambda:data['now'])==1
    assert len(sent)==1 and json.loads(sent[0][1])['version']==3 and json.loads(sent[0][1])['status']=='unavailable'


def test_native_release_cli_requires_explicit_receipt_version():
    import thermal_intel
    args=thermal_intel._build_parser().parse_args(['release','--evidence-inputs','/private/inputs','--receipt-version','2'])
    assert args.receipt_version==2 and args.publish is False


def test_native_current_state_assembly_explicitly_selects_v2_source(monkeypatch):
    import thermal_intel
    import thermal_temperature_runtime as runtime
    from test_thermal_origin_capture import NOW
    saved=[];data=sensor_inputs()
    selected={role:dict(history=(),current=value) for role,value in data['current'].items()}
    def native(at,*,origin_observer=None):
        assert at==NOW;origin_observer(deepcopy(data['origin_temperatures']));return deepcopy(selected)
    monkeypatch.setattr(runtime,'configured_shadow_temperatures_v2',native)
    monkeypatch.setattr(runtime,'configured_shadow_temperatures',lambda *args,**kwargs:pytest.fail('native selected legacy source'))
    monkeypatch.delenv('THERMAL_RADIATION_SHADOW_QUALIFIED_ENABLE',raising=False)
    current=thermal_intel._current_states(NOW,series_reader=lambda *_:[],state_reader=lambda item:dict(name=item,state='60',lastStateUpdate=(NOW-timedelta(seconds=30)).timestamp()*1000),origin_observer=saved.append,receipt_version=2)
    assert current['air']['value']==74 and len(saved)==1


def test_native_production_capture_v4_scores_exact_original_output(tmp_path,monkeypatch):
    from test_thermal_sensor_epoch_origins import sensor_case
    from test_thermal_policy_registration import shift as shift_origin
    from test_thermal_origin_capture import NOW as ORIGINAL
    import thermal_model.graduation_evidence as evidence
    data=native_release_inputs(monkeypatch);output=release.build_sensor_release_output(**data)
    source=sensor_inputs();artifact=source.pop('artifact');delta=data['now']-ORIGINAL
    source=shift_origin(json.loads(_canonical(source)),delta);source['artifact']=artifact;source['output']=output;source['rows']=data['forecast_rows']
    record=origins.build_sensor_release_origin_capture(**source)
    tmp_path.chmod(0o700);path=origins.write_sensor_release_origin_capture(tmp_path,record)
    packet=sensor_case(tmp_path)
    packet.update(origin_path=path,publication=dict(time=int((data['now']+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(output)),outcome=shift_origin(packet['outcome'],delta),recent_cycle_grid=shift_origin(packet['recent_cycle_grid'],delta),assessed_at=packet['assessed_at']+delta)
    result=evidence.score_qualified_origin(**packet)
    assert result['schema']=='earthship-thermal-source-scored-pair/v2' and result['scored_pair']['sensor_epochs']==EPOCHS
    assert result['scored_pair']['model_error_f']==1 and result['release_authorized'] is False


@pytest.mark.parametrize('damage',['wrong_phase','legacy_model'])
def test_native_observation_refuses_model_identity_before_delivery(tmp_path,monkeypatch,damage):
    from dataclasses import replace
    from types import SimpleNamespace
    thermal,_,data=runtime_case(tmp_path,monkeypatch)
    artifact=sensor_inputs()['artifact']
    if damage=='wrong_phase':
        manifest=deepcopy(artifact.data_manifest);manifest['temperature_evidence']['roles']['air']['sensor_epoch']=EPOCHS['mass']
        artifact=replace(artifact,data_manifest=manifest)
    else:
        from test_thermal_artifacts import valid_artifact
        artifact=valid_artifact()
    def predict(**kwargs):kwargs['artifact_observer'](artifact);return deepcopy(data['shadow'])
    monkeypatch.setattr(thermal,'run_shadow',predict)
    models=tmp_path/'models';origins_path=tmp_path/'origins';models.mkdir(mode=0o700);origins_path.mkdir(mode=0o700)
    args=SimpleNamespace(model_directory=models,origin_capture_dir=origins_path,output=tmp_path/'observe.json',candidate_sha256=sha256(_canonical(asdict(artifact))).hexdigest(),runtime_sha256=sha256(_canonical(thermal._release_runtime_binding())).hexdigest(),receipt_version=2,publish=True)
    sent=[]
    assert thermal._observe_candidate(args,data['now'],put_state=lambda *values:sent.append(values),decision_clock=lambda:data['now'],published_clock=lambda:data['now']+timedelta(seconds=30))==1
    assert sent==[] and json.loads(args.output.read_text())['confidence']['grade']=='unavailable'


def test_native_shadow_requires_complete_hardware_bindings(monkeypatch):
    output=release.build_sensor_release_output(**native_release_inputs(monkeypatch,skill=False))
    output['release']['sensorEpochs']={}
    with pytest.raises(ValueError):release.validate_sensor_release_output(output)
