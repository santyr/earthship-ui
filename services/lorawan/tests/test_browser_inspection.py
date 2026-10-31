"""Browser reads keep the admitted context and fresh objects without CLI tasks."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from services.lorawan.tests import stack_ownership as ownership
from services.lorawan.tests import qualification_runtime as runtime
from services.lorawan.tests import qualification_guard as guard


@pytest.fixture
def inspector(tmp_path, monkeypatch):
    nonce = 'a' * 32; digest = 'b' * 64
    ids = {name:f'{i:064x}' for i,name in enumerate((*ownership.SERVICES,'simulator'),1)}
    image = 'sha256:' + 'c' * 64
    unit = 'earthship-sensor-guard-' + nonce + '.service'
    stack = dict(containers={name:{'Id':value} for name,value in ids.items()},
                 rendered={'services':{'sentinel':'original-admission'}},
                 images={image:image},volumes={'owned_volume':{}})
    envelope = dict(mode='qualification', controller={'guardian_unit':unit}, stack=stack)
    receipt = dict(manifest_sha256=digest,ids=ids,phase='armed',workload_phase='browser',pending=None)
    calls = []; lease_reads = []; receipt_reads = []
    class Lease:
        def __init__(self,path,pin,**kwargs):
            assert path == tmp_path/'manifest.json' and pin == digest
            assert kwargs['root'] == tmp_path and kwargs['nonce'] == nonce
        def verify(self):
            lease_reads.append(True); return deepcopy(envelope)
    def api(method,path):
        assert method == 'GET'; calls.append((method,path))
        if path == '/containers/json?all=1': return [{'Id':value} for value in ids.values()]
        if path.startswith('/containers/'): return {'Id':path.split('/')[2], 'fresh':True}
        if path.startswith('/images/'): return {'Id':image,'fresh':True}
        if path == '/volumes/owned_volume': return {'Name':'owned_volume','fresh':True}
        raise AssertionError('unexpected transport path')
    class Backend:
        def __init__(self,value,**kwargs): assert value == stack and kwargs['request'] is api
        def configuration(self): calls.append(('source','fresh-compose-byte-check'))
    def read(path):
        assert str(path) == '/run/' + unit.removesuffix('.service') + '/receipt.json'
        receipt_reads.append(True); return deepcopy(receipt)
    monkeypatch.setattr(ownership,'ROOT',tmp_path)
    monkeypatch.setenv('SENSOR_BROWSER_INSPECTION','1')
    monkeypatch.setenv('SENSOR_QUALIFICATION_NONCE',nonce)
    monkeypatch.setenv('SENSOR_QUALIFICATION_SHA256',digest)
    monkeypatch.setenv('SENSOR_QUALIFICATION_MANIFEST',str(tmp_path/'manifest.json'))
    monkeypatch.setattr(runtime,'Lease',Lease)
    monkeypatch.setattr(runtime,'DockerSocket',lambda:api)
    monkeypatch.setattr(runtime,'DockerBackend',Backend)
    monkeypatch.setattr(guard,'read_private',read)
    monkeypatch.setattr(ownership.subprocess,'run',lambda *a,**k:pytest.fail('browser spawned CLI'))
    return SimpleNamespace(root=tmp_path,ids=ids,image=image,envelope=envelope,receipt=receipt,calls=calls,lease_reads=lease_reads,receipt_reads=receipt_reads,Backend=Backend)


@pytest.mark.parametrize('command', ['rendered','compose-ids','all-ids','containers','image','volume'])
def test_closed_browser_read_translations_keep_fresh_objects(inspector, command):
    s = inspector
    prefix = ['compose','-f',str(s.root/'deploy/lorawan/compose.test.yaml'),'--profile','*']
    commands = {'rendered':[*prefix,'config','--format','json'],
                'compose-ids':[*prefix,'ps','--all','-q',*ownership.SERVICES],
                'all-ids':['ps','--all','--quiet','--no-trunc'],
                'containers':['inspect',*s.ids.values()],
                'image':['image','inspect',s.image], 'volume':['volume','inspect','owned_volume']}
    raw = ownership._inspect(commands[command])
    assert len(s.lease_reads) == len(s.receipt_reads) == 2
    assert s.calls[0] == ('source','fresh-compose-byte-check')
    if command == 'rendered': assert json.loads(raw) == s.envelope['stack']['rendered']
    elif command == 'compose-ids': assert raw.split() == [s.ids[name] for name in ownership.SERVICES]
    elif command == 'all-ids': assert set(raw.split()) == set(s.ids.values())
    else: assert all(row['fresh'] is True for row in json.loads(raw))
    assert all(method in ('source','GET') for method,_ in s.calls)


@pytest.mark.parametrize('change',['mode','unit','digest','ids','python','cleanup','pending'])
def test_wrong_browser_context_refuses_before_any_inspection(inspector,change):
    s = inspector
    if change == 'mode': s.envelope['mode']='lifecycle-proof'
    elif change == 'unit': s.envelope['controller']['guardian_unit']='other.service'
    elif change == 'digest': s.receipt['manifest_sha256']='c'*64
    elif change == 'ids': s.receipt['ids']={}
    elif change == 'python': s.receipt['workload_phase']='python'
    elif change == 'cleanup': s.receipt['phase']='cleanup'
    else: s.receipt['pending']={'action':'stop'}
    with pytest.raises(guard.Refused): ownership._inspect(['ps','--all','--quiet','--no-trunc'])
    assert s.calls == []


@pytest.mark.parametrize('command',[['stop','anything'],['inspect','not-an-id'],['volume','inspect','foreign'],['image','inspect','foreign'],['compose','config']])
def test_unrecognized_or_foreign_command_is_never_translated(inspector,command):
    with pytest.raises((guard.Refused,ownership.IsolationError)): ownership._inspect(command)
    assert all(method != 'GET' for method,_ in inspector.calls)


def test_source_change_refuses_frozen_rendered_data(inspector,monkeypatch):
    def changed(self): raise guard.Refused('changed Compose bytes')
    monkeypatch.setattr(inspector.Backend,'configuration',changed)
    args=['compose','-f',str(inspector.root/'deploy/lorawan/compose.test.yaml'),'--profile','*','config','--format','json']
    with pytest.raises(guard.Refused): ownership._inspect(args)


def test_phase_drift_during_api_read_refuses_result(inspector,monkeypatch):
    original = guard.read_private; reads=[]
    def read(path):
        result=original(path); reads.append(True)
        if len(reads)==2: result['phase']='cleanup'
        return result
    monkeypatch.setattr(guard,'read_private',read)
    with pytest.raises(guard.Refused,match='context changed'):
        ownership._inspect(['ps','--all','--quiet','--no-trunc'])
