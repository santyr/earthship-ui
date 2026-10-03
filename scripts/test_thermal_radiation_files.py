"""Actual file transactions in temporary targets; no household mutation."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('radiation_files',
    Path(__file__).with_name('thermal-radiation-files.py'))
r = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(r)


def setup(tmp_path, monkeypatch):
    root, live, state = tmp_path/'repo', tmp_path/'live', tmp_path/'state'
    unit = tmp_path/'units/shadow.service.d/qualified-radiation.conf'
    monkeypatch.setattr(r, 'ROOT', root); monkeypatch.setattr(r, 'LIVE', live)
    monkeypatch.setattr(r, 'STATE', state); monkeypatch.setattr(r, 'UNIT', unit)
    monkeypatch.setattr(r, 'RECEIPTS', state/'deploy-receipts')
    r.RECEIPTS.mkdir(parents=True, mode=0o700)
    config = tmp_path/'private.env'; config.write_bytes(b'PRIVATE-TEST-CONFIG'); config.chmod(0o600)
    monkeypatch.setattr(r, 'CONFIGS', (config,))
    paths = r.q.bundle.LEGACY_RUNTIME_PATHS
    baseline = {name: (f'RUNTIME_REVISION_PATHS = {paths!r}\n'.encode() if name=='thermal_intel.py'
                      else f'# original {name}\n'.encode()) for name in (*paths, r.q.CAPTURE_HELPER)}
    r.q._write_tree(live, baseline)
    (live/'thermal_intel.py').chmod(0o640)
    delta = {name: (f'RUNTIME_REVISION_PATHS = {r.q.bundle.RADIATION_RUNTIME_PATHS!r}\n'.encode()
                   if name=='thermal_intel.py' else f'# radiation {name}\n'.encode()) for name in r.CODE_ORDER}
    r.q._write_tree(root/'openhab/scripts', delta)
    r.q._write_tree(root, {r.UNIT_SOURCE:b'[Service]\n# isolated drop-in\n'})
    monkeypatch.setattr(r, 'OLD', r.q._revision(baseline, paths))
    monkeypatch.setattr(r, 'NEW', r.q._revision({**baseline, **delta}, r.q.bundle.RADIATION_RUNTIME_PATHS))
    monkeypatch.setattr(r, 'idle_window', lambda: None)
    monkeypatch.setattr(r.q, '_current_inputs', lambda path: dict(scope='test-only-receipts'))
    calls = []
    def systemctl(*args):
        calls.append(args)
        if args==('daemon-reload',): return ''
        assert args==('show','-p','Environment','--value','thermal-model-shadow.service')
        return ' '.join(f'{key}={value}' for key,value in r.RAD_ENV.items())
    monkeypatch.setattr(r, 'systemctl', systemctl)
    receipt = r.RECEIPTS/'radiation-current-20261003T013000Z-01234567'
    return receipt, baseline, calls


def assert_original(baseline):
    for name, data in baseline.items(): assert (r.LIVE/name).read_bytes()==data
    assert (r.LIVE/'thermal_intel.py').stat().st_mode & 0o777 == 0o640
    assert not any((r.LIVE/name).exists() for name in r.CODE_ORDER[:-1])
    assert not r.UNIT.exists()


def test_prepare_is_private_and_apply_restore_preserve_original_runtime(tmp_path, monkeypatch):
    receipt, baseline, calls = setup(tmp_path, monkeypatch)
    result = r.prepare(receipt)
    assert result['production_writes']==0 and result['status']=='prepared'
    assert_original(baseline); assert calls==[]
    assert receipt.stat().st_mode & 0o777 == 0o700
    assert (receipt/'configuration/00.bin').read_bytes()==b'PRIVATE-TEST-CONFIG'
    assert (receipt/'configuration/00.bin').stat().st_mode & 0o777 == 0o600
    assert [entry['source'].removeprefix('openhab/scripts/') for entry in r.manifest()
            if entry['phase']=='code']==list(r.CODE_ORDER)
    assert r.CODE_ORDER[-1]=='thermal_intel.py'
    result=r.apply(receipt)
    assert result['status']=='installed_waiting_natural_publication'
    assert not result['controls_enabled'] and not result['learning_enabled']
    assert r._revision(r.LIVE)==r.NEW and r.UNIT.exists()
    assert (r.LIVE/'thermal_intel.py').stat().st_mode & 0o777 == 0o755
    assert r.restore(receipt)['restored_revision']==r.OLD
    assert_original(baseline)
    assert all(call[0] not in {'start','restart','stop'} for call in calls)


@pytest.mark.parametrize('change', ['config','accepted_source','unit','candidate','active_job'])
def test_prepare_refuses_before_recovery_allocation(tmp_path, monkeypatch, change):
    receipt, _, _=setup(tmp_path, monkeypatch)
    if change=='config': r.CONFIGS[0].unlink()
    elif change=='accepted_source': (r.LIVE/'thermal_model/artifacts.py').write_bytes(b'changed')
    elif change=='unit': r.UNIT.parent.mkdir(parents=True); r.UNIT.write_bytes(b'preexisting')
    elif change=='candidate': (r.ROOT/'openhab/scripts/weather_radiation_reader.py').write_bytes(b'changed')
    else:
        def busy(): raise ValueError('active job')
        monkeypatch.setattr(r,'idle_window',busy)
    with pytest.raises((ValueError,OSError)): r.prepare(receipt)
    assert not receipt.exists()


@pytest.mark.parametrize('change', ['config','source','receipt_status','live','no_current_receipt'])
def test_apply_preflight_refuses_without_modifying_production(tmp_path, monkeypatch, change):
    receipt, baseline, calls=setup(tmp_path,monkeypatch); r.prepare(receipt)
    if change=='config': r.CONFIGS[0].write_bytes(b'NEW-PRIVATE-TEST-CONFIG')
    elif change=='source': (receipt/'source/openhab/scripts/weather_radiation_reader.py').write_bytes(b'changed')
    elif change=='receipt_status':
        data=json.loads((receipt/'qualification.json').read_text()); data['status']='rolled_back'; r._save_state(receipt,data)
    elif change=='live':
        (r.LIVE/'thermal_model/dynamics.py').write_bytes(b'concurrent installed edit')
        baseline['thermal_model/dynamics.py']=b'concurrent installed edit'
    else:
        def unavailable(path): raise ValueError('native receipt unavailable')
        monkeypatch.setattr(r.q,'_current_inputs',unavailable)
    with pytest.raises(ValueError): r.apply(receipt)
    assert_original(baseline); assert calls==[]


@pytest.mark.parametrize('phase', ['code','unit','readback'])
def test_apply_failure_restores_all_new_files_and_original_entrypoint(tmp_path,monkeypatch,phase):
    receipt, baseline, calls=setup(tmp_path,monkeypatch); r.prepare(receipt)
    real=r.q.files.install_phase
    def install(*args,**kwargs):
        if args[2]==phase:
            def fail(event,index):
                if event=='before-parent-fsync' and index==0:
                    raise RuntimeError('isolated rollout failure')
            kwargs['fault']=fail
        return real(*args,**kwargs)
    monkeypatch.setattr(r.q.files,'install_phase',install)
    if phase=='readback':
        monkeypatch.setattr(r,'systemctl',lambda *args: '' if args==('daemon-reload',) else 'wrong=value')
    with pytest.raises((RuntimeError,ValueError)): r.apply(receipt)
    assert_original(baseline)
    assert json.loads((receipt/'qualification.json').read_text())['status']=='rolled_back'


def test_interrupted_dependency_install_requires_guarded_recovery(tmp_path,monkeypatch):
    receipt,baseline,_=setup(tmp_path,monkeypatch); r.prepare(receipt)
    class Crash(BaseException): pass
    def crash(event,index):
        if event=='after-replace' and index==1: raise Crash()
    with pytest.raises(Crash):
        r.q.files.install_phase(receipt/'source',receipt/'files','code',manifest=r.manifest(),fault=crash)
    assert r.recover(receipt)['restored_revision']==r.OLD
    assert_original(baseline)


@pytest.mark.parametrize('value,expected', [('12h 10min 6.908902s',43806.908902),
    ('1d 2h 3min 4s',93784),('10ms 5us',.010005)])
def test_monotonic_deadline_parser(value,expected): assert r._seconds(value)==pytest.approx(expected)


@pytest.mark.parametrize('value',['','infinity','nan','1h PRIVATE','1.2.3s'])
def test_nonfinite_or_unknown_deadline_refuses(value):
    with pytest.raises(ValueError): r._seconds(value)


@pytest.mark.parametrize('busy',['job','timer','deadline'])
def test_actual_idle_window_refuses_busy_or_imminent_jobs(monkeypatch,busy):
    def systemctl(*args):
        if 'MainPID' in args:
            return 'MainPID=1\nActiveState=active' if busy=='job' else 'MainPID=0\nActiveState=inactive'
        if 'ActiveState' in args: return 'inactive' if busy=='timer' else 'active'
        return '110s' if busy=='deadline' else '300s'
    monkeypatch.setattr(r,'systemctl',systemctl); monkeypatch.setattr(r.time,'monotonic',lambda:100)
    with pytest.raises(ValueError): r.idle_window()


def test_cli_write_gate_cannot_activate_without_explicit_flag(tmp_path,monkeypatch,capsys):
    receipt, _, _=setup(tmp_path,monkeypatch)
    monkeypatch.setattr(r,'apply',lambda receipt:pytest.fail('write gate bypassed'))
    assert r.main(['apply','--receipt',str(receipt)])==1
    output=capsys.readouterr()
    assert output.out=='' and 'PRIVATE-TEST' not in output.err


def test_source_dropin_is_only_four_current_shadow_inputs():
    source=Path(__file__).resolve().parents[1]/r.UNIT_SOURCE
    values={line.removeprefix('Environment="').removesuffix('"').split('=',1)[0]:
            line.removeprefix('Environment="').removesuffix('"').split('=',1)[1]
            for line in source.read_text().splitlines() if line.startswith('Environment="')}
    assert values==r.RAD_ENV
    assert 'ExecStart' not in source.read_text() and 'TRAIN' not in values
