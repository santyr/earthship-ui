"""Invocation-local original-byte guards, never release qualification evidence."""
from pathlib import Path
import pytest


def source(tmp_path,name='source.json',raw=b'{}'):
    tmp_path.chmod(0o700);p=tmp_path/name;p.write_bytes(raw);p.chmod(0o600);return p


@pytest.mark.parametrize('reader',['runtime','policy','origin','forecast'])
def test_every_original_read_seam_is_observed_and_rechecked(tmp_path,reader):
    from thermal_model.replay_budget import capture_source_reads
    from thermal_model.origin_capture import _source_bytes,_private_file
    from thermal_model.policy_registration import _read_private
    from forecast_input_capture import _read
    p=source(tmp_path)
    read={'runtime':lambda:_source_bytes(p,maximum=32),'policy':lambda:_read_private(p),'origin':lambda:_private_file(p),'forecast':lambda:_read(p)}[reader]
    with capture_source_reads() as inventory:read()
    assert inventory.file_count==1
    inventory.verify();p.write_bytes(b'{"changed":true}')
    with pytest.raises(ValueError):inventory.verify()


def test_nested_observers_are_isolated_and_restored(tmp_path):
    from thermal_model.replay_budget import capture_source_reads
    from thermal_model.origin_capture import _source_bytes
    a=source(tmp_path,'a.json');b=source(tmp_path,'b.json')
    with capture_source_reads() as outer:
        _source_bytes(a,maximum=32)
        with capture_source_reads() as inner:_source_bytes(b,maximum=32)
        _source_bytes(a,maximum=32)
    assert outer.file_count==1 and inner.file_count==1
    b.unlink();outer.verify()
    with pytest.raises(ValueError):inner.verify()


@pytest.mark.parametrize('damage',['missing','permissions','symlink'])
def test_original_metadata_and_identity_loss_refuse(tmp_path,damage):
    from thermal_model.replay_budget import capture_source_reads
    from thermal_model.origin_capture import _source_bytes
    p=source(tmp_path)
    with capture_source_reads() as inventory:_source_bytes(p,maximum=32)
    if damage=='permissions':p.chmod(0o644)
    elif damage=='missing':p.unlink()
    else:
        other=source(tmp_path,'other.json');p.unlink();p.symlink_to(other)
    with pytest.raises(ValueError):inventory.verify()


def test_byte_recheck_obeys_parent_deadline(tmp_path):
    from thermal_model.replay_budget import capture_source_reads,shared_replay_budget
    from thermal_model.origin_capture import _source_bytes
    p=source(tmp_path,raw=b'x'*2000000)
    with capture_source_reads() as inventory:_source_bytes(p,maximum=2000000)
    calls=[]
    def remaining():calls.append(True);return 1 if len(calls)<4 else 0
    with pytest.raises(ValueError):
        with shared_replay_budget(remaining):inventory.verify()
    assert len(calls)>=4


def test_changes_during_qualification_and_inventory_overflow_refuse(tmp_path,monkeypatch):
    from thermal_model import replay_budget as m
    from thermal_model.origin_capture import _source_bytes
    a=source(tmp_path,'a.json');b=source(tmp_path,'b.json')
    with pytest.raises(ValueError):
        with m.capture_source_reads():
            _source_bytes(a,maximum=32);a.write_bytes(b'{"new":1}');_source_bytes(a,maximum=32)
    monkeypatch.setattr(m,'MAX_OBSERVED_FILES',1)
    with pytest.raises(ValueError):
        with m.capture_source_reads():_source_bytes(a,maximum=32);_source_bytes(b,maximum=32)


@pytest.mark.parametrize('bootstrap',[False,True])
def test_actual_preparation_wrapper_retains_its_original_read_guard(tmp_path,monkeypatch,bootstrap):
    from thermal_model import installed_shade_publication as p
    from thermal_model.runtime_bundle import _owned_bytes
    original=source(tmp_path)
    cls=p.PreparedCompressedBaseBootstrap if bootstrap else p.PreparedCompressedInstalledQualification
    implementation='_prepare_compressed_base_bootstrap' if bootstrap else '_prepare_compressed_installed_qualification'
    def prepare(_):
        _owned_bytes(original,32)
        return cls(b'{}',b'{}',True)
    monkeypatch.setattr(p,implementation,prepare)
    run=p.prepare_compressed_base_bootstrap if bootstrap else p.prepare_compressed_installed_qualification
    result=run(original)
    assert callable(result.source_guard)
    result.source_guard();original.unlink()
    with pytest.raises(ValueError):result.source_guard()


def test_recheck_detects_earlier_original_changed_while_later_file_is_read(tmp_path,monkeypatch):
    import os
    from thermal_model.replay_budget import capture_source_reads
    from thermal_model.origin_capture import _source_bytes
    a=source(tmp_path,'a.json');b=source(tmp_path,'b.json')
    with capture_source_reads() as inventory:_source_bytes(a,maximum=32);_source_bytes(b,maximum=32)
    inode=b.stat().st_ino;read=os.read;changed=[]
    def later(fd,size):
        if os.fstat(fd).st_ino==inode and not changed:
            changed.append(True);a.write_bytes(b'{"changed":true}')
        return read(fd,size)
    monkeypatch.setattr(os,'read',later)
    with pytest.raises(ValueError):inventory.verify()
    assert changed
