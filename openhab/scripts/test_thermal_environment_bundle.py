"""Exact dependency-byte retention; tiny fixtures, no environment rebuild or fit."""
from hashlib import sha256
from pathlib import Path

import pytest


def module():
    from thermal_model import environment_bundle
    return environment_bundle


def files(tmp_path):
    source=tmp_path/'source';source.mkdir(mode=0o700)
    paths={}
    for name,content in [('python',b'fixture interpreter'),('module.py',b'# dependency'),('native.so',b'fixture native library')]:
        path=source/name;path.write_bytes(content);path.chmod(0o600)
        paths[str(path)]=path
    archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    return paths,archive


def test_environment_bytes_survive_original_dependency_changes(tmp_path):
    paths,archive=files(tmp_path)
    target=module().capture_environment_files(archive,paths)
    value=module().read_environment_bundle(target)
    assert value['cold_environment_qualified'] is False
    assert value['production_qualified'] is False
    for name,path in paths.items():
        assert value['files'][name]['sha256']==sha256(path.read_bytes()).hexdigest()
        assert (target/'blobs'/value['files'][name]['sha256']).read_bytes()==path.read_bytes()
    first=next(iter(paths.values()));first.write_bytes(b'upgraded dependency')
    assert module().read_environment_bundle(target)==value


@pytest.mark.parametrize('damage',['blob','extra','mode','manifest'])
def test_changed_environment_archive_is_not_compatible(tmp_path,damage):
    paths,archive=files(tmp_path);target=module().capture_environment_files(archive,paths)
    if damage=='blob':next((target/'blobs').iterdir()).write_bytes(b'changed')
    elif damage=='extra':(target/'blobs'/'unexpected').write_bytes(b'new')
    elif damage=='mode':next((target/'blobs').iterdir()).chmod(0o644)
    else:(target/'manifest.json').write_text('{}')
    with pytest.raises(ValueError):module().read_environment_bundle(target)


def test_same_dependency_content_is_deduplicated_and_retries_are_immutable(tmp_path):
    paths,archive=files(tmp_path)
    original=next(iter(paths.values()));duplicate=original.parent/'alias.py'
    duplicate.write_bytes(original.read_bytes());duplicate.chmod(0o600);paths[str(duplicate)]=duplicate
    first=module().capture_environment_files(archive,paths)
    assert module().capture_environment_files(archive,paths)==first
    assert len(list((first/'blobs').iterdir()))==len(paths)-1


def test_source_change_or_interrupted_copy_leaves_no_partial_bundle(tmp_path,monkeypatch):
    paths,archive=files(tmp_path);bundle=module()
    real=bundle._copy_file
    def changed(source,destination):
        result=real(source,destination)
        source.write_bytes(b'changed during capture')
        return result
    monkeypatch.setattr(bundle,'_copy_file',changed)
    with pytest.raises(ValueError):bundle.capture_environment_files(archive,paths)
    assert not any(path.is_dir() for path in archive.iterdir())


def test_unsafe_or_unbounded_dependency_input_refuses_before_publication(tmp_path,monkeypatch):
    paths,archive=files(tmp_path)
    first=next(iter(paths.values()));first.chmod(0o666)
    with pytest.raises(ValueError):module().capture_environment_files(archive,paths)
    first.chmod(0o600)
    monkeypatch.setattr(module(),'MAX_TOTAL_BYTES',1)
    with pytest.raises(ValueError):module().capture_environment_files(archive,paths)
    assert not any(path.is_dir() for path in archive.iterdir())


def test_dependency_map_preserves_logical_alias_without_following_it_implicitly(tmp_path):
    paths,archive=files(tmp_path);source=next(iter(paths.values()))
    link=source.parent/'logical-alias';link.symlink_to(source)
    with pytest.raises(ValueError):module().capture_environment_files(archive,{str(link):link})
    target=module().capture_environment_files(archive,{str(link):link.resolve()})
    value=module().read_environment_bundle(target)
    assert str(link) in value['files']
    assert value['files'][str(link)]['sha256']==sha256(source.read_bytes()).hexdigest()


def test_retention_flags_cannot_be_promoted_by_rehashing_manifest(tmp_path):
    import json
    from thermal_model.forcing_capture import _canonical
    paths,archive=files(tmp_path);target=module().capture_environment_files(archive,paths)
    path=target/'manifest.json';value=json.loads(path.read_text())
    value['cold_environment_qualified']=True
    value['bundle_sha256']=sha256(_canonical({key:item for key,item in value.items() if key!='bundle_sha256'})).hexdigest()
    path.write_text(json.dumps(value));new=archive/value['bundle_sha256'];target.rename(new)
    with pytest.raises(ValueError):module().read_environment_bundle(new)
