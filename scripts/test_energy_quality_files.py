"""Receipt-bound Energy unit transactions against owned temporary targets."""
from hashlib import sha256
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('energy_files',
    Path(__file__).with_name('energy-quality-files.py'))
e = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e)


def setup(tmp_path, monkeypatch):
    target = tmp_path/'units/energy-daily-aggregate.service.d/zz-qualified-switch.conf'
    target.parent.mkdir(parents=True)
    original = tmp_path/'units/energy-daily-aggregate.service'
    original.write_bytes(b'[Service]\nType=oneshot\n')
    private = tmp_path/'reader.jdbc'
    private.write_bytes(b'PRIVATE-TEST-CONNECTION'); private.chmod(0o600)
    candidate = tmp_path/'candidate.conf'
    # Transaction tests select an isolated unit, independent of host checkout.
    candidate.write_bytes(
        b'[Service]\nExecStart=\n'
        b'ExecStart=/usr/bin/flock --nonblock %t/fixture.lock /usr/bin/python3 '
        b'-m fixture.aggregate --switch-evidence-policy /fixture/switch.json '
        b'--switch-evidence-db-config /fixture/db.json '
        b'--bms-aux-evidence-policy /fixture/bms.json '
        b'--bms-aux-evidence-db-config /fixture/db.json\n')
    monkeypatch.setattr(e, 'CANDIDATE_SHA', sha256(candidate.read_bytes()).hexdigest())
    receipts = tmp_path/'receipts'; receipts.mkdir(mode=0o700)
    monkeypatch.setattr(e, 'UNIT', target)
    monkeypatch.setattr(e, 'BASE', original)
    baseline_dropins = tuple(target.parent/name for name in ('qualified-power.conf','qualified-temperature.conf'))
    for dropin in baseline_dropins: dropin.write_bytes(b'[Service]\n# isolated baseline\n')
    monkeypatch.setattr(e,'BASELINE_DROPINS',baseline_dropins)
    monkeypatch.setattr(e, 'CANDIDATE', candidate)
    monkeypatch.setattr(e, 'RECEIPTS', receipts)
    monkeypatch.setattr(e, 'input_paths', lambda: (original, private))
    monkeypatch.setattr(e, 'idle_window', lambda: None)
    calls = []
    monkeypatch.setattr(e, 'systemctl', lambda *args: calls.append(args) or '')
    monkeypatch.setattr(e, 'verify_effective', lambda installed: calls.append(('verify', installed)))
    monkeypatch.setattr(e, 'verify_unit', lambda path: calls.append(('parse', str(path))))
    monkeypatch.setattr(e, 'SUPPORTING_QUALITY_RELEASE_READY', True)
    receipt = receipts/'quality-20261003T042500Z-01234567'
    return receipt, private, calls


def test_prepare_rehearse_apply_restore_preserve_original(tmp_path, monkeypatch):
    receipt, private, calls = setup(tmp_path, monkeypatch)
    baseline = e.BASE.read_bytes()
    result = e.prepare(receipt)
    assert result['production_writes'] == 0 and not e.UNIT.exists()
    assert calls == [('verify',False)]
    assert receipt.stat().st_mode & 0o777 == 0o700
    assert (receipt/'qualification.json').stat().st_mode & 0o777 == 0o600
    assert any(p.read_bytes() == private.read_bytes() for p in (receipt/'originals').iterdir())
    assert e.rehearse(receipt)['status'] == 'rehearsal_passed'
    assert not e.UNIT.exists() and e.BASE.read_bytes() == baseline
    assert e.apply(receipt)['status'] == 'installed_waiting_natural_aggregate'
    assert e.UNIT.read_bytes() == e.CANDIDATE.read_bytes()
    assert e.UNIT.stat().st_mode & 0o777 == 0o644
    assert e.restore(receipt)['status'] == 'rolled_back'
    assert not e.UNIT.exists() and e.BASE.read_bytes() == baseline
    assert all(call[0] not in {'start','stop','restart','enable','disable'} for call in calls)


@pytest.mark.parametrize('change', ['config', 'candidate', 'new_target', 'busy'])
def test_prepare_refuses_before_private_allocation(tmp_path, monkeypatch, change):
    receipt, private, _ = setup(tmp_path, monkeypatch)
    if change == 'config': private.unlink()
    if change == 'candidate': e.CANDIDATE.write_bytes(b'wrong unit command')
    if change == 'new_target': e.UNIT.write_bytes(b'unowned')
    if change == 'busy':
        monkeypatch.setattr(e, 'idle_window', lambda: (_ for _ in ()).throw(ValueError('busy')))
    with pytest.raises((ValueError, OSError, RuntimeError)): e.prepare(receipt)
    assert not receipt.exists()


@pytest.mark.parametrize('change', ['config', 'source', 'missing_input', 'no_rehearsal', 'gate', 'target', 'backup', 'receipt_mode', 'file_manifest'])
def test_apply_refuses_drift_or_missing_gates_without_writes(tmp_path, monkeypatch, change):
    receipt, private, calls = setup(tmp_path, monkeypatch)
    e.prepare(receipt)
    if change != 'no_rehearsal': e.rehearse(receipt)
    calls.clear()
    if change == 'config': private.write_bytes(b'changed private configuration')
    if change == 'source': (receipt/'source/candidate/zz-qualified-switch.conf').write_bytes(b'changed')
    if change == 'missing_input': private.unlink()
    if change == 'gate': monkeypatch.setattr(e,'SUPPORTING_QUALITY_RELEASE_READY',False)
    if change == 'target': e.UNIT.write_bytes(b'concurrent owner')
    if change == 'backup': next((receipt/'originals').iterdir()).write_bytes(b'corrupt backup')
    if change == 'receipt_mode': receipt.chmod(0o755)
    if change == 'file_manifest': (receipt/'files/file-manifest.json').write_bytes(b'corrupt manifest')
    with pytest.raises((ValueError, OSError, RuntimeError)): e.apply(receipt)
    if change == 'target': assert e.UNIT.read_bytes() == b'concurrent owner'
    else: assert not e.UNIT.exists()
    assert not any(call[0]=='daemon-reload' for call in calls)


def test_readback_failure_rolls_back_only_owned_dropin(tmp_path, monkeypatch):
    receipt, _, calls = setup(tmp_path, monkeypatch)
    e.prepare(receipt); e.rehearse(receipt)
    def verify(installed):
        calls.append(('verify',installed))
        if installed: raise ValueError('wrong effective argv')
    monkeypatch.setattr(e,'verify_effective',verify)
    with pytest.raises(ValueError): e.apply(receipt)
    assert not e.UNIT.exists()
    assert e.state(receipt)['status'] == 'rolled_back'


def test_interrupted_unit_replace_is_recovered_not_reapplied(tmp_path, monkeypatch):
    receipt, _, _ = setup(tmp_path, monkeypatch)
    e.prepare(receipt); e.rehearse(receipt)
    class Crash(BaseException): pass
    def crash(event, index):
        if event == 'after-replace': raise Crash()
    with pytest.raises(Crash):
        e.files.install_phase(receipt/'source',receipt/'files','unit',manifest=e.manifest(),fault=crash)
    assert e.UNIT.exists()
    assert e.recover(receipt)['status'] == 'rolled_back'
    assert not e.UNIT.exists()


def test_unowned_later_unit_is_not_destroyed_on_restore(tmp_path, monkeypatch):
    receipt, _, _ = setup(tmp_path, monkeypatch)
    e.prepare(receipt); e.rehearse(receipt); e.apply(receipt)
    e.UNIT.write_bytes(b'operator changed this unit')
    with pytest.raises(RuntimeError): e.restore(receipt)
    assert e.UNIT.read_bytes() == b'operator changed this unit'


def test_closed_source_gate_cli_cannot_open_release(tmp_path, monkeypatch, capsys):
    receipt, _, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(e,'SUPPORTING_QUALITY_RELEASE_READY',False)
    assert e.main(['apply','--receipt',str(receipt),'--allow-apply']) == 1
    assert not e.UNIT.exists()
    assert 'PRIVATE-TEST' not in capsys.readouterr().err


def test_effective_argv_and_dropin_paths_are_exact(tmp_path, monkeypatch):
    real_verify = e.verify_effective
    receipt, _, _ = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(e,'verify_effective',real_verify)
    candidate = e.command(e.CANDIDATE.read_bytes())
    monkeypatch.setenv('XDG_RUNTIME_DIR','/run/user/1234')
    expected = ' '.join(candidate).replace('%t','/run/user/1234')
    responses = {'ExecStart': '{ path=/usr/bin/flock ; argv[]='+expected+' ; ignore_errors=no ; }',
        'Environment': 'PYTHONPATH='+e.PYTHONPATH,
        'FragmentPath': str(e.BASE),
        'DropInPaths': ' '.join(map(str,(*e.BASELINE_DROPINS,e.UNIT)))}
    monkeypatch.setattr(e,'systemctl',lambda *args: responses[args[2]])
    e.verify_effective(True)
    responses['ExecStart'] = responses['ExecStart'].replace('--bms-aux-evidence-policy','--wrong-policy')
    with pytest.raises(ValueError): e.verify_effective(True)


def test_receipt_root_and_symlink_rejected(tmp_path,monkeypatch):
    receipt, _, _ = setup(tmp_path,monkeypatch)
    with pytest.raises(ValueError): e.validate_receipt_path(tmp_path/'outside')
    receipt.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises((ValueError, RuntimeError)): e.prepare(receipt)


@pytest.mark.parametrize('busy',['job','timer','deadline'])
def test_idle_window_refuses_active_or_imminent_work(monkeypatch,busy):
    from types import SimpleNamespace
    def systemctl(*args):
        if 'MainPID' in args:
            return 'ActiveState=active\nMainPID=123' if busy=='job' else 'ActiveState=inactive\nMainPID=0'
        return 'inactive' if busy=='timer' else 'active'
    monkeypatch.setattr(e,'systemctl',systemctl)
    monkeypatch.setattr(e.time,'time',lambda:1791000000)
    deadline=(1791000000+(30 if busy=='deadline' else 300))*1000000
    monkeypatch.setattr(e.subprocess,'run',lambda *args,**kw:SimpleNamespace(stdout=f't {deadline}'))
    with pytest.raises(ValueError): e.idle_window()


def test_cli_requires_explicit_write_authority(tmp_path,monkeypatch,capsys):
    receipt, _, _=setup(tmp_path,monkeypatch)
    monkeypatch.setattr(e,'apply',lambda path:pytest.fail('write authority bypassed'))
    assert e.main(['apply','--receipt',str(receipt)])==1
    assert not e.UNIT.exists()
    assert 'PRIVATE-TEST' not in capsys.readouterr().err


def test_failed_parser_rehearsal_cannot_qualify_live_release(tmp_path,monkeypatch):
    receipt, _, _=setup(tmp_path,monkeypatch)
    e.prepare(receipt)
    monkeypatch.setattr(e,'verify_unit',lambda path:(_ for _ in ()).throw(ValueError('invalid unit')))
    with pytest.raises(ValueError): e.rehearse(receipt)
    assert e.state(receipt)['status']=='prepared'
    assert not e.UNIT.exists()


def test_transaction_fixture_does_not_read_host_companion_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(e, 'CANDIDATE', tmp_path/'absent-host-companion.conf')
    receipt, _, _ = setup(tmp_path, monkeypatch)
    assert e.prepare(receipt)['status'] == 'prepared'
