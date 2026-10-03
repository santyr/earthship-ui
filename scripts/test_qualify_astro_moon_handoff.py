from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('moon_handoff_fixture_tests',Path(__file__).with_name('qualify-astro-moon-handoff.py'))
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


def pg(socket):
    return {'Config':{'Labels':{m.PG_LABEL:'owner'},'Image':m.PG_IMAGE,'User':'999:999'},
        'HostConfig':{'NetworkMode':'none','Privileged':False,'ReadonlyRootfs':True,'PortBindings':None,
                     'Binds':None,'Devices':[],'Memory':512*1024**2,'MemorySwap':512*1024**2,
                     'NanoCpus':1_000_000_000},
        'NetworkSettings':{'Networks':{'none':{}},'Ports':{'5432/tcp':None}},
        'Mounts':[{'Type':'bind','Source':str(socket),'Destination':'/var/run/postgresql','RW':True}]}


def socket_path(tmp_path):
    root=tmp_path/'earthship-moon-pg-socket-fixture';root.mkdir(mode=0o700)
    socket=root/'socket';socket.mkdir();socket.chmod(0o1777)
    return socket


def test_owned_networkless_socket_database_accepted(tmp_path):
    socket=socket_path(tmp_path)
    m.validate_pg(pg(socket),'owner',socket)


@pytest.mark.parametrize('fault',['owner','image','user','network','privileged','root','mount','device',
                                  'memory','swap','cpu','published_port','wrong_source','wrong_target','extra_network'])
def test_containment_or_production_address_overlap_refused(fault,tmp_path):
    socket=socket_path(tmp_path);row=pg(socket)
    if fault=='owner':row['Config']['Labels'][m.PG_LABEL]='other'
    elif fault=='image':row['Config']['Image']='unknown'
    elif fault=='user':row['Config']['User']='root'
    elif fault=='network':row['HostConfig']['NetworkMode']='host'
    elif fault=='privileged':row['HostConfig']['Privileged']=True
    elif fault=='root':row['HostConfig']['ReadonlyRootfs']=False
    elif fault=='mount':row['HostConfig']['Binds']=['/etc:/host']
    elif fault=='device':row['HostConfig']['Devices']=['hardware']
    elif fault=='memory':row['HostConfig']['Memory']=0
    elif fault=='swap':row['HostConfig']['MemorySwap']=-1
    elif fault=='cpu':row['HostConfig']['NanoCpus']=0
    elif fault=='published_port':row['NetworkSettings']['Ports']['5432/tcp']=[{'HostIp':'127.0.0.1','HostPort':'5432'}]
    elif fault=='wrong_source':row['Mounts'][0]['Source']='/var/run/postgresql'
    elif fault=='wrong_target':row['Mounts'][0]['Destination']='/var/lib/postgresql/data'
    else:row['NetworkSettings']['Networks']['unrelated']={}
    with pytest.raises(RuntimeError):m.validate_pg(row,'owner',socket)


def test_sun_fixture_comparator_drops_only_declared_probe_link_enrichment():
    row={'UID':'astro:sun:local','configuration':{'interval':300},
         'channels':[{'id':'position#elevation','linkedItems':['production-item'],'defaultTags':[]}]}
    other=deepcopy(row);other['channels'][0]['linkedItems']=['Sun_Position_Elevation']
    assert m.sun_contract(row)==m.sun_contract(other)
    other['channels'][0]['defaultTags']=['changed']
    assert m.sun_contract(row)!=m.sun_contract(other)
    assert row['channels'][0]['linkedItems']==['production-item']


def test_fixture_does_not_open_production_gates():
    # Metadata approval is independent of authority to mutate production.
    assert m.m.LIVE_RELEASE_READY is False


def test_fixture_refuses_open_live_gate_even_with_metadata_approved(monkeypatch):
    monkeypatch.setattr(m.m, 'METADATA_DEVIATION_APPROVED', True)
    monkeypatch.setattr(m.m, 'LIVE_RELEASE_READY', True)
    monkeypatch.setattr(m.q, 'validate_container', lambda *_: None)
    monkeypatch.setattr(m.q.runtime, 'run', lambda *_: b'[{}]')
    ops = m.FixtureOperations({'container': 'owned', 'marker': 'owner'}, None)
    with pytest.raises(RuntimeError, match='live gate'):
        ops.validate()


@pytest.mark.parametrize('method,path,body',[('POST','/items/SouthOutlet',{}),('DELETE','/things/other',None),
    ('PUT','/things/astro:moon:local',{'unreviewed':True})])
def test_fixture_mutation_scope_refuses_before_transport(monkeypatch,method,path,body):
    def forbidden(*a):pytest.fail('no REST call')
    ops=m.FixtureOperations({'container':'owned','marker':'owner','rest':forbidden},None)
    monkeypatch.setattr(ops,'validate',lambda:None)
    with pytest.raises(RuntimeError):ops.request(method,path,{'UID':m.q.UID},body)


def test_fixture_receipt_backend_is_not_production_backend():
    assert not issubclass(m.FixtureOperations,m.m.ProductionOperations)


def test_create_failure_reports_only_safe_category(monkeypatch,capsys):
    from types import SimpleNamespace
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:SimpleNamespace(
        returncode=1,stdout=b'',stderr=b'invalid mount config: bind source path does not exist private-secret'))
    with pytest.raises(RuntimeError):m.create_database_container(['docker','create'])
    assert capsys.readouterr().out=='isolated_database_create_failure=socket_path_not_visible\n'


def test_database_creation_records_exact_identity_before_start(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**k:SimpleNamespace(
        returncode=0,stdout=b'a'*64+b'\n',stderr=b''))
    assert m.create_database_container(['docker','create'])=='a'*64
