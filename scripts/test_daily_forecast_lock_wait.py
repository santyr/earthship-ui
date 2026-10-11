"""Actual flock behavior from the policy, using private counter-only fixtures."""
import configparser
from pathlib import Path
import shlex,subprocess,sys
import pytest

DROP=Path(__file__).resolve().parents[1]/'openhab/systemd/user/forecast-intel.service.d/zzzz-daily-lock-wait.conf'


def command(tmp_path):
    assert DROP.exists(),'daily forecast bounded wait policy missing'
    policy=configparser.ConfigParser(strict=False);policy.read(DROP)
    argv=shlex.split(policy['Service']['ExecStart'])
    lock='/home/sat/.local/state/thermal-intel/native-input-consumers.lock'
    assert argv[0]=='/usr/bin/flock' and argv.count(lock)==1
    options=argv[1:argv.index(lock)]
    assert '--wait' in options and 0<float(options[options.index('--wait')+1])<=90
    # Scale only the wait duration; the lock/exit/exclusive behavior is real.
    options[options.index('--wait')+1]='0.4'
    worker=tmp_path/'worker.py';worker.write_text('from pathlib import Path\nimport sys\np=Path(sys.argv[1]);p.write_text(p.read_text()+"run\\n" if p.exists() else "run\\n")\n')
    return policy,['/usr/bin/flock',*options,str(tmp_path/'fixture.lock'),sys.executable,str(worker),str(tmp_path/'runs')]


def holder(tmp_path,seconds):
    path=tmp_path/'holder.py';path.write_text('import fcntl,sys,time\nf=open(sys.argv[1],"a");fcntl.flock(f,fcntl.LOCK_EX);print("held",flush=True);time.sleep(float(sys.argv[2]))\n')
    process=subprocess.Popen([sys.executable,str(path),str(tmp_path/'fixture.lock'),str(seconds)],stdout=subprocess.PIPE,text=True)
    assert process.stdout.readline()=='held\n'
    return process


def test_daily_job_waits_for_original_lock_and_executes_once(tmp_path):
    _,argv=command(tmp_path);locked=holder(tmp_path,.2)
    try:
        result=subprocess.run(argv,capture_output=True,text=True,timeout=3)
        assert result.returncode==0 and (tmp_path/'runs').read_text()=='run\n'
    finally:locked.wait(timeout=3)


def test_exhausted_wait_cannot_execute_worker_or_report_success(tmp_path):
    policy,argv=command(tmp_path);locked=holder(tmp_path,.9)
    try:
        result=subprocess.run(argv,capture_output=True,text=True,timeout=3)
        assert result.returncode==75 and not (tmp_path/'runs').exists()
        assert policy['Service'].get('SuccessExitStatus')=='', 'exhaustion must remain a service failure'
    finally:locked.wait(timeout=3)


def test_uncontended_wait_executes_only_one_worker(tmp_path):
    _,argv=command(tmp_path)
    result=subprocess.run(argv,capture_output=True,text=True,timeout=3)
    assert result.returncode==0 and (tmp_path/'runs').read_text()=='run\n'
