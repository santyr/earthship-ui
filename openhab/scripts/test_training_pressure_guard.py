"""Training-only pressure supervision; no household sources or release authority."""
from pathlib import Path
import sys
import pytest


def source():
    from thermal_model import training_pressure_guard
    return training_pressure_guard


def state(tmp_path,*,available=1980000,swapin=0,pressure='0.00',total=0):
    mem=tmp_path/'mem';vm=tmp_path/'vm';psi=tmp_path/'psi'
    mem.write_text(f'MemAvailable: {available} kB\nSwapTotal: 4194304 kB\nSwapFree: 0 kB\n')
    vm.write_text(f'pswpin {swapin}\npswpout 0\noom_kill 0\n')
    psi.write_text(''.join(f'{name} avg10={pressure} avg60=0.00 avg300=0.00 total={total}\n' for name in ('some','full')))
    return mem,vm,psi


def monitor(tmp_path,**kwargs):
    mem,vm,psi=state(tmp_path,**kwargs)
    return source().TrainingHeadroom(meminfo=mem,vmstat=vm,pressure=psi)


def test_occupied_swap_without_activity_permits_capped_training(tmp_path):
    guard=monitor(tmp_path)
    guard.check();guard.check()


@pytest.mark.parametrize('damage',['low_ram','swapin','pressure','oom','counter_reset','nan','missing_psi'])
def test_deterioration_or_invalid_telemetry_refuses(tmp_path,damage):
    guard=monitor(tmp_path,swapin=2);guard.check()
    if damage=='low_ram':state(tmp_path,available=1500000,swapin=2)
    if damage=='swapin':state(tmp_path,swapin=3)
    if damage=='pressure':state(tmp_path,pressure='1.00',swapin=2)
    if damage=='oom':(tmp_path/'vm').write_text('pswpin 2\npswpout 0\noom_kill 1\n')
    if damage=='counter_reset':state(tmp_path,swapin=1)
    if damage=='nan':state(tmp_path,pressure='nan',swapin=2)
    if damage=='missing_psi':(tmp_path/'psi').write_text('')
    with pytest.raises(ValueError):guard.check()


def test_interval_pressure_catches_activity_hidden_by_averages(tmp_path):
    guard=monitor(tmp_path);guard.check()
    state(tmp_path,total=1000000)
    with pytest.raises(ValueError):guard.check()


def test_supervisor_kills_worker_when_pressure_changes(tmp_path):
    guard=monitor(tmp_path);marker=tmp_path/'started'
    code="from pathlib import Path; import time; Path(%r).write_text('started'); time.sleep(20)" % str(marker)
    calls=[0]
    def check():
        guard.check()
        if marker.exists():raise ValueError('pressure changed')
        calls[0]+=1
    with pytest.raises(ValueError):source().run_training_worker([sys.executable,'-c',code],check=check,seconds=3)
    assert marker.exists()


def test_supervisor_propagates_success_and_exit_failure():
    for status in (0,7):
        assert source().run_training_worker([sys.executable,'-c',f'raise SystemExit({status})'],check=lambda:None,seconds=3)[0]==status


def test_supervisor_enforces_deadline():
    with pytest.raises(ValueError,match='deadline'):
        source().run_training_worker([sys.executable,'-c','import time; time.sleep(20)'],check=lambda:None,seconds=1)


def test_preflight_observes_activity_before_numerical_worker(tmp_path,monkeypatch):
    guard=monitor(tmp_path)
    monkeypatch.setattr(source(),'sleep',lambda _:state(tmp_path,swapin=1))
    with pytest.raises(ValueError):guard.preflight()


def test_cli_fit_uses_supervisor_before_reading_config(tmp_path,monkeypatch,capsys):
    import thermal_installed_train as cli
    monkeypatch.setattr(cli,'_resource_preflight',lambda:None)
    monkeypatch.setattr(source().TrainingHeadroom,'preflight',lambda self:None)
    calls=[]
    def supervised(argv,**kwargs):
        calls.append((argv,kwargs))
        return 1,b'{"status":"withheld","fit_executed":false,"release_authorized":false}'
    monkeypatch.setattr(source(),'run_training_worker',supervised)
    assert cli.main(['--config',str(tmp_path/'missing'),'--fit'])==1
    assert len(calls)==1
    assert calls[0][1]['env']['PYTHONPATH']==str(Path(cli.__file__).resolve().parent)
    assert 'withheld' in capsys.readouterr().out


def test_supervisor_cleans_up_inherited_descendant(tmp_path):
    from time import monotonic,sleep
    marker=tmp_path/'child'
    code="import os,time; from pathlib import Path; child=os.fork(); Path(%r).write_text(str(child)) if child else time.sleep(20)" % str(marker)
    assert source().run_training_worker([sys.executable,'-c',code],check=lambda:None,seconds=3)[0]==0
    child=int(marker.read_text());deadline=monotonic()+1
    while True:
        try:state=Path(f'/proc/{child}/stat').read_text().rsplit(')',1)[1].split()[0]
        except (FileNotFoundError,ProcessLookupError):break
        if state=='Z':break
        assert monotonic()<deadline
        sleep(.01)


def test_supervisor_drains_bounded_result_with_small_pipe(monkeypatch):
    original=source().subprocess.Popen
    monkeypatch.setattr(source().subprocess,'Popen',lambda *args,**kwargs:original(*args,pipesize=4096,**kwargs))
    status,raw=source().run_training_worker([sys.executable,'-c',"import sys; sys.stdout.write('x'*12000)"],check=lambda:None,seconds=3)
    assert status==0 and raw==b'x'*12000


def test_supervisor_refuses_oversized_result():
    with pytest.raises(ValueError,match='bounded training result'):
        source().run_training_worker([sys.executable,'-c',"import sys; sys.stdout.write('x'*20000)"],check=lambda:None,seconds=3)
