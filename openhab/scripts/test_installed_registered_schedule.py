"""Staged units are review artifacts, not activation or household evidence."""
from pathlib import Path
import pytest

@pytest.fixture
def operands():
    return dict(sources='/private/runtime/scripts',live_config='/private/live.json',score_config='/private/score.json',registration='/private/registration.json',release_reference='/private/release.json',shared_lock='/private/global.lock')


def test_registered_schedule_staggers_all_horizons_and_preserves_caps(operands):
    from thermal_model.installed_shade_schedule import render_registered_monitoring_units
    units=render_registered_monitoring_units(template_directory=Path(__file__).resolve().parents[2]/'openhab/systemd/user',operands=operands)
    assert len(units)==18
    for n,hours in enumerate((1,6,12,24)):
        for kind,minute in (('score',1+5*n),('index',2+5*n)):
            name=f'thermal-registered-{kind}-{hours}'
            service=units[name+'.service'];timer=units[name+'.timer']
            assert f'--horizon {hours}' in service and '--score-registration /private/registration.json' in service
            assert '--queue ' not in service and '--contract-version 4' in service
            for line in ('CPUQuota=20%','MemoryMax=256M','MemorySwapMax=0','TasksMax=24','Nice=15','IOWeight=10','UMask=0077'):assert line in service.splitlines()
            assert 'timeout 60s' in service and f'*:{minute:02d}/20:00 UTC' in timer
            assert 'Persistent=false' in timer and f'Unit={name}.service' in timer
    publisher=units['thermal-registered-forecast.service']
    assert '--contract-version 3' in publisher and '--score-registration /private/registration.json' in publisher
    assert '--publish' in publisher and '--shared-lock /private/global.lock' in publisher
    assert all('@' not in value and '%h' not in value for value in units.values())

@pytest.mark.parametrize('value',['/private/new\nExecStart=/bin/false','/private/%h','/private/$token','relative/file','/private/../file'])
def test_schedule_rejects_unsafe_or_noncanonical_operands(operands,value):
    from thermal_model.installed_shade_schedule import render_registered_monitoring_units
    with pytest.raises(ValueError):render_registered_monitoring_units(template_directory=Path(__file__).resolve().parents[2]/'openhab/systemd/user',operands=dict(operands,registration=value))


def test_stage_retains_private_manifest_without_installing_or_enabling(operands,tmp_path):
    from thermal_model.installed_shade_schedule import stage_registered_monitoring_units
    tmp_path.chmod(0o700)
    manifest=stage_registered_monitoring_units(template_directory=Path(__file__).resolve().parents[2]/'openhab/systemd/user',operands=operands,output_directory=tmp_path)
    assert manifest['schema']=='earthship-registered-monitoring-stage/v1'
    assert manifest['release_authorized'] is False and manifest['services_enabled_by_stage'] is False
    assert len(manifest['units'])==18 and (tmp_path/'manifest.json').exists()
    assert all(p.stat().st_mode&0o777==0o600 for p in tmp_path.iterdir())


def test_stage_refuses_existing_contents_without_overwriting(operands,tmp_path):
    from thermal_model.installed_shade_schedule import stage_registered_monitoring_units
    tmp_path.chmod(0o700);p=tmp_path/'preserve';p.write_text('original');p.chmod(0o600)
    with pytest.raises(ValueError):stage_registered_monitoring_units(template_directory=Path(__file__).resolve().parents[2]/'openhab/systemd/user',operands=operands,output_directory=tmp_path)
    assert p.read_text()=='original' and not (tmp_path/'manifest.json').exists()


def test_staging_command_prints_only_review_status_and_writes_private_files(operands,tmp_path,capsys):
    import importlib.util
    path=Path(__file__).resolve().parents[2]/'scripts/stage-installed-monitoring.py'
    spec=importlib.util.spec_from_file_location('stage_monitoring',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    tmp_path.chmod(0o700);args=['--output-dir',str(tmp_path)]
    for name,value in operands.items():args.extend(['--'+name.replace('_','-'),value])
    assert module.main(args)==0
    output=capsys.readouterr().out
    assert 'staged_for_review' in output and '/private/' not in output
    assert (tmp_path/'manifest.json').exists()
