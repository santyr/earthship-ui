"""Earlier native preparation is immutable and pinned to the selected model."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import pytest
from thermal_model.forcing_capture import _canonical
from test_native_thermal_live_publication import fixture,originals,ISSUE


def prepared(tmp_path,monkeypatch,originals):
    live,s,b,clock,c,g,runtime=fixture(tmp_path,monkeypatch,originals)
    folder=tmp_path/'geometry';folder.mkdir(mode=0o700);s['geometry_directory']=str(folder)
    clock[0]=ISSUE-timedelta(seconds=100)
    from test_native_thermal_inputs import RUNTIME
    import astro_geometry_worker as worker
    from astro_geometry import build_cache
    monkeypatch.setattr(worker,'runtime_identity',lambda *a,**kw:deepcopy(RUNTIME))
    calls=[]
    def capture(request,source,**kw):
        calls.append(deepcopy(request));kw['guard']();clock[0]+=timedelta(seconds=5)
        raw=''.join(at+'\t30\t180\n' for at in request['instants']).encode()
        return build_cache(request,source,native_output=raw,computed_at=clock[0])
    monkeypatch.setattr(worker,'capture_batch',capture)
    return live,s,clock,c,g,runtime,calls


def test_geometry_preparation_batches_whole_future_grid_and_readbacks_before_collection(tmp_path,monkeypatch,originals):
    live,s,clock,c,g,runtime,calls=prepared(tmp_path,monkeypatch,originals)
    result=live.prepare_geometry(s,issue=ISSUE,library_paths={},guard=lambda:None)
    assert result['status']=='prepared' and [len(row['instants']) for row in calls]==[128,128,32]
    loaded=live.read_geometry(s,issue=ISSUE,guard=lambda:None)
    assert loaded.descriptor()['point_count']==288
    assert loaded.descriptor()['native_runtime']==g.descriptor()['native_runtime']
    assert loaded.descriptor()['available_at']<ISSUE.isoformat()
    body=json.loads(Path(result['path']).read_bytes())
    assert body['artifact_sha256']==c['artifact_sha256'] and body['runtime_sha256']==c['runtime_sha256']
    assert Path(result['path']).stat().st_mode&0o777==0o600


@pytest.mark.parametrize('damage',['issue','artifact','runtime','geometry','clock','suffix','extra'])
def test_prepared_geometry_refuses_resealed_wrong_model_or_clock(tmp_path,monkeypatch,originals,damage):
    live,s,clock,c,g,runtime,calls=prepared(tmp_path,monkeypatch,originals)
    result=live.prepare_geometry(s,issue=ISSUE,library_paths={},guard=lambda:None)
    path=Path(result['path']);body=json.loads(path.read_bytes())
    if damage=='issue':body['issued_at']=(ISSUE+timedelta(minutes=5)).isoformat()
    elif damage in ('artifact','runtime'):body[damage+'_sha256']='f'*64
    elif damage=='geometry':body['geometry_series_sha256']='f'*64
    elif damage=='clock':body['prepared_at']=(ISSUE+timedelta(seconds=1)).isoformat()
    elif damage=='extra':body['authorized_action']=True
    else:
        wrong=path.with_name('wrong.json');path.rename(wrong);path=wrong
    from native_thermal_forecast import digest
    body['preparation_sha256']=digest(body,'preparation_sha256');path.write_bytes(_canonical(body))
    with pytest.raises((ValueError,OSError)):live.read_geometry(s,issue=ISSUE,guard=lambda:None)


def test_late_geometry_preparation_never_publishes_packet(tmp_path,monkeypatch,originals):
    live,s,clock,c,g,runtime,calls=prepared(tmp_path,monkeypatch,originals)
    clock[0]=ISSUE-timedelta(seconds=25)
    with pytest.raises(ValueError):live.prepare_geometry(s,issue=ISSUE,library_paths={},guard=lambda:None)
    assert not list(Path(s['geometry_directory']).glob('*.native-forecast-geometry-v1.json'))


def settings_file(tmp_path,s):
    from native_thermal_live import SOURCE_FIELDS
    s=deepcopy(s);s.update(openhab_base='http://127.0.0.1:8080/rest',shared_lock=str(tmp_path/'lock'))
    for key in (SOURCE_FIELDS-{'candidate_path'})|{'shared_lock'}:
        path=tmp_path/key;path.write_bytes(b'synthetic owned fixture');path.chmod(0o600);s[key]=str(path)
    folder=tmp_path/'geometry';folder.mkdir(mode=0o700,exist_ok=True);s['geometry_directory']=str(folder)
    path=tmp_path/'settings.json';path.write_bytes(_canonical(s));path.chmod(0o600);return path,s


def test_native_settings_accept_only_owned_google_profile_and_external_model_pins(tmp_path,monkeypatch,originals):
    live,s,_,_,_,_,_=fixture(tmp_path,monkeypatch,originals);path,s=settings_file(tmp_path,s)
    assert live.load_settings(path)==s
    for damage in ('schema','artifact','runtime','extra'):
        wrong=deepcopy(s)
        if damage=='schema':wrong['schema']='earthship-provisional-thermal-live-config/v1'
        elif damage=='extra':wrong['command_endpoint']='unapproved'
        else:wrong[damage+'_sha256']='invalid'
        path.write_bytes(_canonical(wrong))
        with pytest.raises(ValueError):live.load_settings(path)


def test_native_withdrawal_settings_allow_absent_candidate_and_geometry(tmp_path,monkeypatch,originals):
    live,s,_,_,_,_,_=fixture(tmp_path,monkeypatch,originals);path,s=settings_file(tmp_path,s)
    Path(s['candidate_path']).unlink();Path(s['geometry_directory']).rmdir()
    assert live.load_settings(path,withdraw=True)==s
    with pytest.raises((ValueError,OSError)):live.load_settings(path)
