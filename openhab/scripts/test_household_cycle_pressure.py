"""Inference remains bounded without treating cold host swap as a training job."""
import importlib
import pytest


def fixture(tmp_path,monkeypatch):
    api=importlib.import_module('household_cycle_pressure')
    import thermal_installed_intel as installed
    calls=[];monkeypatch.setattr(installed,'_resource_preflight',lambda:calls.append('preflight'))
    vmstat=tmp_path/'vmstat';events=tmp_path/'memory.events'
    vmstat.write_text('pswpin 100\npswpout 100\noom_kill 3\n')
    events.write_text('low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\n')
    return api.PublicationHeadroom(vmstat=vmstat,memory_events=events,resource_check=lambda:installed._resource_preflight()),vmstat,events,calls


def test_cold_host_swap_does_not_cancel_bounded_publication(tmp_path,monkeypatch):
    monitor,vmstat,_,calls=fixture(tmp_path,monkeypatch);monitor.check()
    vmstat.write_text('pswpin 900000\npswpout 900000\noom_kill 3\n');monitor.check()
    assert len(calls)>=2


@pytest.mark.parametrize('counter',['host_oom','max','oom','oom_kill'])
def test_new_host_oom_or_worker_memory_limit_event_stops_publication(counter,tmp_path,monkeypatch):
    monitor,vmstat,events,_=fixture(tmp_path,monkeypatch);monitor.check()
    if counter=='host_oom':vmstat.write_text('pswpin 100\npswpout 100\noom_kill 4\n')
    else:events.write_text('low 0\nhigh 0\n'+'\n'.join(k+' '+('1' if k==counter else '0') for k in ['max','oom','oom_kill'])+'\n')
    with pytest.raises(ValueError):monitor.check()


@pytest.mark.parametrize('bad',['missing','negative','duplicate','regressed'])
def test_unknown_or_regressed_memory_counters_refuse(bad,tmp_path,monkeypatch):
    monitor,vmstat,_,_=fixture(tmp_path,monkeypatch);monitor.check()
    vmstat.write_text({'missing':'pswpout 1\n','negative':'oom_kill -1\n','duplicate':'oom_kill 3\noom_kill 3\n','regressed':'oom_kill 2\n'}[bad])
    with pytest.raises(ValueError):monitor.check()


def test_original_publication_resource_and_pressure_refusal_propagates(tmp_path,monkeypatch):
    monitor,*_=fixture(tmp_path,monkeypatch)
    import thermal_installed_intel as installed
    def refused():raise ValueError('publication memory pressure unavailable')
    monkeypatch.setattr(installed,'_resource_preflight',refused)
    with pytest.raises(ValueError,match='publication memory pressure'):monitor.check()


def test_preflight_observes_quiet_interval_without_numerical_work(tmp_path,monkeypatch):
    monitor,_,_,calls=fixture(tmp_path,monkeypatch)
    api=importlib.import_module('household_cycle_pressure');sleeps=[]
    monkeypatch.setattr(api,'sleep',lambda seconds:sleeps.append(seconds))
    monitor.preflight()
    assert sleeps==[1]*5 and len(calls)>=6


def default_fixture(tmp_path,monkeypatch):
    from pathlib import Path
    api=importlib.import_module('household_cycle_pressure')
    import thermal_installed_intel as installed
    monkeypatch.setattr(installed,'_resource_preflight',lambda:None)
    vmstat=tmp_path/'vmstat';vmstat.write_text('oom_kill 3\n')
    root=tmp_path/'cgroups';root.mkdir()
    for name in ['a','b']:
        leaf=root/name;leaf.mkdir();(leaf/'memory.events').write_text('max 0\noom 0\noom_kill 0\n')
    membership=tmp_path/'membership';membership.write_text('0::/a\n')
    small_text=api._small_text
    monkeypatch.setattr(api,'_small_text',lambda path:small_text(membership if str(path)=='/proc/self/cgroup' else path))
    monkeypatch.setattr(api,'Path',lambda value:root if str(value)=='/sys/fs/cgroup' else Path(value))
    return api.PublicationHeadroom(vmstat=vmstat,resource_check=lambda:installed._resource_preflight()),root,membership


def test_default_monitor_discovers_current_worker_leaf(tmp_path,monkeypatch):
    monitor,root,_=default_fixture(tmp_path,monkeypatch)
    monitor.check();monitor.check()
    assert monitor.memory_events==root/'a/memory.events'


def test_default_monitor_refuses_move_to_another_capped_leaf(tmp_path,monkeypatch):
    monitor,root,membership=default_fixture(tmp_path,monkeypatch);monitor.check()
    membership.write_text('0::/b\n');(root/'b/memory.events').write_text('max 5\noom 1\noom_kill 1\n')
    with pytest.raises(ValueError):monitor.check()


def test_default_monitor_refuses_replaced_leaf_with_same_name(tmp_path,monkeypatch):
    monitor,root,_=default_fixture(tmp_path,monkeypatch);monitor.check()
    (root/'a').rename(root/'old-a');(root/'a').mkdir()
    (root/'a/memory.events').write_text('max 0\noom 0\noom_kill 0\n')
    with pytest.raises(ValueError):monitor.check()


@pytest.mark.parametrize('row',['1:memory:/a','0::/a\n0::/b','0::/../a','0:://a'])
def test_default_monitor_refuses_unknown_or_unnormalized_membership(row,tmp_path,monkeypatch):
    monitor,_,membership=default_fixture(tmp_path,monkeypatch);membership.write_text(row)
    with pytest.raises(ValueError):monitor.check()
