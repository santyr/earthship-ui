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


def test_inventory_requires_explicit_file_and_directory_aliases(tmp_path):
    paths,_=files(tmp_path);root=next(iter(paths.values())).parent
    outside=tmp_path/'outside';outside.mkdir(mode=0o700)
    dependency=outside/'dependency.py';dependency.write_bytes(b'# required');dependency.chmod(0o600)
    link=root/'external.py';link.symlink_to(dependency)
    directory_link=root/'external-package';directory_link.symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):module().inventory_environment_files([root],aliases={})
    inventory=module().inventory_environment_files([root],aliases={str(link):dependency,str(directory_link):outside})
    assert inventory[str(link)]==dependency
    assert inventory[str(directory_link/'dependency.py')]==dependency
    assert set(paths)<=set(inventory)


def test_inventory_ignores_bytecode_but_rejects_unused_or_wrong_alias(tmp_path):
    paths,_=files(tmp_path);root=next(iter(paths.values())).parent
    cache=root/'__pycache__';cache.mkdir(mode=0o700);(cache/'module.pyc').write_bytes(b'cache')
    assert module().inventory_environment_files([root],aliases={})==paths
    with pytest.raises(ValueError):module().inventory_environment_files([root],aliases={str(root/'missing'):root})
    link=root/'alias';source=next(iter(paths.values()));link.symlink_to(source)
    with pytest.raises(ValueError):module().inventory_environment_files([root],aliases={str(link):root})


def test_inventory_refuses_directory_alias_cycle_and_entry_overflow(tmp_path,monkeypatch):
    paths,_=files(tmp_path);root=next(iter(paths.values())).parent
    link=root/'loop';link.symlink_to(root,target_is_directory=True)
    with pytest.raises(ValueError):module().inventory_environment_files([root],aliases={str(link):root})
    link.unlink()
    monkeypatch.setattr(module(),'MAX_FILES',1)
    with pytest.raises(ValueError):module().inventory_environment_files([root],aliases={})


def test_inventory_feeds_real_immutable_dependency_capture(tmp_path):
    paths,archive=files(tmp_path);root=next(iter(paths.values())).parent
    inventory=module().inventory_environment_files([root],aliases={})
    target=module().capture_environment_files(archive,inventory)
    assert set(module().read_environment_bundle(target)['files'])==set(paths)


def test_prepare_environment_mirrors_retained_bytes_without_install_or_execution(tmp_path):
    paths,archive=files(tmp_path);bundle=module();retained=bundle.capture_environment_files(archive,paths)
    target=tmp_path/'prepared'
    receipt=bundle.prepare_environment_restore(retained,target)
    assert receipt['installed'] is False and receipt['cold_environment_qualified'] is False
    assert receipt['production_qualified'] is False
    for logical,source in paths.items():
        destination=target/'rootfs'/Path(logical).relative_to('/')
        assert destination.read_bytes()==source.read_bytes()
        assert destination.stat().st_mode & 0o777 == 0o600
    assert bundle.verify_environment_restore(retained,target)==receipt


@pytest.mark.parametrize('damage',['byte','extra','extra_directory','permission','symlink','flag'])
def test_prepared_dependency_changes_refuse_verification(tmp_path,damage):
    import json
    paths,archive=files(tmp_path);bundle=module();retained=bundle.capture_environment_files(archive,paths)
    target=tmp_path/'prepared';bundle.prepare_environment_restore(retained,target)
    logical=next(iter(paths));path=target/'rootfs'/Path(logical).relative_to('/')
    if damage=='byte':path.write_bytes(b'changed')
    elif damage=='extra':(path.parent/'extra').write_bytes(b'unexpected')
    elif damage=='extra_directory':(path.parent/'unexpected-package').mkdir(mode=0o700)
    elif damage=='permission':path.chmod(0o755)
    elif damage=='symlink':path.unlink();path.symlink_to(paths[logical])
    else:
        receipt=target/'restore.json';value=json.loads(receipt.read_text());value['installed']=True
        receipt.write_text(json.dumps(value))
    with pytest.raises(ValueError):bundle.verify_environment_restore(retained,target)


def test_restore_cannot_replace_existing_directory_or_publish_interrupted_copy(tmp_path,monkeypatch):
    paths,archive=files(tmp_path);bundle=module();retained=bundle.capture_environment_files(archive,paths)
    target=tmp_path/'prepared';target.mkdir(mode=0o700);(target/'keep').write_text('untouched')
    with pytest.raises(ValueError):bundle.prepare_environment_restore(retained,target)
    assert (target/'keep').read_text()=='untouched'
    def refused(*_):raise OSError('interrupted')
    monkeypatch.setattr(bundle,'_copy_file',refused)
    new=tmp_path/'new-prepared'
    with pytest.raises(OSError):bundle.prepare_environment_restore(retained,new)
    assert not new.exists() and not list(tmp_path.glob('.environment-restore-*'))


def restore_cli():
    import importlib.util
    path=Path(__file__).resolve().parents[2]/'scripts/prepare-thermal-environment.py'
    specification=importlib.util.spec_from_file_location('environment_restore_cli',path)
    result=importlib.util.module_from_spec(specification);specification.loader.exec_module(result)
    return result


def test_environment_recovery_cli_prepares_then_verifies_without_live_install(tmp_path,capsys):
    import json
    paths,archive=files(tmp_path);retained=module().capture_environment_files(archive,paths)
    target=tmp_path/'prepared';arguments=['--bundle',str(retained),'--destination',str(target)]
    assert restore_cli().main(arguments)==0
    assert json.loads(capsys.readouterr().out)['installed'] is False
    before=(target/'restore.json').read_bytes()
    assert restore_cli().main([*arguments,'--verify-only'])==0
    assert (target/'restore.json').read_bytes()==before


def test_environment_recovery_cli_refuses_invalid_bundle_without_success(tmp_path,capsys):
    assert restore_cli().main(['--bundle',str(tmp_path/'missing'),'--destination',str(tmp_path/'prepared')])==2
    result=capsys.readouterr();assert result.out=='' and 'refused' in result.err


def test_capture_and_verification_share_a_read_rate_limit_across_files(tmp_path,monkeypatch):
    paths,archive=files(tmp_path);bundle=module()
    normal=bundle.capture_environment_files(archive,paths)
    clock=[0.0]
    monkeypatch.setattr(bundle,'monotonic',lambda:clock[0],raising=False)
    def advance(seconds):
        assert seconds > 0
        clock[0]+=seconds
    monkeypatch.setattr(bundle,'sleep',advance,raising=False)
    monkeypatch.setattr(bundle,'CHUNK',4)
    rate=10
    import os
    identities={(path.stat().st_dev,path.stat().st_ino) for path in paths.values()}
    actual_read=bundle.os.read;source_bytes=[0]
    def observed_read(descriptor,count):
        info=os.fstat(descriptor)
        chunk=actual_read(descriptor,count)
        if (info.st_dev,info.st_ino) in identities:
            source_bytes[0]+=len(chunk)
            assert source_bytes[0]<=clock[0]*rate+1e-8
        return chunk
    monkeypatch.setattr(bundle.os,'read',observed_read)
    limited=bundle.capture_environment_files(archive,paths,max_read_bytes_per_second=rate)
    assert limited==normal
    size=sum(path.stat().st_size for path in paths.values())
    # Pin, copy, source recheck, and retained-blob recheck all consume bandwidth.
    assert clock[0]>=4*size/rate
    before=clock[0]
    bundle.read_environment_bundle(limited,max_read_bytes_per_second=rate)
    assert clock[0]-before>=size/rate


@pytest.mark.parametrize('rate',[0,-1,True,1.5,float('nan'),float('inf'),'10'])
def test_invalid_read_rate_refuses_before_creating_bundle(tmp_path,rate):
    paths,archive=files(tmp_path)
    with pytest.raises(ValueError):
        module().capture_environment_files(archive,paths,max_read_bytes_per_second=rate)
    assert not list(archive.iterdir())


def test_interrupted_rate_limited_capture_leaves_no_partial_bundle(tmp_path,monkeypatch):
    paths,archive=files(tmp_path);bundle=module();calls=[0]
    monkeypatch.setattr(bundle,'monotonic',lambda:0.0,raising=False)
    def interrupted(_):
        calls[0]+=1
        if calls[0]>len(paths):raise OSError('interrupted pacing during copy')
    monkeypatch.setattr(bundle,'sleep',interrupted,raising=False)
    with pytest.raises(OSError,match='interrupted pacing'):
        bundle.capture_environment_files(archive,paths,max_read_bytes_per_second=10)
    assert not list(archive.iterdir())
