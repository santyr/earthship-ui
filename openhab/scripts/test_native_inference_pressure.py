"""Deterministic counter tests of the approved inference-only pressure policy."""
from pathlib import Path
import pytest
import native_inference_pressure as policy
from thermal_model.training_pressure_guard import TrainingHeadroom


@pytest.fixture
def rig(tmp_path,monkeypatch):
    clock=[10.0];monkeypatch.setattr(policy,'monotonic',lambda:clock[0])
    monkeypatch.setattr(policy.os,'sysconf',lambda key:4096)
    paths={key:tmp_path/key for key in ('meminfo','vmstat','pressure')}
    def sample(at,pages=0,*,out=0,oom=0,reserve=1572864,some=0,full=0,avg='0.00'):
        clock[0]=at
        paths['meminfo'].write_text(f'MemAvailable: {reserve} kB\nSwapTotal: 2048 kB\nSwapFree: 1024 kB\n')
        paths['vmstat'].write_text(f'pswpin {pages}\npswpout {out}\noom_kill {oom}\n')
        paths['pressure'].write_text(f'some avg10={avg} avg60=0.00 avg300=0.00 total={some}\nfull avg10=0.00 avg60=0.00 avg300=0.00 total={full}\n')
    worker=[]
    guard=policy.NativeInferenceHeadroom(**paths,worker_check=lambda:worker.append(1))
    sample(10);guard.check()
    return guard,sample,clock,paths,worker


def test_one_page_in_submillisecond_allowed_but_original_fitting_guard_refuses(rig,monkeypatch):
    guard,sample,clock,paths,worker=rig
    import thermal_model.training_pressure_guard as training
    monkeypatch.setattr(training,'monotonic',lambda:clock[0])
    fitting=TrainingHeadroom(**paths,max_swapin_bytes_per_second=1048576);fitting.check()
    sample(10.000719,1);guard.check()
    with pytest.raises(ValueError,match='swap-read'):fitting.check()
    assert len(worker)==2


def test_startup_total_and_repeated_bursts_do_not_renew_budget(rig):
    guard,sample,*_=rig
    sample(10.1,128);guard.check();sample(10.2,256);guard.check()
    sample(10.3,257)
    with pytest.raises(ValueError,match='trailing one-second'):guard.check()
    sample(12,257)
    with pytest.raises(ValueError,match='previously refused'):guard.check()


def test_retains_unmeasured_partial_interval_and_allows_observed_expiry(rig):
    guard,sample,*_=rig
    sample(10.5,128);guard.check();sample(11.2,256);guard.check()
    assert guard.samples[0][0]==10
    sample(11.3,257)
    with pytest.raises(ValueError,match='trailing one-second'):guard.check()


def test_window_expires_only_at_observed_sample(rig):
    guard,sample,*_=rig
    sample(10.5,256);guard.check();sample(11.5,256);guard.check()
    assert guard.samples[0][0]==10.5
    sample(11.6,512);guard.check()


@pytest.mark.parametrize('changes,match',[
    ({'out':4097},'swap-out'),({'oom':1},'OOM'),({'reserve':1572863},'reserve'),
    ({'some':50001},'trailing one-second memory pressure'),({'full':10001},'trailing one-second memory pressure'),
    ({'avg':'0.51'},'memory pressure'),({'pages':-1},'resource counters'),
])
def test_original_pressure_reserve_and_counter_checks_remain(rig,changes,match):
    guard,sample,*_=rig;sample(10.1,**changes)
    with pytest.raises(ValueError,match=match):guard.check()


def test_counter_regression_clock_and_worker_caps_refuse(rig):
    guard,sample,*_=rig
    sample(10.1,1);guard.check();sample(10.2,0)
    with pytest.raises(ValueError,match='regressed'):guard.check()


def test_worker_resource_failure_latches(rig):
    guard,sample,*_=rig
    def fail():raise ValueError('worker memory cap exceeded')
    guard.worker_check=fail;sample(10.1)
    with pytest.raises(ValueError,match='worker memory cap'):guard.check()
    guard.worker_check=lambda:None
    with pytest.raises(ValueError,match='previously refused'):guard.check()


def test_original_five_second_preflight_retained(rig,monkeypatch):
    guard,sample,clock,*_=rig
    import thermal_model.training_pressure_guard as training
    waits=[]
    def sleep(seconds):waits.append(seconds);sample(clock[0]+seconds)
    monkeypatch.setattr(training,'sleep',sleep)
    sample(10.1);guard.preflight()
    assert waits==[1]*5 and guard.previous[0]==15.1
