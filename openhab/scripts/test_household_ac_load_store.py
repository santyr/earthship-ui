"""Daily preparation admits original files once; serving verifies without fitting."""
from datetime import timedelta
from copy import deepcopy
from pathlib import Path
import importlib,json
import pytest
from test_household_ac_load_sources import START,packet,raw
from household.codec import canonical,identity

NOW=START+timedelta(days=14,hours=1)
CUTOFF=START+timedelta(days=14)


def prepared(tmp_path,monkeypatch):
    api=importlib.import_module('household_ac_load_store');calls=[]
    def capture(**kw):
        calls.append(kw['start'])
        _,source=packet(start=kw['start'],end=kw['end'],rows=[(kw['start'],raw(kw['start']))])
        return source
    monkeypatch.setattr(api,'capture_day',capture)
    result=api.refresh_profile(root=tmp_path,connect=lambda **kw:pytest.fail('fake capture connected'),cutoff=CUTOFF,
        clock=lambda:NOW,remaining=lambda:10.,guard=lambda:None)
    return api,calls,result


def test_daily_source_files_and_admission_are_private_and_idempotent(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);api,calls,result=prepared(tmp_path,monkeypatch)
    assert result['status']=='load_profile_prepared' and len(calls)==14
    source=api.read_current(tmp_path,assessed_at=NOW,guard=lambda:None)
    assert source['artifact']['cutoff']==CUTOFF.isoformat() and source['available_at']==NOW.isoformat()
    assert len(source['admission']['sources'])==14 and source['artifact']['profile']['status']=='insufficient_support'
    before={p.name:p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    again=api.refresh_profile(root=tmp_path,connect=None,cutoff=CUTOFF,clock=lambda:NOW,remaining=lambda:10.,guard=lambda:None)
    assert again['status']=='load_profile_already_current' and len(calls)==14
    assert {p.name:p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}==before
    assert all(p.stat().st_mode&0o777==0o600 for p in tmp_path.iterdir())


def test_serving_reads_hashes_and_compact_replay_without_raw_parsing_or_fit(tmp_path,monkeypatch):
    api,calls,_=prepared(tmp_path,monkeypatch)
    def forbidden(*a,**kw):pytest.fail('serving rebuilt historical day accounting')
    import household_ac_load_artifact as artifacts
    monkeypatch.setattr(artifacts,'build_artifact',forbidden)
    monkeypatch.setattr(api,'_read_day',forbidden)
    result=api.read_current(tmp_path,assessed_at=NOW,guard=lambda:None)
    assert result['schema']=='earthship-ac-load-admitted-source/v1'
    assert len(calls)==14


@pytest.mark.parametrize('damage',['raw','artifact','receipt','pointer','runtime','future','mode','symlink'])
def test_any_changed_original_or_admission_refuses_serving(tmp_path,monkeypatch,damage):
    api,_,_=prepared(tmp_path,monkeypatch);current=json.loads((tmp_path/'current.json').read_bytes());at=NOW
    if damage=='runtime':monkeypatch.setattr(api,'runtime_manifest',lambda:{'changed':'f'*64})
    elif damage=='future':at=NOW-timedelta(seconds=1)
    else:
        admission=json.loads((tmp_path/current['admission_name']).read_bytes())
        name={'raw':admission['sources'][0]['name'],'artifact':admission['artifact']['name'],'receipt':current['admission_name'],
            'pointer':'current.json','mode':admission['sources'][0]['name'],'symlink':admission['sources'][0]['name']}[damage]
        target=tmp_path/name
        if damage=='mode':target.chmod(0o644)
        elif damage=='symlink':
            other=tmp_path/'external';target.rename(other);target.symlink_to(other)
        else:target.write_bytes(target.read_bytes()+b' ')
    with pytest.raises((ValueError,OSError)):api.read_current(tmp_path,assessed_at=at,guard=lambda:None)


def test_later_daily_failure_preserves_current_model_and_originals(tmp_path,monkeypatch):
    api,_,_=prepared(tmp_path,monkeypatch);pointer=(tmp_path/'current.json').read_bytes()
    def failed(**kw):raise ValueError('source unavailable')
    monkeypatch.setattr(api,'capture_day',failed)
    with pytest.raises(ValueError):api.refresh_profile(root=tmp_path,connect=None,cutoff=CUTOFF+timedelta(days=1),clock=lambda:NOW+timedelta(days=1),remaining=lambda:10.,guard=lambda:None)
    assert (tmp_path/'current.json').read_bytes()==pointer
    assert api.read_current(tmp_path,assessed_at=NOW,guard=lambda:None)['artifact']['cutoff']==CUTOFF.isoformat()


def test_freshly_collected_profile_keeps_actual_old_source_expiry(tmp_path,monkeypatch):
    api,_,_=prepared(tmp_path,monkeypatch)
    value=api.read_current(tmp_path,assessed_at=NOW,guard=lambda:None)
    # Each synthetic day only has a thirty-second first interval; none of its
    # hours reaches 99% support. Admission must not invent an observed cutoff.
    assert value['artifact']['profile']['latest_qualified_hour_end'] is None
    assert value['artifact']['profile']['valid_until'] is None


def test_interrupted_immutable_write_leaves_no_partial_original_and_can_retry(tmp_path,monkeypatch):
    api=importlib.import_module('household_ac_load_store');path=tmp_path/'original.json';real=api.os.fsync
    def interrupted(fd):raise OSError('injected interrupted write')
    monkeypatch.setattr(api.os,'fsync',interrupted)
    with pytest.raises(OSError):api._immutable(path,b'original complete bytes')
    assert not path.exists() and not list(tmp_path.iterdir())
    monkeypatch.setattr(api.os,'fsync',real);api._immutable(path,b'original complete bytes')
    assert path.read_bytes()==b'original complete bytes'
    with pytest.raises(ValueError):api._immutable(path,b'changed bytes')
    assert path.read_bytes()==b'original complete bytes'
