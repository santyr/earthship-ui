"""Production forecast gets one CPU; other kernel limits remain bounded."""
from pathlib import Path
import pytest
from test_household_cycle_resources import fixture as resources


def test_forecast_admission_accepts_one_core_and_rejects_more(tmp_path):
    from household_cycle_resources import publication_resource_preflight
    args,_=resources(tmp_path)
    (args['leaf']/'cpu.max').write_text('100000 100000')
    publication_resource_preflight(**args)
    (args['leaf']/'cpu.max').write_text('100001 100000')
    with pytest.raises(ValueError):publication_resource_preflight(**args)


def test_forecast_driver_uses_production_resource_admission(tmp_path,monkeypatch):
    from test_household_native_cycle_driver import native_setup
    import thermal_model.serial_publication_caps as installed
    import household_cycle_resources as resources
    cycle,native,config,calls=native_setup(tmp_path,monkeypatch)
    def old_profile():raise AssertionError('development CPU profile used for production')
    monkeypatch.setattr(installed,'_resource_preflight',old_profile)
    monkeypatch.setattr(resources,'publication_resource_preflight',lambda:calls.append('production_resources'))
    assert cycle.run_cycle(config,code_revision='e'*40)['status']=='published'
    assert 'production_resources' in calls


def test_family_only_raises_forecast_cpu_for_new_pinned_driver(tmp_path):
    import household_native_family as family
    scripts=tmp_path/'sources/openhab/scripts';scripts.mkdir(parents=True)
    source=scripts/'household_cycle.py';source.write_text("FORECAST_CPU_QUOTA = '100%'\n")
    (scripts/'household_forecast_score.py').write_text('SCORE_LIFETIME_SECONDS = 120\n')
    (tmp_path/'service.conf').write_text('[Service]\nExecStart=\nExecStart=/usr/bin/python3 driver.py --stage '+str(tmp_path)+'\n')
    (tmp_path/'service.conf').chmod(0o600)
    files=family._render(tmp_path,tmp_path/'config',tmp_path/'libraries',deployment_sha256='a'*64)
    assert b'CPUQuota=100%\n' in files['forecast.conf']
    assert b'CPUQuota=20%\n' in files['thermal-native-geometry-prepare.service']
    assert b'CPUQuota=100%' not in files['score.conf']
    source.write_text('# previous sealed driver\n')
    old=family._render(tmp_path,tmp_path/'config',tmp_path/'libraries',deployment_sha256='a'*64)
    assert b'CPUQuota=100%' not in old['forecast.conf']


def test_owned_handoff_accepts_one_core_but_never_unbounded_cpu():
    import household_cycle_deploy as deploy
    state=dict(deploy.EFFECTIVE_LIMITS,MainPID='0',ActiveState='inactive',CPUQuotaPerSecUSec='1s')
    deploy._inactive_capped(state)
    state['CPUQuotaPerSecUSec']='infinity'
    with pytest.raises(ValueError):deploy._inactive_capped(state)
