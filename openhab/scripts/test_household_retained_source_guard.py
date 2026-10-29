"""Every retained-worker checkpoint still reads all source bytes and custody."""
from pathlib import Path
import os
import pytest
from household_forecast_score import RetainedSourceGuard
from household_score_report_reuse import _json_key


def sources(tmp_path):
    parent=tmp_path/'parents'/'selected';parent.mkdir(parents=True)
    paths=[]
    for i,kind in enumerate(('owned','private','source')):
        p=parent/(str(i)+'.json');p.write_bytes((b'original '+str(i).encode())*100)
        p.chmod(0o600 if kind=='private' else 0o644)
        paths.append((p,p.read_bytes(),kind))
    return tuple(paths)


def test_every_checkpoint_reads_every_complete_file(tmp_path,monkeypatch):
    refs=sources(tmp_path);guard=RetainedSourceGuard(refs);original=os.read;seen=[]
    def read(fd,size):
        path=Path(os.readlink('/proc/self/fd/'+str(fd)));value=original(fd,size)
        seen.append((path,value));return value
    monkeypatch.setattr(os,'read',read)
    guard();guard()
    assert seen==[(p,raw) for _ in range(2) for p,raw,_ in refs]


@pytest.mark.parametrize('damage',['bytes','replacement','symlink','mode','parent'])
def test_checkpoint_refuses_source_or_parent_changes(tmp_path,damage):
    refs=sources(tmp_path);guard=RetainedSourceGuard(refs);p,raw,_=refs[0]
    if damage=='bytes':p.write_bytes(b'x'*len(raw))
    elif damage=='replacement':
        q=p.with_name('replacement');q.write_bytes(raw);q.chmod(0o644);q.replace(p)
    elif damage=='symlink':
        q=p.with_name('target');p.rename(q);p.symlink_to(q)
    elif damage=='mode':p.chmod(0o600)
    else:
        parent=p.parent;old=parent.with_name('moved');parent.rename(old);parent.symlink_to(old,target_is_directory=True)
    with pytest.raises(ValueError,match='retained worker changed'):guard()


def test_later_read_cannot_change_an_earlier_original(tmp_path,monkeypatch):
    refs=sources(tmp_path);guard=RetainedSourceGuard(refs);original=os.read;count=[]
    def read(fd,size):
        value=original(fd,size);count.append(1)
        if len(count)==2:refs[0][0].write_bytes(b'x'*len(refs[0][1]))
        return value
    monkeypatch.setattr(os,'read',read)
    with pytest.raises(ValueError,match='retained worker changed'):guard()


def test_file_descriptor_closes_on_read_failure(tmp_path,monkeypatch):
    refs=sources(tmp_path);guard=RetainedSourceGuard(refs);fds=[]
    def fail(fd,size):fds.append(fd);raise OSError('read refused')
    monkeypatch.setattr(os,'read',fail)
    with pytest.raises(ValueError,match='retained worker changed'):guard()
    with pytest.raises(OSError):os.fstat(fds[0])


@pytest.mark.parametrize('kind,mode',[('private',0o644),('source',0o666)])
def test_original_private_and_source_modes_remain_required(tmp_path,kind,mode):
    refs=sources(tmp_path);p,raw,_=refs[0];p.chmod(mode)
    with pytest.raises(ValueError):RetainedSourceGuard(((p,raw,kind),))


def test_canonical_copy_fallback_preserves_aliased_original_inputs():
    child={'value':[1,2]}
    with pytest.raises(TypeError):_json_key({'a':child,'b':child})
    assert _json_key({'a':{'value':[1,2]},'b':{'value':[1,2]}})
