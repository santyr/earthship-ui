"""Tiny opaque v4 preservation fixtures; no eligibility, code execution or fitting."""
import json
from pathlib import Path
import pytest
from test_thermal_origin_capture import capture_inputs
from thermal_model.environment_bundle import capture_environment_files


def module():
    from thermal_model import legacy_recovery
    return legacy_recovery


def fixture(tmp_path):
    sources=tmp_path/'sources';sources.mkdir(mode=0o700)
    names=['thermal_intel.py','thermal_model/artifacts.py','thermal_model/schema.py','thermal_model/pipeline.py','thermal_model/forcing_capture.py']
    mapping={}
    for name in names:
        path=sources/name;path.parent.mkdir(mode=0o700,exist_ok=True)
        path.write_bytes(b'# opaque retained fixture\n');path.chmod(0o600);mapping[str(path)]=path
    archive=tmp_path/'archives';archive.mkdir(mode=0o700)
    source_bundle=capture_environment_files(archive,mapping)
    executable=tmp_path/'python';executable.write_bytes(b'opaque interpreter fixture');executable.chmod(0o600)
    env=capture_environment_files(archive,{str(executable):executable})
    output=capture_inputs()['output'];model=output['model']
    artifact=dict(schema='earthship-thermal-model/v4',created_at=model['createdAt'],trained_from='2026-01-01T00:00:00+00:00',trained_through=model['trainedThrough'],code_revision=model['codeRevision'],behavior={},dynamics={},data_manifest={},metrics={})
    artifact_path=tmp_path/'artifact.json';artifact_path.write_text(json.dumps(artifact,indent=2));artifact_path.chmod(0o600)
    output_path=tmp_path/'output.json';output_path.write_text(json.dumps(output,indent=2));output_path.chmod(0o600)
    return dict(artifact_path=artifact_path,output_path=output_path,source_bundle=source_bundle,source_root=str(sources),revision_paths=names,environment_bundles={'interpreter':env},interpreter=str(executable),native_bindings={},reason='operator_rollback')


def test_original_v4_bytes_and_sources_survive_preparation_without_qualification(tmp_path):
    inputs=fixture(tmp_path);target=tmp_path/'recovery'
    receipt=module().prepare_legacy_generation(target,**inputs)
    assert (target/'models/accepted.json').read_bytes()==inputs['artifact_path'].read_bytes()
    assert (target/'last-shadow.json').read_bytes()==inputs['output_path'].read_bytes()
    assert (target/'runtime/thermal_intel.py').read_bytes()==b'# opaque retained fixture\n'
    assert all(receipt[key] is False for key in ('artifact_reader_qualified','cold_runtime_qualified','journal_qualified','installed','automatic_actuation'))
    assert module().verify_legacy_generation(target)==receipt
    from thermal_model.rollback import read_snapshot
    with pytest.raises(ValueError):read_snapshot(target)


@pytest.mark.parametrize('damage',['artifact','source','environment','extra','flag','schema','mode'])
def test_changed_or_promoted_generation_refuses_verification(tmp_path,damage):
    inputs=fixture(tmp_path);target=tmp_path/'recovery'
    module().prepare_legacy_generation(target,**inputs)
    if damage=='artifact':(target/'models/accepted.json').write_text('{}')
    elif damage=='source':(target/'runtime/thermal_intel.py').write_text('# changed')
    elif damage=='environment':next((inputs['environment_bundles']['interpreter']/'blobs').iterdir()).write_bytes(b'changed')
    elif damage=='extra':(target/'extra').write_bytes(b'unexpected')
    elif damage=='mode':(target/'last-shadow.json').chmod(0o644)
    else:
        path=target/'manifest.json';value=json.loads(path.read_text())
        if damage=='flag':value['installed']=True
        else:value['schema']='earthship-thermal-rollback-snapshot/v1'
        path.write_text(json.dumps(value))
    with pytest.raises(ValueError):module().verify_legacy_generation(target)


@pytest.mark.parametrize('damage',['v5','code','created','unavailable','missing_interpreter','binding','reason'])
def test_incompatible_or_unbound_inputs_refuse_without_destination(tmp_path,damage):
    inputs=fixture(tmp_path)
    if damage in ('v5','code','created'):
        path=inputs['artifact_path'];value=json.loads(path.read_text())
        if damage=='v5':value['schema']='earthship-thermal-model/v5'
        elif damage=='code':value['code_revision']='a'*64
        else:value['created_at']='2099-01-01T00:00:00+00:00'
        path.write_text(json.dumps(value))
    elif damage=='unavailable':
        path=inputs['output_path'];value=json.loads(path.read_text());value['confidence']['grade']='unavailable';path.write_text(json.dumps(value))
    elif damage=='missing_interpreter':inputs['interpreter']='/missing/interpreter'
    elif damage=='binding':inputs['native_bindings']={'libmissing.so':'/missing/library'}
    else:inputs['reason']='active_override'
    target=tmp_path/'refused'
    with pytest.raises(ValueError):module().prepare_legacy_generation(target,**inputs)
    assert not target.exists()


def test_existing_destination_is_never_replaced(tmp_path):
    inputs=fixture(tmp_path);target=tmp_path/'existing';target.mkdir(mode=0o700);(target/'keep').write_text('untouched')
    with pytest.raises(ValueError):module().prepare_legacy_generation(target,**inputs)
    assert (target/'keep').read_text()=='untouched'


@pytest.mark.parametrize('damage',['promoted_flag','missing_revision','extra_runtime_directory'])
def test_outer_rehash_cannot_promote_or_weaken_generation(tmp_path,damage):
    from hashlib import sha256
    inputs=fixture(tmp_path);target=tmp_path/'recovery'
    module().prepare_legacy_generation(target,**inputs)
    path=target/'manifest.json';value=json.loads(path.read_text())
    if damage=='promoted_flag':value['cold_runtime_qualified']=True
    elif damage=='missing_revision':value['runtime_revision']=None
    else:(target/'runtime/unexpected-package').mkdir(mode=0o700)
    value['generation_sha256']=sha256(json.dumps({key:item for key,item in value.items() if key!='generation_sha256'},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):module().verify_legacy_generation(target)


def test_interrupted_copy_cleans_private_partial_generation(tmp_path,monkeypatch):
    inputs=fixture(tmp_path);target=tmp_path/'interrupted'
    def interrupted(*args,**kwargs):raise OSError('copy interrupted')
    monkeypatch.setattr(module(),'_copy_file',interrupted)
    with pytest.raises(OSError):module().prepare_legacy_generation(target,**inputs)
    assert not target.exists() and not list(tmp_path.glob('.legacy-recovery-*'))
