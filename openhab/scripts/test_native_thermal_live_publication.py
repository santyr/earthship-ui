"""Native issuer transport is synthetic; capture/candidate replay is genuine."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import pytest
from test_native_thermal_forecast import originals,context,ISSUE,future
from thermal_model.forcing_capture import _canonical
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM


def earlier_geometry(issue):
    from astro_geometry import build_source,build_cache
    from astro_geometry_series import build_series_request,split_series_request,build_series
    from test_native_thermal_inputs import RUNTIME
    points=[issue+timedelta(minutes=5*i) for i in range(1,289)]
    request=build_series_request(points,requested_at=issue-timedelta(seconds=40),latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver')
    caches=[]
    for chunk in split_series_request(request):
        source=build_source(chunk,observed_at=issue-timedelta(seconds=39),native_runtime=RUNTIME,source_status='ONLINE',latitude=38.3739919,longitude=-105.7744609,timezone_name='America/Denver',altitude_m=None)
        raw=''.join(at+'\t30\t180\n' for at in chunk['instants']).encode()
        caches.append(build_cache(chunk,source,native_output=raw,computed_at=issue-timedelta(seconds=35)))
    return build_series(request,caches,expected_native_runtime=RUNTIME)


def fixture(tmp_path,monkeypatch,originals):
    import native_thermal_live as live
    import native_thermal_artifact as artifact
    c,inputs,k=context(tmp_path,monkeypatch,originals)
    from test_google_irradiance_model import fresh_candidate
    from test_google_native_selection import source
    from weather_learning.archive import Archive
    c,runtime,_=fresh_candidate(tmp_path/'preserved-fit',monkeypatch)
    path=tmp_path/'preserved-fit'/(c['artifact_sha256']+'.native-provisional-candidate-v4.json')
    archive=tmp_path/'archive';archive.mkdir(mode=0o700)
    settings=dict(schema=live.LIVE_SCHEMA,weather_source=source(Archive(tmp_path/'google').root),candidate_path=str(path),artifact_sha256=c['artifact_sha256'],
        runtime_sha256=c['runtime_sha256'],evidence_directory=str(archive),native_cutover=(ISSUE-timedelta(days=1)).isoformat())
    clock=[ISSUE-timedelta(seconds=30)]
    monkeypatch.setattr(live,'_clock',lambda:clock[0],raising=False);monkeypatch.setattr(live,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+timedelta(seconds=seconds)),raising=False)
    monkeypatch.setattr(live,'current_runtime',lambda **kw:deepcopy(runtime),raising=False);monkeypatch.setattr(live,'_resource_preflight',lambda:None,raising=False)
    class Backend:
        def __init__(self):self.states={};self.puts=[]
        def collect(self,**kwargs):clock[0]=ISSUE;return deepcopy(inputs)
        def verify_unchanged(self):pass
        def put(self,item,state,*,preflight):preflight();self.states[item]=state;self.puts.append(item)
        def persisted(self,item,state,*,since):clock[0]+=timedelta(milliseconds=10);return {'item':item,'time':int(clock[0].timestamp()*1000),'state':state}
    return live,settings,Backend(),clock,c,earlier_geometry(ISSUE),runtime


def test_native_issuer_retains_exact_v2_origin_and_both_receipts(tmp_path,monkeypatch,originals):
    live,s,b,clock,c,geometry,runtime=fixture(tmp_path,monkeypatch,originals)
    result=live.publish_cycle(s,geometry=geometry,guard=lambda:None,backend=b)
    assert result['status']=='published' and result['delivery_verified'] is True
    assert b.puts==[NUMERIC_ITEM,PUBLICATION_ITEM]
    capture=json.loads(Path(result['origin_path']).read_bytes());delivery=json.loads(Path(result['delivery_path']).read_bytes())
    assert capture['schema']=='earthship-provisional-thermal-origin/v2'
    assert delivery['schema']=='earthship-provisional-thermal-delivery/v2'
    assert delivery['runtime_sha256']==c['runtime_sha256'] and delivery['geometry_series_sha256']==geometry.sha256
    assert json.loads(b.states[PUBLICATION_ITEM])['version']==9
    from household_cycle import load_cycle_delivery
    restored=load_cycle_delivery(result,issue=ISSUE,guard=lambda:None,runtime=runtime,
        expected_artifact_sha256=c['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    assert restored['capture']==capture and restored['native'] is True


@pytest.mark.parametrize('damage',['receipt','runtime','artifact','geometry','changed_candidate'])
def test_native_issuer_refuses_missing_delivery_or_changed_originals(tmp_path,monkeypatch,originals,damage):
    live,s,b,clock,c,g,runtime=fixture(tmp_path,monkeypatch,originals)
    if damage=='receipt':b.persisted=lambda *a,**kw:None
    elif damage=='runtime':s['runtime_sha256']='f'*64
    elif damage=='artifact':s['artifact_sha256']='f'*64
    elif damage=='geometry':
        from test_native_thermal_forecast import future
        g=future(ISSUE,late=True)
    else:
        real=b.collect
        def collect(**kwargs):
            result=real(**kwargs);Path(s['candidate_path']).write_bytes(b'{}');return result
        b.collect=collect
    with pytest.raises(ValueError):live.publish_cycle(s,geometry=g,guard=lambda:None,backend=b)
    assert not list(Path(s['evidence_directory']).glob('origins-*/*.native-provisional-delivery-v2.json'))
    if damage!='receipt':assert b.puts==[]


def test_native_withdrawal_requires_both_persisted_unavailable_states_without_candidate(tmp_path,monkeypatch,originals):
    live,s,b,clock,c,g,runtime=fixture(tmp_path,monkeypatch,originals)
    Path(s['candidate_path']).unlink()
    result=live.withdraw(s,guard=lambda:None,backend=b)
    assert result['status']=='withdrawn' and result['delivery_verified'] is True
    main=json.loads(b.states[PUBLICATION_ITEM]);numeric=json.loads(b.states[NUMERIC_ITEM])
    assert main['schema']=='earthship-provisional-thermal-publication/v2' and main['version']==9
    assert main['status']=='unavailable' and numeric['schema']=='earthship-provisional-thermal-forecast/v2'


def test_native_issuer_loads_prepared_geometry_for_its_exact_issue(tmp_path,monkeypatch,originals):
    live,s,b,clock,c,g,runtime=fixture(tmp_path,monkeypatch,originals);calls=[]
    def read(settings,*,issue,guard):
        assert settings==s and issue==ISSUE;guard();calls.append('geometry');return g
    monkeypatch.setattr(live,'read_geometry',read)
    result=live.publish_cycle(s,guard=lambda:None,backend=b)
    assert result['delivery_verified'] is True and calls==['geometry']


def test_native_collection_starts_with_thirty_seconds_for_parent_and_observer(tmp_path,monkeypatch,originals):
    live,settings,backend,clock,_,geometry,_=fixture(tmp_path,monkeypatch,originals)
    seen=[]
    class Collected(Exception):pass
    def collect(*,issue,known_at):
        seen.append((issue-known_at).total_seconds())
        raise Collected()
    backend.collect=collect
    with pytest.raises(Collected):live.publish_cycle(settings,geometry=geometry,guard=lambda:None,backend=backend)
    assert seen==[30.0]
