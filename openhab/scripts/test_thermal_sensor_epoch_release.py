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


def test_native_shadow_requires_complete_hardware_bindings(monkeypatch):
    output=release.build_sensor_release_output(**native_release_inputs(monkeypatch,skill=False))
    output['release']['sensorEpochs']={}
    with pytest.raises(ValueError):release.validate_sensor_release_output(output)
