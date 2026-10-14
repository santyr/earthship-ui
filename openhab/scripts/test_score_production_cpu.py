"""Scoring uses the verified publication profile, including archived workers."""
import pytest


def test_score_family_opts_in_without_changing_old_archives(tmp_path):
    import household_native_family as family
    stage=tmp_path/'stage';scripts=stage/'sources/openhab/scripts';scripts.mkdir(parents=True)
    (scripts/'household_cycle.py').write_text('# retained\n')
    source=scripts/'household_forecast_score.py';source.write_text('# retained\n')
    template=stage/'service.conf';template.write_text('[Service]\nExecStart=/usr/bin/python3 driver.py --stage '+str(stage)+'\n');template.chmod(0o600)
    old=family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64)
    assert b'CPUQuota=100%' not in old['score.conf']
    source.write_text("SCORE_CPU_QUOTA = '100%'\nSCORE_LIFETIME_SECONDS = 120\n")
    new=family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64)
    assert b'CPUQuota=100%\n' in new['score.conf']
    assert b'CPUQuota=20%' in new['thermal-native-geometry-prepare.service']
    assert new['forecast.conf']==old['forecast.conf']


def test_archived_entrypoint_uses_explicit_policy_and_restores_it(monkeypatch):
    import household_forecast_score as score,thermal_installed_intel as installed
    import household_cycle_resources as resources,native_thermal_live as native
    original=installed._resource_preflight;resource_original=resources.publication_resource_preflight
    native_original=native._resource_preflight;calls=[]
    monkeypatch.setattr(score,'production_resource_preflight',lambda:calls.append('verified'))
    with score.production_score_policy():
        installed._resource_preflight();resources.publication_resource_preflight();native._resource_preflight()
    assert calls==['verified']*4
    assert resources.publication_resource_preflight is resource_original
    assert native._resource_preflight is native_original
    assert installed._resource_preflight is original
    with pytest.raises(RuntimeError):
        with score.production_score_policy():raise RuntimeError('worker failed')
    assert installed._resource_preflight is original


def test_archive_cannot_enter_if_publication_policy_refuses(monkeypatch):
    import household_forecast_score as score,thermal_installed_intel as installed
    original=installed._resource_preflight
    def refuse():raise ValueError('publication caps exceed approved limits')
    monkeypatch.setattr(score,'production_resource_preflight',refuse)
    with pytest.raises(ValueError):
        with score.production_score_policy():pytest.fail('refused worker entered')
    assert installed._resource_preflight is original


def test_policy_source_drift_refuses_before_execution(tmp_path,monkeypatch):
    import household_forecast_score as score
    coordinator=tmp_path/'household_forecast_score.py';coordinator.write_text('# test\n')
    (tmp_path/'household_cycle_resources.py').write_text("raise AssertionError('must not load changed policy')\n")
    (tmp_path/'household_cycle_resources.py').chmod(0o644)
    monkeypatch.setattr(score,'__file__',str(coordinator))
    with pytest.raises(ValueError,match='policy source'):
        score.production_resource_preflight()


def test_one_core_score_effective_readback_matches_only_opted_in_family(tmp_path,monkeypatch):
    import household_native_family as family
    from test_native_serving_effective import fixture
    monkeypatch.setattr(family,'_score_cpu_quota',lambda stage:'100%')
    install,selected,pin,states=fixture(tmp_path,monkeypatch)
    states['thermal-provisional-score.service']['CPUQuotaPerSecUSec']='1s'
    assert install._verify_effective_family(selected,guard=lambda:None)['deployment_sha256']==pin
    states['thermal-provisional-score.service']['CPUQuotaPerSecUSec']='200ms'
    with pytest.raises(ValueError,match='role CPU budget'):
        install._verify_effective_family(selected,guard=lambda:None)


def test_retained_pressure_monitor_checks_actual_worker_cgroup():
    # Run under the same one-core, 256-MiB, zero-swap scope as production.
    # Dropping the leaf keyword from the adapter breaks this real caller.
    import household_forecast_score as score
    from native_inference_pressure import NativeInferenceHeadroom
    with score.production_score_policy():
        pressure=NativeInferenceHeadroom()
        pressure.check()
        assert pressure.cgroup_binding is not None
        pressure.check()
        assert pressure.refused is False


def test_explicit_missing_cgroup_is_not_replaced_with_current_worker(tmp_path):
    import household_forecast_score as score
    with pytest.raises(ValueError,match='verified publication resources required'):
        score.production_resource_preflight(leaf=tmp_path/'missing-cgroup')


def test_retained_native_uses_current_monitor_instead_of_retired_swap_guard(tmp_path,monkeypatch):
    import household_forecast_score as score,native_inference_pressure as native
    from pathlib import Path
    for name in ('household_forecast_score.py','household_cycle_resources.py','household_cycle_pressure.py','household_score_report_reuse.py'):
        target=tmp_path/name;target.write_bytes(Path(score.__file__).with_name(name).read_bytes());target.chmod(0o644)
    monkeypatch.setattr(score,'__file__',str(tmp_path/'household_forecast_score.py'))
    class RetiredMonitor:
        def __init__(self):raise AssertionError('retired host-wide swap guard executed')
    monkeypatch.setattr(native,'NativeInferenceHeadroom',RetiredMonitor)
    with score.production_score_policy():
        monitor=native.NativeInferenceHeadroom();monitor.preflight();monitor.check()
    assert native.NativeInferenceHeadroom is RetiredMonitor


def test_retained_worker_exit_forces_current_memory_event_check(tmp_path,monkeypatch):
    import household_forecast_score as score,native_inference_pressure as native
    from household_cycle_pressure import PublicationHeadroom
    vmstat=tmp_path/'vmstat';vmstat.write_text('oom_kill 0\n')
    events=tmp_path/'memory.events';events.write_text('max 0\noom 0\noom_kill 0\n')
    def monitor():
        return PublicationHeadroom(vmstat=vmstat,memory_events=events,resource_check=score.production_resource_preflight)
    monkeypatch.setattr(score,'production_pressure_monitor',monitor,raising=False)
    original=native.NativeInferenceHeadroom
    with pytest.raises(ValueError,match='memory-limit counters changed'):
        with score.production_score_policy():
            pressure=native.NativeInferenceHeadroom();pressure.preflight()
            events.write_text('max 1\noom 0\noom_kill 0\n')
    assert native.NativeInferenceHeadroom is original


def test_current_monitor_source_drift_refuses_before_loading(tmp_path,monkeypatch):
    import household_forecast_score as score
    coordinator=tmp_path/'household_forecast_score.py';coordinator.write_text('# test\n')
    (tmp_path/'household_cycle_pressure.py').write_text("raise AssertionError('changed monitor loaded')\n")
    (tmp_path/'household_cycle_pressure.py').chmod(0o644)
    monkeypatch.setattr(score,'__file__',str(coordinator))
    with pytest.raises(ValueError,match='monitor source'):
        score.production_pressure_monitor()


@pytest.mark.parametrize('operation',['production_resource_preflight','production_pressure_monitor'])
def test_policy_sample_during_original_verification_does_not_mutate_inventory(tmp_path,monkeypatch,operation):
    import household_forecast_score as score
    from thermal_model.origin_capture import _source_bytes
    from thermal_model.replay_budget import capture_source_reads,shared_replay_budget
    from pathlib import Path
    for name in ('household_forecast_score.py','household_cycle_resources.py','household_cycle_pressure.py','household_score_report_reuse.py'):
        target=tmp_path/name;target.write_bytes(Path(score.__file__).with_name(name).read_bytes());target.chmod(0o644)
    monkeypatch.setattr(score,'__file__',str(tmp_path/'household_forecast_score.py'))
    original=tmp_path/'original';original.write_bytes(b'original evidence');original.chmod(0o600)
    later=tmp_path/'later';later.write_bytes(b'later evidence');later.chmod(0o600)
    calls=[]
    def remaining():
        calls.append(True)
        # First sample happens after iteration of the original inventory starts.
        if len(calls)==3:getattr(score,operation)()
        return 30.
    with shared_replay_budget(remaining),capture_source_reads() as inventory:
        _source_bytes(original,maximum=32)
        inventory.verify()
        assert set(inventory.records)=={original}
        _source_bytes(later,maximum=32)
        assert set(inventory.records)=={original,later}
        inventory.verify()
        later.write_bytes(b'changed bytes')
        with pytest.raises(ValueError,match='source metadata changed|source bytes changed'):
            inventory.verify()
