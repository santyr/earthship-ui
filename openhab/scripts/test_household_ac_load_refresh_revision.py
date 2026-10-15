"""A scheduled refresh can revalidate changed runtime without losing originals."""
from datetime import timedelta
from copy import deepcopy
from household.codec import canonical
from test_household_ac_load_store import prepared,CUTOFF,NOW
import pytest


def test_normal_daily_refresh_revalidates_runtime_drift_from_original_day_files(tmp_path,monkeypatch):
    api,calls,_=prepared(tmp_path,monkeypatch);old=api.read_current(tmp_path,assessed_at=NOW,guard=lambda:None)
    originals={p.name:p.read_bytes() for p in tmp_path.iterdir() if p.name!='current.json'}
    runtime=deepcopy(api.runtime_manifest());runtime[next(iter(runtime))]='f'*64
    monkeypatch.setattr(api,'runtime_manifest',lambda:runtime)
    with pytest.raises(ValueError):api.read_current(tmp_path,assessed_at=NOW,guard=lambda:None)
    result=api.refresh_profile(root=tmp_path,connect=None,cutoff=CUTOFF,clock=lambda:NOW+timedelta(seconds=1),remaining=lambda:10.,guard=lambda:None)
    assert result['status']=='load_profile_prepared' and result['fit_executed'] is True and len(calls)==14
    new=api.read_current(tmp_path,assessed_at=NOW+timedelta(seconds=1),guard=lambda:None)
    assert new['artifact']['runtime_manifest']==runtime and new['artifact']['artifact_sha256']!=old['artifact']['artifact_sha256']
    assert new['artifact']['profile']['inputs']['hourly_rows']==old['artifact']['profile']['inputs']['hourly_rows']
    assert all((tmp_path/name).read_bytes()==raw for name,raw in originals.items())


def test_daily_refresh_does_not_replace_foreign_current_pointer(tmp_path,monkeypatch):
    api,_,_=prepared(tmp_path,monkeypatch);raw=canonical(dict(schema='unrelated-owner',keep=True));(tmp_path/'current.json').write_bytes(raw)
    with pytest.raises(ValueError):api.refresh_profile(root=tmp_path,connect=None,cutoff=CUTOFF,clock=lambda:NOW,remaining=lambda:10.,guard=lambda:None)
    assert (tmp_path/'current.json').read_bytes()==raw


@pytest.mark.parametrize('runtime_changed',[False,True])
def test_revalidation_never_accepts_resealed_changes_to_retained_originals(tmp_path,monkeypatch,runtime_changed):
    api,_,_=prepared(tmp_path,monkeypatch);pointer=(tmp_path/'current.json').read_bytes()
    import gzip,json
    from household.codec import identity
    target=next(tmp_path.glob('*.ac-day.json.gz'));packet=json.loads(gzip.decompress(target.read_bytes()))
    payload=json.loads(packet['rows'][0][1]);payload['fields']['inverter.ac_output_w']['watts']=0;packet['rows'][0][1]=json.dumps(payload)
    packet['source_sha256']=identity({k:v for k,v in packet.items() if k!='source_sha256'});target.write_bytes(gzip.compress(canonical(packet),mtime=0))
    if runtime_changed:
        runtime=deepcopy(api.runtime_manifest());runtime[next(iter(runtime))]='f'*64;monkeypatch.setattr(api,'runtime_manifest',lambda:runtime)
    with pytest.raises(ValueError):api.refresh_profile(root=tmp_path,connect=None,cutoff=CUTOFF,clock=lambda:NOW+timedelta(seconds=1),remaining=lambda:10.,guard=lambda:None)
    assert (tmp_path/'current.json').read_bytes()==pointer
