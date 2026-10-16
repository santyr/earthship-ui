"""Migration boundary/failure tests; no network, SQL writes or live mutations."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
from pathlib import Path
import tempfile
import pytest

spec = importlib.util.spec_from_file_location('charging_item_migration',
    Path(__file__).with_name('migrate-battery-charging-status-item.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

ORIGINAL = {'name': 'BatteryChargingStatus', 'type': 'Switch',
    'label': 'BatteryChargingStatus', 'category': '', 'tags': [],
    'groupNames': [], 'editable': True, 'state': 'OFF'}

def test_rejects_state_commands_and_other_resource_mutations():
    for method, path, body in [
        ('PUT', '/items/BatteryChargingStatus/state', 'ON'),
        ('POST', '/items/BatteryChargingStatus', 'ON'),
        ('DELETE', '/items/BatteryIcon', None),
        ('POST', '/rules/hex_south_planter_fan/enable', False),
        ('POST', '/rules/UpdateBatteryIcon/runnow', None),
        ('PUT', '/items/BatteryChargingStatus', {**ORIGINAL, 'state': 'ON'}),
        ('POST', '/rules/UpdateBatteryIcon/enable', 'false'),
    ]:
        with pytest.raises(RuntimeError):
            m.allowed_mutation(method, path, body)

def test_original_descriptor_and_display_enable_are_the_only_writes():
    m.allowed_mutation('DELETE', '/items/BatteryChargingStatus', None)
    m.allowed_mutation('PUT', '/items/BatteryChargingStatus',
        {k: v for k, v in ORIGINAL.items() if k not in ('editable', 'state')})
    m.allowed_mutation('POST', '/rules/UpdateBatteryIcon/enable', False)
    m.allowed_mutation('POST', '/rules/UpdateBatteryIcon/enable', True)

def test_closed_gate_refuses_before_transport_or_credential_access(monkeypatch):
    monkeypatch.setattr(m, 'urlopen', lambda *_a, **_k: pytest.fail('network reached'))
    monkeypatch.setattr(m.oh, 'token', lambda: pytest.fail('credential reached'))
    with pytest.raises(RuntimeError, match='release gate'):
        m.request('DELETE', '/items/BatteryChargingStatus')


def test_open_gate_still_refuses_commands_and_other_rule_scope_before_network(monkeypatch):
    monkeypatch.setattr(m,'RELEASE_READY',True)
    monkeypatch.setattr(m,'urlopen',lambda *_a,**_k:pytest.fail('network reached'))
    monkeypatch.setattr(m.oh,'token',lambda:pytest.fail('credential reached'))
    for method,path,body in [('PUT','/items/BatteryChargingStatus/state','ON'),
            ('POST','/rules/hex_south_planter_fan/enable',False)]:
        with pytest.raises(RuntimeError,match='scope'):
            m.request(method,path,body)

def test_apply_gate_refuses_before_database_or_preflight(monkeypatch):
    monkeypatch.setattr(m, 'preflight', lambda *_a: pytest.fail('preflight reached'))
    with pytest.raises(SystemExit):
        m.main(['--apply'])

def test_original_switch_only_accepts_exact_valid_state_and_descriptor():
    m.validate_item(ORIGINAL, managed=True, state='OFF')
    m.validate_item({**ORIGINAL, 'editable': False, 'category': None},
                    managed=False, state='OFF')
    for damage in [dict(type='String'), dict(label='changed'), dict(state='NULL'),
            dict(groupNames=['gForecast']), dict(tags=['Control']),
            dict(metadata={'command': {'value': 'ON'}}), dict(editable=False)]:
        with pytest.raises(RuntimeError):
            m.validate_item({**ORIGINAL, **damage}, managed=True, state='OFF')


@pytest.mark.parametrize('provider',[None,0,1,'false'])
def test_unknown_provider_marker_never_qualifies_recovery(provider):
    with pytest.raises(RuntimeError,match='provider'):
        m.validate_item({**ORIGINAL,'editable':provider},managed=provider)

def test_writer_contract_accepts_runtime_registration_change_only():
    rule = {'uid': 'UpdateBatteryIcon', 'editable': False,
        'triggers': [{'type': 'timer.GenericCronTrigger',
                      'configuration': {'cronExpression': '0/30 * * * * ?'}}],
        'conditions': [], 'actions': [{'type': 'jsr223.ScriptedAction',
                                      'configuration': {'privId': 'i12'}}],
        'status': {'status': 'IDLE', 'statusDetail': 'NONE'}}
    m.validate_writer(rule, disabled=False)
    for change in ['managed', 'extra_trigger', 'wrong_cron', 'extra_action',
                   'unknown_action', 'condition', 'wrong_uid', 'unknown_priv_id']:
        bad = deepcopy(rule)
        if change == 'managed': bad['editable'] = True
        elif change == 'extra_trigger': bad['triggers'].append(deepcopy(bad['triggers'][0]))
        elif change == 'wrong_cron': bad['triggers'][0]['configuration']['cronExpression'] = '* * * * * ?'
        elif change == 'extra_action': bad['actions'].append(deepcopy(bad['actions'][0]))
        elif change == 'unknown_action': bad['actions'][0]['configuration']['script'] = 'untrusted'
        elif change == 'condition': bad['conditions'] = [{'type': 'unknown'}]
        elif change == 'wrong_uid': bad['uid'] = 'hex_southoutlet_cycle'
        else: bad['actions'][0]['configuration']['privId'] = 'i12\n'
        with pytest.raises(RuntimeError): m.validate_writer(bad, disabled=False)

def test_owned_withdrawal_never_adopts_matching_bytes_from_another_inode(tmp_path):
    target = tmp_path/'candidate.items'; target.write_bytes(b'qualified source')
    owned = (target.stat().st_dev, target.stat().st_ino)
    replacement = tmp_path/'replacement.items'; replacement.write_bytes(target.read_bytes())
    replacement.replace(target)
    directory = tmp_path/'private'; directory.mkdir(mode=0o700)
    with pytest.raises(RuntimeError, match='ownership'):
        m.withdraw_owned(target, directory, sha256(b'qualified source').hexdigest(), owned, 1)
    assert target.read_bytes() == b'qualified source' and not list(directory.iterdir())

def test_withdrawal_preserves_original_and_refuses_existing_recovery_entry(tmp_path):
    target = tmp_path/'candidate.items'; target.write_bytes(b'qualified source')
    identity = (target.stat().st_dev, target.stat().st_ino)
    directory = tmp_path/'private'; directory.mkdir(mode=0o700)
    saved = m.withdraw_owned(target, directory, sha256(b'qualified source').hexdigest(), identity, 1)
    assert not target.exists() and saved.read_bytes() == b'qualified source'
    assert saved.stat().st_mode & 0o777 == 0o600
    target.write_bytes(b'qualified source'); identity=(target.stat().st_dev,target.stat().st_ino)
    with pytest.raises(RuntimeError, match='recovery entry'):
        m.withdraw_owned(target, directory, sha256(b'qualified source').hexdigest(), identity, 1)
    assert target.exists() and saved.read_bytes() == b'qualified source'


def test_owned_withdrawal_preserves_backup_on_another_filesystem(tmp_path):
    if not Path('/dev/shm').is_dir():
        pytest.skip('no separate temporary filesystem available')
    target=tmp_path/'candidate.items';target.write_bytes(b'qualified source')
    identity=(target.stat().st_dev,target.stat().st_ino)
    with tempfile.TemporaryDirectory(prefix='charging-withdrawal-',dir='/dev/shm') as backup:
        directory=Path(backup)
        if directory.stat().st_dev==target.stat().st_dev:
            pytest.skip('temporary directories share a filesystem')
        saved=m.withdraw_owned(target,directory,sha256(target.read_bytes()).hexdigest(),identity,1)
        assert not target.exists() and saved.read_bytes()==b'qualified source'
        assert saved.stat().st_dev!=identity[0] and saved.stat().st_mode&0o777==0o600


def test_failed_recovery_copy_fsync_preserves_watched_file(tmp_path,monkeypatch):
    target=tmp_path/'candidate.items';target.write_bytes(b'qualified source')
    identity=(target.stat().st_dev,target.stat().st_ino)
    directory=tmp_path/'private';directory.mkdir(mode=0o700)
    def failed_sync(_fd):
        raise OSError('injected recovery-copy fsync failure')
    monkeypatch.setattr(m.os,'fsync',failed_sync)
    with pytest.raises(OSError,match='recovery-copy fsync failure'):
        m.withdraw_owned(target,directory,sha256(target.read_bytes()).hexdigest(),identity,1)
    assert target.exists() and (target.stat().st_dev,target.stat().st_ino)==identity


def test_replacement_after_durable_backup_is_never_removed(tmp_path,monkeypatch):
    target=tmp_path/'candidate.items';target.write_bytes(b'qualified source')
    identity=(target.stat().st_dev,target.stat().st_ino)
    directory=tmp_path/'private';directory.mkdir(mode=0o700)
    original_sync=m.history_tools.sync_directory
    def replaced_after_sync(path):
        original_sync(path)
        if path==directory:
            replacement=tmp_path/'replacement';replacement.write_bytes(target.read_bytes())
            replacement.replace(target)
    monkeypatch.setattr(m.history_tools,'sync_directory',replaced_after_sync)
    with pytest.raises(RuntimeError,match='watched file ownership drift'):
        m.withdraw_owned(target,directory,sha256(target.read_bytes()).hexdigest(),identity,1)
    assert target.exists() and (target.stat().st_dev,target.stat().st_ino)!=identity
    assert (directory/'withdrawal-1.items').read_bytes()==b'qualified source'


@pytest.fixture
def handoff_environment(monkeypatch, tmp_path):
    """Replace only REST/SQL/process reads; exercise real watched-file methods."""
    source = Path(__file__).resolve().parents[1]/'openhab/file-config/items/battery-charging-status.items'
    target = tmp_path/'watched'/'battery-charging-status.items'; target.parent.mkdir()
    root = tmp_path/'private'; root.mkdir(mode=0o700)
    monkeypatch.setattr(m, 'TARGET', target); monkeypatch.setattr(m, 'SOURCE', source)
    monkeypatch.setattr(m, 'BACKUP_ROOT', root)
    def readonly_get(path):
        assert path == '/links', 'unexpected network boundary in offline test'
        return []
    monkeypatch.setattr(m.oh, 'get', readonly_get)
    writer = {'uid': 'UpdateBatteryIcon', 'editable': False,
        'triggers': [{'type': 'timer.GenericCronTrigger',
                      'configuration': {'cronExpression': '0/30 * * * * ?'}}],
        'conditions': [], 'actions': [{'type': 'jsr223.ScriptedAction',
                                      'configuration': {'privId': 'i12'}}],
        'status': {'status': 'IDLE', 'statusDetail': 'NONE'}}
    state = {'managed': deepcopy(ORIGINAL), 'writer': writer,
             'writes': [], 'fault_write': None, 'fault_file': False,
             'persisted_state': 'OFF', 'natural_change_on_resume': False}
    def read_item():
        if state['managed'] is not None: return deepcopy(state['managed'])
        if target.exists():
            if state['fault_file']:
                state['fault_file'] = False
                raise RuntimeError('injected file readback failure')
            return {**deepcopy(ORIGINAL), 'editable': False,
                    'state':state['persisted_state']}
        return None
    def mutate(method, path, body=None):
        m.allowed_mutation(method, path, body)
        state['writes'].append((method, path, deepcopy(body)))
        if method in ('DELETE','PUT'):
            assert state['writer']['status']['statusDetail'] == 'DISABLED', 'provider changed with active writer'
        if method == 'DELETE': state['managed'] = None
        elif method == 'PUT':
            assert not target.exists(), 'managed/file duplicate created'
            state['managed'] = {**deepcopy(body), 'editable': True,
                                'state':state['persisted_state']}
        elif method == 'POST':
            state['writer']['status'] = ({'status': 'IDLE', 'statusDetail': 'NONE'} if body
                else {'status': 'UNINITIALIZED', 'statusDetail': 'DISABLED'})
            if body and state['natural_change_on_resume']:
                state['persisted_state'] = 'ON'
        if len(state['writes']) == state['fault_write']:
            raise RuntimeError('injected accepted-write timeout')
    monkeypatch.setattr(m, 'item', read_item, raising=False)
    monkeypatch.setattr(m, 'request', mutate)
    monkeypatch.setattr(m, 'writer', lambda *, disabled: (
        m.validate_writer(state['writer'], disabled=disabled), deepcopy(state['writer']))[1], raising=False)
    monkeypatch.setattr(m, 'protected_signature', lambda: {'pid': '1696', 'definitions': 'fixed'}, raising=False)
    baseline = {'id':154, 'count':2, 'cutoff':'2026-10-05T18:00:00+00:00',
                'sha256':'fixed', 'bytes':10, 'last_state':'OFF'}
    def history(_db, cutoff=None, output=None):
        if cutoff is None and state['persisted_state']=='ON':
            return {**deepcopy(baseline),'last_state':'ON','count':3,
                    'cutoff':'2026-10-05T18:01:00+00:00','sha256':'later'}
        return deepcopy(baseline)
    monkeypatch.setattr(m, 'history', history, raising=False)
    def backup_history(_db, directory, name, before):
        m.b.private_file(directory, name, b'original rows')
    monkeypatch.setattr(m, 'backup_history', backup_history, raising=False)
    return state, target


def test_real_file_roundtrip_has_one_provider_and_restores_writer(handoff_environment):
    state, target = handoff_environment
    ops = m.Operations(object())
    ops.run()
    assert target.exists() and state['managed'] is None
    assert state['writer']['status'] == {'status':'IDLE','statusDetail':'NONE'}
    assert state['writes'] == [
        ('POST','/rules/UpdateBatteryIcon/enable',False),
        ('DELETE','/items/BatteryChargingStatus',None),
        ('PUT','/items/BatteryChargingStatus',m.ORIGINAL_DTO),
        ('DELETE','/items/BatteryChargingStatus',None),
        ('POST','/rules/UpdateBatteryIcon/enable',True)]
    assert (ops.directory/'withdrawal-1.items').exists()


@pytest.mark.parametrize('fault_write', [1,2,3,4,5])
def test_accepted_write_timeout_recovers_original_without_duplicate_provider(
        handoff_environment, fault_write):
    state, target = handoff_environment
    state['fault_write'] = fault_write
    ops = m.Operations(object())
    with pytest.raises(RuntimeError, match='injected accepted-write timeout'): ops.run()
    assert not target.exists()
    assert state['managed'] == ORIGINAL
    assert state['writer']['status'] == {'status':'IDLE','statusDetail':'NONE'}


def test_failed_file_readback_withdraws_owned_file_before_original_restore(handoff_environment):
    state, target = handoff_environment
    state['fault_file'] = True
    ops = m.Operations(object())
    with pytest.raises(RuntimeError, match='injected file readback failure'): ops.run()
    assert not target.exists() and state['managed'] == ORIGINAL
    assert (ops.directory/'withdrawal-1.items').exists()
    assert state['writer']['status'] == {'status':'IDLE','statusDetail':'NONE'}


def test_install_never_adopts_replaced_watched_file_even_with_matching_bytes(
        handoff_environment, monkeypatch):
    state, target = handoff_environment
    ops = m.Operations(object())
    state['managed'] = None
    original_link = m.os.link
    def replace_after_link(source, destination, **kwargs):
        original_link(source, destination, **kwargs)
        if Path(destination) == target:
            target.unlink()
            target.write_bytes(Path(source).read_bytes())
    monkeypatch.setattr(m.os, 'link', replace_after_link)
    with pytest.raises(RuntimeError, match='ownership'):
        ops.install_file()
    assert target.exists()
    assert ops.owned_identity != (target.stat().st_dev,target.stat().st_ino)


def test_writer_wait_tolerates_transient_status_only(handoff_environment, monkeypatch):
    ops = m.Operations(object())
    pending = [True]
    def transition(*, disabled):
        if pending[0]:
            pending[0] = False
            raise RuntimeError('writer status drift')
        return {'status':{'status':'UNINITIALIZED','statusDetail':'DISABLED'}}
    monkeypatch.setattr(m, 'writer', transition)
    monkeypatch.setattr(m.time, 'sleep', lambda _seconds: None)
    m.wait_for(ops.paused_writer)
    monkeypatch.setattr(m,'writer',lambda **_k: (_ for _ in ()).throw(RuntimeError('writer ownership drift')))
    with pytest.raises(RuntimeError,match='ownership'):
        ops.paused_writer()


def test_late_failure_retains_genuine_appended_state_during_managed_recovery(handoff_environment):
    state,target = handoff_environment
    state['fault_write'] = 5
    state['natural_change_on_resume'] = True
    ops = m.Operations(object())
    with pytest.raises(RuntimeError,match='injected accepted-write timeout'):
        ops.run()
    assert not target.exists()
    assert state['managed'] == {**ORIGINAL,'state':'ON'}
    assert state['writer']['status'] == {'status':'IDLE','statusDetail':'NONE'}
    assert ops.before['last_state'] == 'OFF'  # The original prefix is never rebased.


@pytest.mark.parametrize('unrestored',['NULL','UNDEF'])
def test_unrestored_owned_file_recovers_original_provider(handoff_environment,monkeypatch,unrestored):
    state,target=handoff_environment
    ops=m.Operations(object());ops.backup();ops.withdraw_managed();ops.install_file()
    read=m.item
    def unrestored_item():
        current=read()
        if current is not None and current['editable'] is False:
            current['state']=unrestored
        return current
    monkeypatch.setattr(m,'item',unrestored_item)
    ops.recover_managed();ops.resume_writer()
    assert not target.exists() and state['managed']==ORIGINAL
    assert state['writer']['status']=={'status':'IDLE','statusDetail':'NONE'}
    assert ops.before['last_state']=='OFF'

def test_recovery_waits_for_genuine_later_jdbc_state(handoff_environment,monkeypatch):
    state,target=handoff_environment
    ops=m.Operations(object());ops.backup();ops.withdraw_managed();ops.install_file()
    state['persisted_state']='ON'
    original_history=m.history;reads=[]
    def delayed_history(db,cutoff=None,output=None):
        if cutoff is None:
            reads.append(1)
            if len(reads)==1:return {**ops.before}
        return original_history(db,cutoff,output)
    monkeypatch.setattr(m,'history',delayed_history)
    monkeypatch.setattr(m.time,'sleep',lambda seconds:None)
    ops.recover_managed();ops.resume_writer()
    assert len(reads)>=2
    assert not target.exists() and state['managed']=={**ORIGINAL,'state':'ON'}
    assert ops.before['last_state']=='OFF'

def test_partial_pending_write_cleans_owned_inode_and_preserves_error(handoff_environment,monkeypatch):
    state,target=handoff_environment
    ops=m.Operations(object());state['managed']=None
    original_fdopen=m.os.fdopen
    class PartialWrite:
        def __init__(self,stream):self.stream=stream
        def __enter__(self):self.stream.__enter__();return self
        def __exit__(self,*args):return self.stream.__exit__(*args)
        def write(self,data):
            self.stream.write(data[:8]);self.stream.flush()
            raise OSError('injected partial write failure')
    monkeypatch.setattr(m.os,'fdopen',lambda *args,**kwargs:PartialWrite(original_fdopen(*args,**kwargs)))
    with pytest.raises(OSError,match='injected partial write failure'):
        ops.install_file()
    assert not target.exists() and not list(target.parent.glob('.charging-*.pending'))


def test_unrestored_provider_with_changed_original_history_refuses_withdrawal(
        handoff_environment,monkeypatch):
    state,target=handoff_environment
    ops=m.Operations(object());ops.backup();ops.withdraw_managed();ops.install_file()
    read=m.item
    def unrestored_item():
        current=read()
        if current is not None and current['editable'] is False:
            current['state']='NULL'
        return current
    original_history=m.history
    def changed_history(db,cutoff=None,output=None):
        receipt=original_history(db,cutoff,output)
        return {**receipt,'sha256':'changed'} if cutoff is not None else receipt
    monkeypatch.setattr(m,'item',unrestored_item)
    monkeypatch.setattr(m,'history',changed_history)
    with pytest.raises(RuntimeError,match='history prefix changed'):
        ops.recover_managed()
    assert target.exists() and state['managed'] is None
    assert state['writer']['status']['statusDetail']=='DISABLED'


@pytest.mark.parametrize('failure', ['directory-sync', 'withdrawal-readback'])
@pytest.mark.parametrize('cached_reads', [0, 1, 3])
def test_recovery_waits_for_removed_owned_file_provider_before_managed_restore(
        handoff_environment, monkeypatch, failure, cached_reads):
    state, target = handoff_environment
    ops = m.Operations(object())
    ops.backup(); ops.withdraw_managed(); ops.install_file(); ops.verify_file()
    cached = {**ORIGINAL, 'editable': False}
    real_read = m.item
    pending_reads = [cached_reads]
    failed = [False]
    def delayed_withdrawal():
        if state['managed'] is not None or target.exists():
            return real_read()
        if failure == 'withdrawal-readback' and not failed[0]:
            failed[0] = True
            raise OSError('injected post-unlink readback failure')
        if pending_reads[0]:
            pending_reads[0] -= 1
            return deepcopy(cached)
        return None
    real_sync = m.history_tools.sync_directory
    def failed_parent_sync(path):
        if failure == 'directory-sync' and path == target.parent and not target.exists() and not failed[0]:
            failed[0] = True
            raise OSError('injected post-unlink directory sync failure')
        real_sync(path)
    def bounded_wait(predicate, seconds=90):
        for _ in range(10):
            if predicate(): return
        raise RuntimeError('provider or writer recovery timeout')
    monkeypatch.setattr(m, 'item', delayed_withdrawal)
    monkeypatch.setattr(m.history_tools, 'sync_directory', failed_parent_sync)
    monkeypatch.setattr(m, 'wait_for', bounded_wait)
    with pytest.raises(OSError, match='injected post-unlink'):
        ops.withdraw_file()
    assert not target.exists()
    ops.recover_managed(); ops.resume_writer()
    assert state['managed'] == ORIGINAL
    assert state['writer']['status'] == {'status': 'IDLE', 'statusDetail': 'NONE'}
    assert (ops.directory/'withdrawal-1.items').read_bytes() == m.SOURCE.read_bytes()
