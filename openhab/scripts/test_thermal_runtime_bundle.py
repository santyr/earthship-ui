"""Private runtime retention boundaries; never executes archived code."""
from hashlib import sha256
import json
from pathlib import Path

import pytest

from test_thermal_origin_capture import runtime_tree
from thermal_model.origin_capture import build_runtime_binding
from thermal_model.forcing_capture import _canonical


def module():
    from thermal_model import runtime_bundle
    return runtime_bundle


def inputs(tmp_path,monkeypatch):
    root,executable=runtime_tree(tmp_path,monkeypatch)
    archive=tmp_path/'archives';archive.mkdir(mode=0o700)
    paths=('thermal_intel.py',)
    binding=build_runtime_binding(root,paths)
    return root,executable,archive,paths,binding


def test_bundle_preserves_exact_original_sources_and_interpreter_after_live_update(tmp_path,monkeypatch):
    bundle=module();root,executable,archive,paths,binding=inputs(tmp_path,monkeypatch)
    directory=bundle.capture_runtime_bundle(archive,root,paths,expected_binding=binding)
    manifest=bundle.read_runtime_bundle(directory)
    assert manifest['schema']=='earthship-thermal-runtime-bundle/v1'
    assert manifest['runtime']==binding
    assert manifest['revision_paths']==list(paths)
    assert manifest['release_authorized'] is False
    assert directory.name==sha256(_canonical(binding)).hexdigest()
    assert (directory/'sources/thermal_intel.py').read_bytes()==(root/'thermal_intel.py').read_bytes()
    assert (directory/'interpreter.bin').read_bytes()==executable.read_bytes()
    assert (directory/'interpreter.bin').stat().st_mode & 0o777==0o600
    assert bundle.capture_runtime_bundle(archive,root,paths,expected_binding=binding)==directory
    (root/'thermal_intel.py').write_bytes(b'# later deployment\n')
    assert bundle.read_runtime_bundle(directory)==manifest
    with pytest.raises(ValueError):bundle.capture_runtime_bundle(archive,root,paths,expected_binding=binding)


@pytest.mark.parametrize('damage',['source','interpreter','manifest','extra','file_mode','directory_mode',
    'path_escape','duplicate_path','order','symlink','path_type'])
def test_changed_or_unsafe_runtime_bundle_refuses_replay(tmp_path,monkeypatch,damage):
    bundle=module();root,executable,archive,paths,binding=inputs(tmp_path,monkeypatch)
    directory=bundle.capture_runtime_bundle(archive,root,paths,expected_binding=binding)
    path=directory/'manifest.json';manifest=json.loads(path.read_text())
    if damage=='source':(directory/'sources/thermal_intel.py').write_bytes(b'# changed\n')
    elif damage=='interpreter':(directory/'interpreter.bin').write_bytes(b'not the interpreter')
    elif damage=='manifest':manifest['runtime']['dependencies']['numpy']='99.0'
    elif damage=='extra':(directory/'extra.json').write_text('{}')
    elif damage=='file_mode':(directory/'sources/thermal_intel.py').chmod(0o644)
    elif damage=='directory_mode':(directory/'sources').chmod(0o755)
    elif damage=='path_escape':manifest['revision_paths']=['../thermal_intel.py']
    elif damage=='duplicate_path':manifest['revision_paths']*=2
    elif damage=='path_type':manifest['revision_paths']=[{}]
    elif damage=='order':manifest['revision_paths']=['thermal_model/origin_capture.py','thermal_intel.py']
    elif damage=='symlink':
        source=directory/'sources/thermal_intel.py';source.unlink();source.symlink_to(root/'thermal_intel.py')
    if damage in ('manifest','path_escape','duplicate_path','order','path_type'):
        body={key:value for key,value in manifest.items() if key!='bundle_sha256'}
        manifest['bundle_sha256']=sha256(_canonical(body)).hexdigest();path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):bundle.read_runtime_bundle(directory)


def test_bundle_refuses_source_drift_during_copy_and_does_not_publish_partial_archive(tmp_path,monkeypatch):
    bundle=module();root,executable,archive,paths,binding=inputs(tmp_path,monkeypatch)
    real=bundle._source_bytes
    def drift(path,**kwargs):
        raw=real(path,**kwargs)
        if path==root/'thermal_model/origin_capture.py':(root/'thermal_intel.py').write_bytes(b'# changed during copy\n')
        return raw
    monkeypatch.setattr(bundle,'_source_bytes',drift)
    with pytest.raises(ValueError):bundle.capture_runtime_bundle(archive,root,paths,expected_binding=binding)
    assert not (archive/sha256(_canonical(binding)).hexdigest()).exists()


def test_private_storage_is_required_before_capture(tmp_path,monkeypatch):
    bundle=module();root,executable,archive,paths,binding=inputs(tmp_path,monkeypatch)
    archive.chmod(0o755)
    with pytest.raises(ValueError):bundle.capture_runtime_bundle(archive,root,paths,expected_binding=binding)
