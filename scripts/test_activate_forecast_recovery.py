from hashlib import sha256
import importlib.util
from pathlib import Path

import pytest

SPEC=importlib.util.spec_from_file_location('activation',Path(__file__).with_name('activate-forecast-recovery.py'))
a=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(a)


def setup(tmp_path,monkeypatch):
    live=tmp_path/'live';live.mkdir()
    units=tmp_path/'units';units.mkdir()
    closed=b'# closed helper fixture\n'
    (live/'forecast_fetch_recovery.py').write_bytes(closed)
    (live/'forecast_fetch_recovery.py').chmod(0o644)
    (live/'forecast_intel.py').write_bytes((a.s.ROOT/'openhab/scripts/forecast_intel.py').read_bytes())
    for name in ('forecast-intel-fetch-recovery.service','forecast-intel-fetch-recovery.timer'):
        (units/name).write_bytes((a.s.ROOT/'deploy'/name).read_bytes())
    monkeypatch.setattr(a.s,'LIVE',live);monkeypatch.setattr(a.s,'UNITS',units)
    monkeypatch.setattr(a.s,'LEGACY_CANDIDATES',{**a.s.LEGACY_CANDIDATES,a.CODE:sha256(closed).hexdigest()})
    receipts=tmp_path/'receipts';receipts.mkdir(mode=0o700)
    monkeypatch.setattr(a.s,'RECEIPTS',receipts)
    policy={'baseline':{'sha256':'fixture','mode':0o644}}
    monkeypatch.setattr(a.s,'policies',lambda:policy)
    monkeypatch.setattr(a.s,'idle_window',lambda:None)
    calls=[]
    monkeypatch.setattr(a,'verify',lambda enabled:calls.append(('verify',enabled)))
    monkeypatch.setattr(a.s,'systemctl',lambda *args:calls.append(args) or '')
    return receipts/'fetch-20261003T091500Z-a1b2c3d4',closed,policy,calls


def test_activation_and_rollback_only_change_the_two_owned_files(tmp_path,monkeypatch):
    receipt,closed,_,calls=setup(tmp_path,monkeypatch)
    assert a.prepare(receipt)['production_writes']==0
    assert a.activate(receipt)=={'status':'enabled','jobs_started':False,'forecast_policy_changed':False}
    assert (a.s.LIVE/'forecast_fetch_recovery.py').read_bytes()==(a.s.ROOT/a.CODE).read_bytes()
    assert Path(a.manifest()[1]['target']).read_bytes()==(a.s.ROOT/a.DROP).read_bytes()
    assert a.restore(receipt)['status']=='rolled_back'
    assert (a.s.LIVE/'forecast_fetch_recovery.py').read_bytes()==closed
    assert not Path(a.manifest()[1]['target']).exists()
    assert all(call[0] not in {'start','stop','restart','enable'} for call in calls)


@pytest.mark.parametrize('fault',['policy','unit','forecast','frozen','backup','permissions','unowned_helper','unowned_dropin'])
def test_drift_refuses_activation_without_overwriting_originals(tmp_path,monkeypatch,fault):
    receipt,closed,policy,calls=setup(tmp_path,monkeypatch);a.prepare(receipt);calls.clear()
    if fault=='policy':policy['baseline']['sha256']='changed'
    elif fault=='unit':(a.s.UNITS/'forecast-intel-fetch-recovery.timer').write_bytes(b'changed')
    elif fault=='forecast':(a.s.LIVE/'forecast_intel.py').write_bytes(b'changed')
    elif fault=='frozen':(receipt/'source'/a.CODE).write_bytes(b'changed')
    elif fault=='backup':next((receipt/'files/backups').glob('*.bin')).write_bytes(b'changed')
    elif fault=='permissions':receipt.chmod(0o755)
    elif fault=='unowned_helper':(a.s.LIVE/'forecast_fetch_recovery.py').write_bytes(b'operator code')
    elif fault=='unowned_dropin':
        drop=Path(a.manifest()[1]['target']);drop.parent.mkdir();drop.write_bytes(b'operator unit')
    with pytest.raises((ValueError,RuntimeError)):a.activate(receipt)
    if fault!='unowned_helper':assert (a.s.LIVE/'forecast_fetch_recovery.py').read_bytes()==closed
    else:assert (a.s.LIVE/'forecast_fetch_recovery.py').read_bytes()==b'operator code'
    assert ('daemon-reload',) not in calls


def test_failed_effective_readback_restores_the_closed_gate(tmp_path,monkeypatch):
    receipt,closed,_,_=setup(tmp_path,monkeypatch);a.prepare(receipt)
    def verify(enabled):
        if enabled:raise ValueError('effective setting mismatch')
    monkeypatch.setattr(a,'verify',verify)
    with pytest.raises(ValueError):a.activate(receipt)
    assert (a.s.LIVE/'forecast_fetch_recovery.py').read_bytes()==closed
    assert not Path(a.manifest()[1]['target']).exists()
    assert a.state(receipt)['status']=='rolled_back'


@pytest.mark.parametrize('fault',[None,'environment','command'])
def test_exact_effective_opt_in_and_command(monkeypatch,fault):
    monkeypatch.setattr(a.s,'verify_effective',lambda *args,**kwargs:None)
    def show(*args):
        field=args[3]
        if field=='Environment':return 'OTHER=1' if fault=='environment' else a.FLAG
        if field=='ExecStart':return '{ argv[]=/usr/bin/python3 '+str(a.s.LIVE/'forecast_fetch_recovery.py')+(
            ' --other' if fault=='command' else ' --run')+' ; ignore_errors=no ; }'
        pytest.fail('unreviewed property')
    monkeypatch.setattr(a.s,'systemctl',show)
    if fault:
        with pytest.raises(ValueError):a.verify(True)
    else:a.verify(True)
