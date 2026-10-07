"""Real file-engine transactions, with no production units or forecast calls."""
from hashlib import sha256
import importlib.util
from pathlib import Path

import pytest

SPEC=importlib.util.spec_from_file_location('forecast_files',Path(__file__).with_name('forecast-recovery-files.py'))
f=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(f)


def setup(tmp_path,monkeypatch):
    live=tmp_path/'live';live.mkdir()
    original=live/'forecast_intel.py';original.write_bytes(b'# original fixture');original.chmod(0o640)
    units=tmp_path/'units';units.mkdir()
    baseline={}
    for path in (f.BASE,f.UNITS/'forecast-intel.timer',f.UNITS/'forecast-json.service',f.UNITS/'forecast-json.timer',*f.DROPINS):
        target=units/path.relative_to(f.UNITS);target.parent.mkdir(exist_ok=True,parents=True)
        target.write_bytes(b'[Service]\n# original fixture unit\n');baseline[target]=target.read_bytes()
    drops=tuple(units/path.relative_to(f.UNITS) for path in f.DROPINS)
    monkeypatch.setattr(f,'LIVE',live);monkeypatch.setattr(f,'UNITS',units)
    monkeypatch.setattr(f,'BASE',units/'forecast-intel.service');monkeypatch.setattr(f,'DROPINS',drops)
    receipts=tmp_path/'receipts';receipts.mkdir(mode=0o700)
    monkeypatch.setattr(f,'RECEIPTS',receipts)
    monkeypatch.setattr(f,'OLD',sha256(original.read_bytes()).hexdigest())
    # This transaction fixture selects the current source. Production pins still
    # bind the separately qualified historical release and must not be repinned.
    monkeypatch.setattr(f, 'CANDIDATES', {
        source: sha256((f.ROOT/source).read_bytes()).hexdigest()
        for source in f.CANDIDATES
    })
    monkeypatch.setattr(f,'idle_window',lambda:None)
    calls=[]
    monkeypatch.setattr(f,'verify_effective',lambda installed:calls.append(('verify',installed)))
    monkeypatch.setattr(f,'systemctl',lambda *args:calls.append(args) or '')
    monkeypatch.setattr(f.subprocess,'run',lambda *a,**k:None)
    receipt=receipts/'fetch-20261003T091000Z-01234567'
    return receipt,original,baseline,calls


def test_prepare_rehearse_install_restore_preserves_all_originals(tmp_path,monkeypatch):
    receipt,original,baseline,calls=setup(tmp_path,monkeypatch)
    assert f.prepare(receipt)=={'status':'prepared','production_writes':0}
    assert f.rehearse(receipt)['temporary_storage_removed']
    assert f.apply(receipt)=={'status':'installed_disabled','jobs_started':False,'recovery_enabled':False}
    for record in f.manifest():assert Path(record['target']).read_bytes()==(f.ROOT/record['source']).read_bytes()
    assert f.restore(receipt)['status']=='rolled_back'
    assert original.read_bytes()==b'# original fixture' and original.stat().st_mode & 0o777==0o640
    assert all(path.read_bytes()==raw for path,raw in baseline.items())
    assert all(not Path(record['target']).exists() for record in f.manifest() if not record['source'].endswith('/forecast_intel.py'))
    assert f.rehearse(receipt)['status']=='rehearsal_passed'
    assert f.apply(receipt)['status']=='installed_disabled'
    assert all(call[0] not in {'start','stop','restart','enable'} for call in calls)


@pytest.mark.parametrize('fault',['unrehearsed','policy','frozen_source','backup','archive','permissions','new_target','busy'])
def test_apply_refuses_without_changing_owned_originals(tmp_path,monkeypatch,fault):
    receipt,original,baseline,calls=setup(tmp_path,monkeypatch)
    f.prepare(receipt)
    if fault!='unrehearsed':f.rehearse(receipt)
    calls.clear()
    if fault=='policy':f.DROPINS[0].write_bytes(b'operator change')
    elif fault=='frozen_source':(receipt/'source/openhab/scripts/forecast_fetch_recovery.py').write_bytes(b'bad')
    elif fault=='backup':next((receipt/'files/backups').glob('*.bin')).write_bytes(b'bad')
    elif fault=='archive':next((receipt/'original-policies').iterdir()).write_bytes(b'bad')
    elif fault=='permissions':receipt.chmod(0o755)
    elif fault=='new_target':(f.LIVE/'forecast_fetch_recovery.py').write_bytes(b'operator code')
    elif fault=='busy':monkeypatch.setattr(f,'idle_window',lambda:(_ for _ in ()).throw(ValueError('busy')))
    with pytest.raises((ValueError,RuntimeError)):f.apply(receipt)
    assert original.read_bytes()==b'# original fixture'
    assert not any(call[0]=='daemon-reload' for call in calls)
    if fault=='permissions':assert receipt.stat().st_mode & 0o777==0o755
    if fault=='new_target':assert (f.LIVE/'forecast_fetch_recovery.py').read_bytes()==b'operator code'


@pytest.mark.parametrize('phase',['code','unit'])
def test_interrupted_replace_recovers_to_original_not_reapplies(tmp_path,monkeypatch,phase):
    receipt,original,_,_=setup(tmp_path,monkeypatch)
    f.prepare(receipt);f.rehearse(receipt)
    class Crash(BaseException):pass
    def crash(event,index):
        if event=='after-replace':raise Crash()
    with pytest.raises(Crash):
        f.files.install_phase(receipt/'source',receipt/'files',phase,manifest=f.manifest(),fault=crash)
    assert f.restore(receipt,recover=True)['status']=='rolled_back'
    assert original.read_bytes()==b'# original fixture'


def test_failed_effective_readback_restores_without_starting_any_job(tmp_path,monkeypatch):
    receipt,original,_,calls=setup(tmp_path,monkeypatch)
    f.prepare(receipt);f.rehearse(receipt)
    def verify(installed):
        if installed:raise ValueError('readback mismatch')
    monkeypatch.setattr(f,'verify_effective',verify)
    with pytest.raises(ValueError):f.apply(receipt)
    assert original.read_bytes()==b'# original fixture' and f.state(receipt)['status']=='rolled_back'
    assert calls.count(('daemon-reload',))==2


def test_explicit_write_gate_refuses_before_receipt_access(monkeypatch,tmp_path):
    monkeypatch.setattr(f,'state',lambda *_:pytest.fail('receipt access'))
    assert f.main(['apply','--receipt',str(tmp_path/'anything')])==1


@pytest.mark.parametrize('fault',[None,'command','policy','failure_target','helper_override'])
def test_effective_systemd_paths_and_command_checked_exactly(monkeypatch,fault):
    installed=True
    def show(*args):
        assert args[0]=='show'
        _,unit,_,field,_=args
        if field=='FragmentPath':return str(f.UNITS/unit)
        if field=='DropInPaths':
            if unit==f.BASE.name:
                result=sorted((*f.DROPINS,Path(str(f.BASE)+'.d/fetch-recovery.conf')))
                return ' '.join(map(str,result)) if fault!='policy' else '/unreviewed.conf'
            return '/unreviewed.conf' if fault=='helper_override' else ''
        if field=='ExecStart':return '{ argv[]=/usr/bin/python3 '+(
            '/wrong.py' if fault=='command' else str(f.LIVE/'forecast_intel.py'))+' ; ignore_errors=no ; }'
        if field=='OnFailure':return 'other.timer' if fault=='failure_target' else 'forecast-intel-fetch-recovery.timer'
        if field=='ActiveState':return 'inactive'
        pytest.fail('unreviewed property')
    monkeypatch.setattr(f,'systemctl',show)
    if fault:
        with pytest.raises(ValueError):f.verify_effective(installed)
    else:f.verify_effective(installed)
