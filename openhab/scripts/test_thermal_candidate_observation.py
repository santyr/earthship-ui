"""First frozen-runtime shadow origins need no previous qualification pairs."""
from copy import deepcopy
from datetime import timedelta
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import json,sys
import pytest

from thermal_model.forcing_capture import _canonical
from test_thermal_origin_capture import capture_inputs


def observation_case(tmp_path,monkeypatch):
    import thermal_intel as thermal
    source=capture_inputs();now=source['inputs_available_at']
    for name in ('models','origins','outputs','runtime'):(tmp_path/name).mkdir(mode=0o700)
    runtime=tmp_path/'runtime'
    for name in thermal._release_runtime_paths():
        path=runtime/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'# synthetic frozen runtime source\n');path.chmod(0o600)
    executable=tmp_path/'interpreter';executable.write_bytes(b'synthetic interpreter identity\n');executable.chmod(0o700)
    monkeypatch.setattr(sys,'executable',str(executable))
    monkeypatch.setattr(thermal,'__file__',str(runtime/'thermal_intel.py'))
    binding=thermal._release_runtime_binding()
    monkeypatch.setattr(thermal.forecast_intel,'load_site_settings',lambda:None)
    monkeypatch.setattr(thermal.forecast_intel,'fetch_forecast',lambda:deepcopy(source['snapshot']))
    monkeypatch.setattr(thermal,'_forecast_rows',lambda *_:deepcopy(source['rows']))
    def observed(at,*,origin_observer):origin_observer(deepcopy(source['origin_temperatures']));return deepcopy(source['current'])
    monkeypatch.setattr(thermal,'_current_states',observed)
    def predict(**kwargs):
        assert kwargs.get('optimize_schedule') is False
        kwargs['artifact_observer'](source['artifact']);return deepcopy(source['output'])
    monkeypatch.setattr(thermal,'run_shadow',predict)
    from thermal_model import graduation_decision
    monkeypatch.setattr(graduation_decision,'load_qualification_inputs',lambda *_:pytest.fail('observation required existing qualification'))
    args=SimpleNamespace(model_directory=tmp_path/'models',origin_capture_dir=tmp_path/'origins',output=tmp_path/'outputs/shadow.json',publish=True,
        candidate_sha256=sha256(_canonical(asdict(source['artifact']))).hexdigest(),runtime_sha256=sha256(_canonical(binding)).hexdigest())
    return thermal,args,source,now,binding


def test_explicit_observation_cli_defaults_to_preview():
    import thermal_intel
    args=thermal_intel._build_parser().parse_args(['observe-candidate','--model-directory','/private/models','--origin-capture-dir','/private/origins','--output','/private/output/shadow.json','--candidate-sha256','a'*64,'--runtime-sha256','b'*64])
    assert args.publish is False and args.subcommand=='observe-candidate'


def test_first_frozen_release_runtime_origin_is_issued_archived_and_source_scored(tmp_path,monkeypatch):
    from thermal_model.origin_capture import read_origin_capture
    from thermal_model.runtime_bundle import read_runtime_bundle
    from thermal_model.graduation_evidence import score_qualified_origin
    from test_thermal_graduation_evidence import receipt
    thermal,args,source,now,binding=observation_case(tmp_path,monkeypatch)
    assert sha256(_canonical(thermal._origin_runtime_binding())).hexdigest()!=args.runtime_sha256
    sent=[]
    assert thermal._observe_candidate(args,now,put_state=lambda item,raw:sent.append(json.loads(raw)),decision_clock=lambda:now,published_clock=lambda:now+timedelta(seconds=2))==0
    assert len(sent)==1 and sent[0]['status']=='shadow' and sent[0]['version']==1
    assert sent[0]['confidence']['grade']=='low'
    origins=list(args.origin_capture_dir.glob('*/*-origin-v1.json.gz'));assert len(origins)==1
    record=read_origin_capture(origins[0]);assert record['output']==sent[0]
    assert record['sha256']['runtime']==args.runtime_sha256 and record['sha256']['artifact']==args.candidate_sha256
    assert read_runtime_bundle(args.origin_capture_dir/'runtime-bundles'/args.runtime_sha256)['runtime']==binding
    target=now+timedelta(hours=1);cycles=[]
    for lag in range(1,8):
        start=now-timedelta(days=lag);end=target-timedelta(days=lag)
        cycles.extend([[start.isoformat(),receipt(start,70)],[end.isoformat(),receipt(end,71)]])
    result=score_qualified_origin(origin_path=origins[0],publication=dict(time=int((now+timedelta(seconds=2)).timestamp()*1000),state=json.dumps(sent[0])),horizon_hours=1,
        outcome=dict(target_at=target.isoformat(),receipt=receipt(target,74)),recent_cycle_grid=cycles,assessed_at=target+timedelta(minutes=10))
    assert result['scored_pair']['runtime_sha256']==args.runtime_sha256
    assert result['scored_pair']['model_error_f']==1
    assert result['forecast_source_binding_verified'] is True and result['release_authorized'] is False
    assert result['action_response_qualification_claimed'] is False


def test_observation_preview_never_publishes_or_archives(tmp_path,monkeypatch):
    thermal,args,_,now,_=observation_case(tmp_path,monkeypatch);args.publish=False
    def prohibited(*args,**kwargs):pytest.fail('preview published or archived')
    monkeypatch.setattr(thermal,'_archive_original_publication',prohibited)
    assert thermal._observe_candidate(args,now,put_state=prohibited,decision_clock=lambda:now,published_clock=prohibited)==0
    assert json.loads(args.output.read_text())['confidence']['grade']=='low'
    assert list(args.origin_capture_dir.iterdir())==[]


def test_release_accepts_actual_native_observer_tuple_rows(tmp_path,monkeypatch):
    from datetime import datetime
    from test_thermal_release_runtime import release_case
    thermal,args,_,now=release_case(tmp_path,monkeypatch)
    original=thermal._current_states
    def observed(at,*,origin_observer):
        def raw_native(proof):
            proof['assessed_at']=datetime.fromisoformat(proof['assessed_at'])
            for role in proof['roles'].values():
                role['grid']=[(datetime.fromisoformat(at),{key:datetime.fromisoformat(value) if key in ('receivedAt','storedAt','validUntil') else value for key,value in receipt.items()}) for at,receipt in role['grid']]
            origin_observer(proof)
        return original(at,origin_observer=raw_native)
    monkeypatch.setattr(thermal,'_current_states',observed)
    sent=[]
    assert thermal._release(args,now,put_state=lambda item,raw:sent.append(json.loads(raw)),decision_clock=lambda:now,qualification_clock=lambda:now)==0
    assert len(sent)==1 and sent[0]['status']=='forecast_active'


@pytest.mark.parametrize('damage',['runtime_pin','runtime_drift','candidate_pin','missing_proof','mixed_epoch','expired','clock_backwards'])
def test_observation_identity_or_native_failure_never_publishes(tmp_path,monkeypatch,damage):
    thermal,args,source,now,binding=observation_case(tmp_path,monkeypatch)
    clocks=iter([now,now+timedelta(seconds=91)] if damage=='expired' else [now,now-timedelta(seconds=1)] if damage=='clock_backwards' else [now,now])
    if damage=='runtime_pin':
        args.runtime_sha256='0'*64
        monkeypatch.setattr(thermal,'_current_states',lambda *args,**kwargs:pytest.fail('wrong runtime collected current inputs'))
    elif damage=='runtime_drift':
        reads=[]
        def changed():
            reads.append(True);value=deepcopy(binding)
            if len(reads)>2:value['code_revision']='0'*64
            return value
        monkeypatch.setattr(thermal,'_release_runtime_binding',changed)
    elif damage=='candidate_pin':args.candidate_sha256='0'*64
    elif damage=='missing_proof':monkeypatch.setattr(thermal,'_current_states',lambda *args,**kwargs:deepcopy(source['current']))
    elif damage=='mixed_epoch':source['origin_temperatures']['roles']['mass']['grid'][0][1]['streamEpoch']='064142d5-99ee-4b7a-b5fc-e6a96e7274d8'
    def prohibited(*args,**kwargs):pytest.fail('invalid observation delivered or archived')
    monkeypatch.setattr(thermal,'_archive_original_publication',prohibited)
    assert thermal._observe_candidate(args,now,put_state=prohibited,decision_clock=lambda:next(clocks),published_clock=prohibited)==1
    assert list(args.origin_capture_dir.iterdir())==[]


@pytest.mark.parametrize('damage',['models','origins','outputs','output_in_models','output_in_origins','output_in_runtime','output_is_interpreter'])
def test_observation_private_path_failure_refuses_before_collection(tmp_path,monkeypatch,damage):
    thermal,args,_,now,_=observation_case(tmp_path,monkeypatch)
    if damage in ('models','origins','outputs'):(tmp_path/damage).chmod(0o755)
    elif damage=='output_in_models':args.output=args.model_directory/'shadow.json'
    elif damage=='output_in_origins':args.output=args.origin_capture_dir/'shadow.json'
    elif damage=='output_in_runtime':args.output=Path(thermal.__file__).parent/'shadow.json'
    else:args.output=Path(sys.executable)
    def prohibited(*args,**kwargs):pytest.fail('bad private path reached collection or transport')
    monkeypatch.setattr(thermal,'_current_states',prohibited)
    assert thermal._observe_candidate(args,now,put_state=prohibited,decision_clock=lambda:now)==1


def test_failed_observation_transport_never_archives(tmp_path,monkeypatch):
    thermal,args,_,now,_=observation_case(tmp_path,monkeypatch)
    monkeypatch.setattr(thermal,'_archive_original_publication',lambda *args,**kwargs:pytest.fail('unaccepted write archived'))
    def failed(*args):raise OSError('controlled transport failure')
    with pytest.raises(OSError,match='controlled transport'):
        thermal._observe_candidate(args,now,put_state=failed,decision_clock=lambda:now)
    assert list(args.origin_capture_dir.iterdir())==[]


def test_accepted_observation_archive_failure_is_explicit_without_redelivery(tmp_path,monkeypatch,capsys):
    thermal,args,_,now,_=observation_case(tmp_path,monkeypatch);sent=[]
    def failed(*args,**kwargs):raise OSError('controlled archive failure')
    monkeypatch.setattr(thermal,'_archive_original_publication',failed)
    assert thermal._observe_candidate(args,now,put_state=lambda item,raw:sent.append(json.loads(raw)),decision_clock=lambda:now,published_clock=lambda:now+timedelta(seconds=2))==2
    assert len(sent)==1 and sent[0]['status']=='shadow'
    assert 'accepted but original observation proof unavailable' in capsys.readouterr().err


def test_main_dispatches_explicit_candidate_observation_without_qualification(monkeypatch):
    import thermal_intel
    def observed(args,now,**kwargs):
        assert args.publish is False and args.candidate_sha256=='a'*64
        assert now.utcoffset() is not None
        return 2
    monkeypatch.setattr(thermal_intel,'_observe_candidate',observed)
    assert thermal_intel.main(['observe-candidate','--model-directory','/private/models','--origin-capture-dir','/private/origins','--output','/private/output/shadow.json','--candidate-sha256','a'*64,'--runtime-sha256','b'*64])==2


def test_accepted_observation_backward_ack_clock_cannot_create_source_proof(tmp_path,monkeypatch):
    thermal,args,_,now,_=observation_case(tmp_path,monkeypatch);sent=[]
    clocks=iter([now,now+timedelta(seconds=1)])
    assert thermal._observe_candidate(args,now,put_state=lambda item,raw:sent.append(json.loads(raw)),decision_clock=lambda:next(clocks),published_clock=lambda:now+timedelta(milliseconds=500))==2
    assert len(sent)==1
    assert list(args.origin_capture_dir.glob('*/*-origin-v1.json.gz'))==[]
