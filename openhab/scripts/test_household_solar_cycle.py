"""New monitoring uses the scheduled observer and its existing bounded score slot."""
from pathlib import Path
import pytest
from household.codec import loads
from test_household_native_weather import originals


@pytest.mark.parametrize('blocked_public_target',[False,True])
def test_scheduled_cycle_materializes_curated_solar_view_after_retaining_originals(tmp_path,monkeypatch,originals,blocked_public_target):
    from native_cycle_test_support import energy_cycle
    cycle,args,calls,source,plan=energy_cycle(tmp_path,monkeypatch,originals)
    args['clock']=lambda:source['now'];args['collection']['originals']=dict(schema='earthship-household-cycle-sources/v7',
        load_topology_source=source['topology_source'],pv_system_source=source['system_source'],solar_horizon_source=source['horizon_source'])
    monkeypatch.setattr(cycle,'derive_cycle',lambda **kw:plan)
    path=args['observation_cache'].parent/'energy-observation.json'
    if blocked_public_target:
        path.write_bytes(b'{"owner":"unrelated"}');path.chmod(0o600)
    result=cycle.complete_cycle(**args);assert result['status']=='observation_written'
    if blocked_public_target:
        assert result['energy_observation_status']=='unavailable' and path.read_bytes()==b'{"owner":"unrelated"}'
        assert any(row[0]=='cache' for row in calls) and list(args['evidence_directory'].glob('*.household-energy-forecast-v1.json'))
        return
    path=args['observation_cache'].parent/'energy-observation.json';view=loads(path.read_bytes())
    original=loads(next(args['evidence_directory'].glob('*.household-energy-forecast-v1.json')).read_bytes())
    assert view['receipt_sha256']==original['receipt_sha256'] and len(view['trajectory'])==24
    assert path.stat().st_mode&0o777==0o600 and '/home/' not in path.read_text()


@pytest.mark.parametrize('fails',[False,True])
def test_solar_outcomes_share_only_unused_battery_slot_budget_without_affecting_battery(tmp_path,monkeypatch,fails):
    from test_native_serving_score_driver import fixture
    import household_battery_score as battery,household_solar_score as solar
    c,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,8)
    path=stage/'sources/openhab/scripts/household_solar_score.py';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# retained producer')
    class Pressure:
        def check(self):pass
    monkeypatch.setattr(c,'production_pressure_monitor',lambda:Pressure())
    monkeypatch.setattr(battery,'run',lambda **kw:dict(status='battery_performance_refreshed',count=12))
    def work(**kwargs):
        assert kwargs['stage']==stage and kwargs['historical']==[] and 100<kwargs['deadline']<=115
        kwargs['guard']()
        if fails:raise ValueError('operator-private-diagnostic')
        return dict(status='solar_storage_performance_refreshed',count=1,automatic_actuation=False)
    monkeypatch.setattr(solar,'run',work)
    result=c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100.)
    assert result['status']=='monitoring_refreshed' and result['battery_outcomes']['count']==12
    assert result['solar_outcomes']['status']==('deferred' if fails else 'solar_storage_performance_refreshed')
    assert 'operator-private-diagnostic' not in str(result) and 'read_model' not in calls


@pytest.mark.parametrize('fails',[False,True])
def test_profiled_outcomes_use_remaining_slot_without_changing_existing_results(tmp_path,monkeypatch,fails):
    from test_native_serving_score_driver import fixture
    import household_battery_score as battery,household_profiled_score as profiled
    c,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,8)
    path=stage/'sources/openhab/scripts/household_profiled_score.py';path.parent.mkdir(parents=True,exist_ok=True);path.write_text('# retained producer')
    class Pressure:
        def check(self):pass
    monkeypatch.setattr(c,'production_pressure_monitor',lambda:Pressure())
    monkeypatch.setattr(battery,'run',lambda **kw:dict(status='battery_performance_refreshed',count=12))
    def score(**kw):
        assert kw['stage']==stage and kw['historical']==[] and 100<kw['deadline']<=115;kw['guard']()
        if fails:raise ValueError('private source detail')
        return dict(status='profiled_energy_performance_refreshed',count=2)
    monkeypatch.setattr(profiled,'run',score)
    value=c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100.)
    assert value['battery_outcomes']['count']==12 and value['profiled_outcomes']['status']==('deferred' if fails else 'profiled_energy_performance_refreshed')
    assert 'private source detail' not in str(value)
