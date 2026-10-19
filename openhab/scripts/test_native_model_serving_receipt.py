"""Receipt admission must retain complete originals and fresh serving authority."""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
import importlib,importlib.util,json,os
import pytest
from test_native_thermal_artifact import originals,fixture,encode


def api():
    assert importlib.util.find_spec('native_model_serving_receipt') is not None, 'model receipt admission is missing'
    return importlib.import_module('native_model_serving_receipt')


def prepared(tmp_path,originals):
    module=api()
    import native_thermal_artifact as artifacts
    from test_google_irradiance_model import fresh_candidate
    from datetime import datetime
    with pytest.MonkeyPatch.context() as patch:
        candidate,runtime,paths=fresh_candidate(tmp_path,patch)
    at=datetime.fromisoformat(candidate['created_at'])
    path=tmp_path/(candidate['artifact_sha256']+'.native-provisional-candidate-v4.json')
    directory=tmp_path/'receipts';directory.mkdir(mode=0o700)
    return module,artifacts,candidate,path,paths,runtime,at,directory


def test_admission_retains_full_numerical_validation_and_complete_originals(tmp_path,originals,monkeypatch):
    module,artifacts,candidate,path,paths,runtime,at,directory=prepared(tmp_path,originals)
    calls=[];real=artifacts.read_native_candidate
    def observed(*args,**kwargs):
        calls.append(Path(args[0]));return real(*args,**kwargs)
    monkeypatch.setattr(artifacts,'read_native_candidate',observed)
    receipt=module.admit_model(path,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'],directory=directory,clock=lambda:at+timedelta(seconds=1),guard=lambda:None)
    value=json.loads(receipt.read_bytes())
    assert calls==[path]
    assert value['schema']=='earthship-native-model-verification-receipt/v1'
    assert value['candidate_file_sha256']==sha256(path.read_bytes()).hexdigest()
    assert value['artifact_sha256']==candidate['artifact_sha256']
    assert set(value['originals'])=={'snapshot','dataset','geometry','fit_evidence'}
    assert all(value['originals'][role]['sha256']==sha256(source.read_bytes()).hexdigest() for role,source in paths.items())
    assert receipt.stat().st_mode&0o777==0o600
    assert value['release_authorized'] is False


@pytest.mark.parametrize('role',['snapshot','dataset','geometry','fit_evidence'])
def test_original_change_during_admission_creates_no_receipt(tmp_path,originals,monkeypatch,role):
    module,artifacts,candidate,path,paths,runtime,at,directory=prepared(tmp_path,originals)
    real=artifacts.read_native_candidate;altered=[]
    def changed(*args,**kwargs):
        result=real(*args,**kwargs);paths[role].write_bytes(paths[role].read_bytes()+b' ');altered.append(role);return result
    monkeypatch.setattr(artifacts,'read_native_candidate',changed)
    with pytest.raises(ValueError):
        module.admit_model(path,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'],directory=directory,clock=lambda:at+timedelta(seconds=1),guard=lambda:None)
    assert altered==[role]
    assert list(directory.iterdir())==[]


def test_public_constructor_cannot_authorize_serving():
    module=api()
    for kind in (module.ServingModel,module.OwnedServingSelection):
        with pytest.raises(TypeError):kind()
        with pytest.raises(TypeError):kind({'artifact_sha256':'a'*64})


def serving(tmp_path,originals):
    module=api()
    assert callable(getattr(module,'load_serving_selection',None)), 'owned serving selection is missing'
    assert callable(getattr(module,'read_serving_model',None)), 'fresh serving reader is missing'
    module,artifacts,candidate,path,paths,runtime,at,directory=prepared(tmp_path,originals)
    receipt=module.admit_model(path,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'],directory=directory,clock=lambda:at+timedelta(seconds=1),guard=lambda:None)
    stage=tmp_path/'stage';stage.mkdir(mode=0o700);root=stage/'sources';root.mkdir(mode=0o700)
    names={'openhab/scripts/'+name for name in runtime['base_runtime']['source_manifest']}|set(runtime['native_source_manifest'])|{'openhab/scripts/native_model_serving_receipt.py'}
    sources={}
    for name in names:
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        raw=(artifacts.ROOT/name).read_bytes();target.write_bytes(raw);target.chmod(0o644);sources[name]=sha256(raw).hexdigest()
    def private(name,value):
        target=stage/name;target.write_bytes(encode(value));target.chmod(0o600);return target
    origins=tmp_path/'origins';origins.mkdir(mode=0o700);geometry=tmp_path/'future-geometry';geometry.mkdir(mode=0o700)
    settings=dict(schema='earthship-weathernext-thermal-live-config/v2',candidate_path=str(path),artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],geometry_directory=str(geometry),evidence_directory=str(origins),model_receipt_path=str(receipt),model_receipt_sha256=sha256(receipt.read_bytes()).hexdigest(),openhab_base='http://127.0.0.1:8080/rest',native_cutover='2026-09-23T00:00:00+00:00')
    for key in ('token_file','journal_dsn_file','native_db_config','native_policy','shared_lock'):
        target=private(key+'.txt',{'synthetic':'noncredential input'});settings[key]=str(target)
    from test_google_native_selection import source
    from weather_learning.archive import Archive
    settings['weather_source']=source(Archive(tmp_path/'google').root)
    config=private('forecast.json',settings);cycle=private('cycle.json',{'forecast_config':str(config)})
    dispatch=private('score-dispatch.json',{'schema':'earthship-native-score-dispatch/v2','current':'current','historical':[]})
    dropin=stage/'service.conf';dropin.write_bytes(b'[Service]\n');dropin.chmod(0o600)
    helper=root/'openhab/scripts/native_model_serving_receipt.py'
    record=dict(schema='earthship-household-cycle-deployment/v3',code_revision='e'*40,stage=str(stage),service_file=str(dropin),original_bindings={str(config):sha256(config.read_bytes()).hexdigest(),str(path):sha256(path.read_bytes()).hexdigest()},source_manifest=sources,protected_runtime_sources=runtime['base_runtime']['source_manifest'],cycle_sha256=sha256(cycle.read_bytes()).hexdigest(),dropin_sha256=sha256(dropin.read_bytes()).hexdigest(),automatic_actuation=False,native_runtime_sources=runtime['native_source_manifest'],native_originals=candidate['originals'],artifact_sha256=candidate['artifact_sha256'],runtime_sha256=candidate['runtime_sha256'],model_verification={'receipt':{'path':str(receipt),'sha256':sha256(receipt.read_bytes()).hexdigest()},'helper':{'path':str(helper),'sha256':sha256(helper.read_bytes()).hexdigest()}},score_dispatch={'path':str(dispatch),'sha256':sha256(dispatch.read_bytes()).hexdigest()})
    manifest=private('deployment.json',record);pin=sha256(manifest.read_bytes()).hexdigest()
    selection=module.load_serving_selection(stage,expected_deployment_sha256=pin,assessed_at=at+timedelta(seconds=2),guard=lambda:None)
    return module,artifacts,candidate,path,paths,runtime,at,receipt,stage,pin,selection


def test_fresh_serving_matches_admission_without_replaying_numerical_model(tmp_path,originals,monkeypatch):
    module,artifacts,candidate,path,paths,runtime,at,receipt,stage,pin,selection=serving(tmp_path,originals)
    def forbidden(*args,**kwargs):pytest.fail('serving repeated full candidate numerical replay')
    monkeypatch.setattr(artifacts,'read_native_candidate',forbidden)
    model=module.read_serving_model(selection,assessed_at=at+timedelta(seconds=2),guard=lambda:None)
    assert model.candidate==candidate and model.runtime==runtime
    returned=model.candidate;returned['fit']['coefficients'][0]=0
    assert model.candidate==candidate
    model.verify_bindings(assessed_at=at+timedelta(seconds=3),guard=lambda:None)
    assert model.candidate['fit']['graduated'] is False


@pytest.mark.parametrize('damage',['receipt','candidate','snapshot','dataset','geometry','fit_evidence','permission','hardlink','symlink','stage_source'])
def test_changed_selection_or_original_refuses_serving_and_binding_recheck(tmp_path,originals,damage):
    module,artifacts,candidate,path,paths,runtime,at,receipt,stage,pin,selection=serving(tmp_path,originals)
    model=module.read_serving_model(selection,assessed_at=at+timedelta(seconds=2),guard=lambda:None)
    source=receipt if damage=='receipt' else path if damage=='candidate' else paths.get(damage,paths['dataset'])
    if damage=='permission':source.chmod(0o640)
    elif damage=='hardlink':os.link(source,source.with_name('duplicate-original'))
    elif damage=='symlink':
        moved=source.with_name('moved-original');source.rename(moved);source.symlink_to(moved)
    elif damage=='stage_source':
        source=stage/'sources/openhab/scripts/native_model_serving_receipt.py';source.write_bytes(source.read_bytes()+b'\n')
    else:
        st=source.stat();raw=source.read_bytes();source.write_bytes(b'['+raw[1:]);os.utime(source,ns=(st.st_atime_ns,st.st_mtime_ns))
    with pytest.raises(ValueError):module.read_serving_model(selection,assessed_at=at+timedelta(seconds=3),guard=lambda:None)
    with pytest.raises(ValueError):model.verify_bindings(assessed_at=at+timedelta(seconds=3),guard=lambda:None)


def test_original_effective_pin_refuses_resealed_stage(tmp_path,originals):
    module,artifacts,candidate,path,paths,runtime,at,receipt,stage,pin,selection=serving(tmp_path,originals)
    manifest=stage/'deployment.json';value=json.loads(manifest.read_bytes());value['code_revision']='f'*40;manifest.write_bytes(encode(value))
    with pytest.raises(ValueError):module.load_serving_selection(stage,expected_deployment_sha256=pin,assessed_at=at+timedelta(seconds=2),guard=lambda:None)


def test_future_admission_and_caller_dictionary_cannot_authorize_serving(tmp_path,originals):
    module,artifacts,candidate,path,paths,runtime,at,receipt,stage,pin,selection=serving(tmp_path,originals)
    with pytest.raises(ValueError):module.read_serving_model(selection,assessed_at=at,guard=lambda:None)
    with pytest.raises((ValueError,TypeError)):module.read_serving_model({'stage':str(stage),'deployment_sha256':pin},assessed_at=at+timedelta(seconds=2),guard=lambda:None)


def test_changed_executing_dependency_refuses_serving(tmp_path,originals,monkeypatch):
    from copy import deepcopy
    module,artifacts,candidate,path,paths,runtime,at,receipt,stage,pin,selection=serving(tmp_path,originals)
    changed=deepcopy(runtime);changed['base_runtime']['dependencies']['numpy']='999.0.0'
    monkeypatch.setattr(artifacts,'current_native_runtime',lambda **kwargs:changed)
    with pytest.raises(ValueError):module.read_serving_model(selection,assessed_at=at+timedelta(seconds=2),guard=lambda:None)


def test_stage_change_during_serving_read_is_refused(tmp_path,originals,monkeypatch):
    module,artifacts,candidate,path,paths,runtime,at,receipt,stage,pin,selection=serving(tmp_path,originals)
    real=module._check_receipt
    def changed(*args,**kwargs):
        result=real(*args,**kwargs)
        manifest=stage/'deployment.json';value=json.loads(manifest.read_bytes());value['code_revision']='f'*40;manifest.write_bytes(encode(value))
        return result
    monkeypatch.setattr(module,'_check_receipt',changed)
    with pytest.raises(ValueError):module.read_serving_model(selection,assessed_at=at+timedelta(seconds=2),guard=lambda:None)


def test_admission_readback_refuses_corrupt_persisted_receipt(tmp_path,originals,monkeypatch):
    module,artifacts,candidate,path,paths,runtime,at,directory=prepared(tmp_path,originals)
    real=module._persist
    def corrupt(*args,**kwargs):
        target=real(*args,**kwargs);target.write_bytes(b'{}');return target
    monkeypatch.setattr(module,'_persist',corrupt)
    with pytest.raises(ValueError):module.admit_model(path,runtime=runtime,expected_artifact_sha256=candidate['artifact_sha256'],directory=directory,clock=lambda:at+timedelta(seconds=1),guard=lambda:None)
