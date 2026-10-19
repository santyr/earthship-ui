"""The retained journal/helpers must not select an incumbent weather producer."""
from pathlib import Path
import subprocess
import sys

import pytest


def test_local_thermal_helpers_work_without_retired_forecast_provider():
    code = """
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, *args):
  if fullname == 'forecast_intel': raise AssertionError('retired forecast provider imported')
sys.meta_path.insert(0, Block())
import thermal_intel as thermal
assert 'forecast_intel.py' not in thermal._release_runtime_paths()
assert len(thermal._code_revision()) == 64
args = thermal._build_parser().parse_args(['journal', '--message-file', '/private/message', '--idempotency-key', 'local-message'])
assert args.subcommand == 'journal'
assert thermal._build_parser().parse_args(['schema-audit']).subcommand == 'schema-audit'
assert 'forecast_intel' not in sys.modules
"""
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=30, cwd=Path(__file__).resolve().parent)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('arguments', [
    ['train'], ['backtest'], ['shadow'],
    ['release', '--evidence-inputs', '/private/inputs'],
    ['observe-candidate', '--model-directory', '/private/models', '--origin-capture-dir', '/private/origins',
     '--output', '/private/shadow', '--candidate-sha256', 'a'*64, '--runtime-sha256', 'b'*64],
])
def test_journal_cli_rejects_retired_weather_commands(arguments):
    import thermal_intel
    with pytest.raises(SystemExit) as error:
        thermal_intel._build_parser().parse_args(arguments)
    assert error.value.code == 2


def test_retired_thermal_factories_cannot_be_called_directly():
    import thermal_intel
    assert not [name for name in ('_training_kwargs', '_train', '_backtest', '_shadow', '_observe_candidate', '_release', '_forecast_rows')
                if hasattr(thermal_intel, name)], 'retired weather producer remains callable'


@pytest.mark.parametrize('relative', [
    'scripts/experiment-sunset-soc-drop.py',
    'scripts/household_energy_source_install.py',
    'scripts/weather_forecast_lock_wait.py',
    'scripts/daily_forecast_lock_wait.py',
    'openhab/systemd/user/forecast-json.service.d/zzzz-weather-lock-wait.conf',
    'openhab/systemd/user/forecast-intel.service.d/zzzz-daily-lock-wait.conf',
])
def test_retired_forecast_installers_and_cached_state_tool_are_unavailable(relative):
    root = Path(__file__).resolve().parents[2]
    assert not (root / relative).exists(), 'obsolete provider entry point remains available: ' + relative


def test_file_transactions_have_no_builtin_provider_deployment(tmp_path):
    import importlib.util
    root = Path(__file__).resolve().parents[2]
    script = root / 'scripts/thermal-model-files.py'
    spec = importlib.util.spec_from_file_location('_explicit_file_transactions', script)
    files = importlib.util.module_from_spec(spec); spec.loader.exec_module(files)
    assert not hasattr(files, 'MANIFEST'), 'implicit incumbent deployment remains available'
    with pytest.raises(TypeError, match='manifest'):
        files.capture_backup(tmp_path / 'absent-repo', tmp_path / 'absent-receipt')
    assert not (tmp_path / 'absent-receipt').exists()
    result = subprocess.run([sys.executable, str(script), 'install-code', '--repo-root', str(tmp_path / 'repo'), '--receipt-dir', str(tmp_path / 'receipt')], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2, 'retired provider deployment command was not rejected by the parser'


@pytest.mark.parametrize('relative', ['scripts/forecast-recovery-files.py', 'scripts/activate-forecast-recovery.py', 'scripts/thermal-replay-bundle.py', 'scripts/qualify-thermal-radiation-runtime.py', 'scripts/thermal-radiation-files.py', 'scripts/verify-thermal-natural-publication.py', 'scripts/qualify-thermal-collector-baseline-bundle.py', 'scripts/replay-thermal-forcing.py', 'deploy/forecast-intel.timer', 'deploy/forecast-intel.service', 'deploy/forecast-pre-dusk.timer', 'deploy/thermal-model-shadow.service', 'deploy/forecast-json.timer', 'deploy/forecast-intel-fetch-recovery.service', 'deploy/thermal-model-train.service', 'deploy/thermal-model-train.timer', 'deploy/forecast-intel-fetch-recovery.timer', 'deploy/thermal-model-shadow.timer', 'deploy/forecast-json.service', 'deploy/forecast-pre-dusk.service', 'deploy/forecast-intel.service.d/fetch-recovery.conf', 'deploy/thermal-model-shadow.service.d/bounded-retry.conf', 'deploy/thermal-model-shadow.service.d/qualified-radiation.conf', 'deploy/thermal-model-shadow.service.d/forcing-capture.conf', 'deploy/forecast-intel-fetch-recovery.service.d/enabled.conf', 'openhab/systemd/user/forecast-temperature-score.service', 'openhab/systemd/user/forecast-temperature-score.timer', 'openhab/systemd/user/forecast-pre-dusk.timer', 'openhab/systemd/user/forecast-pre-dusk.service', 'openhab/systemd/user/forecast-pre-dusk.service.d/zzz-bounded-native-inputs.conf', 'openhab/systemd/user/thermal-model-train.service.d/resource-limits.conf', 'openhab/systemd/user/thermal-model-train.service.d/memory-preflight.conf', 'openhab/systemd/user/thermal-model-train.service.d/memory-preflight.awk', 'openhab/systemd/user/forecast-intel.service.d/qualified-soc.conf', 'openhab/systemd/user/thermal-model-shadow.service.d/zzzz-legacy-origin-observer.conf'])
def test_closed_provider_operator_tools_and_schedules_are_absent(relative):
    root = Path(__file__).resolve().parents[2]
    assert not (root / relative).exists(), "obsolete forecast operator or schedule remains: " + relative


def test_file_transactions_write_only_the_explicit_manifest(tmp_path, monkeypatch):
    import importlib.util
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location('_manifest_only_file_transactions', root / 'scripts/thermal-model-files.py')
    files = importlib.util.module_from_spec(spec); spec.loader.exec_module(files)
    implicit = tmp_path / 'implicit-model-state'
    monkeypatch.setattr(files, 'ALLOWED_STATE_ROOT', implicit)
    repo = tmp_path / 'repo'; source = repo / 'deploy/thermal-model-shadow.service.d/forcing-capture.conf'
    source.parent.mkdir(parents=True); source.write_bytes(b'explicit unit data')
    target = tmp_path / 'live/unit.conf'; receipt = tmp_path / 'receipt'
    manifest = ({'source': 'deploy/thermal-model-shadow.service.d/forcing-capture.conf',
                 'target': str(target), 'phase': 'unit', 'mode': 0o644},)
    files.capture_backup(repo, receipt, manifest=manifest)
    files.install_phase(repo, receipt, 'unit', manifest=manifest)
    assert target.read_bytes() == b'explicit unit data'
    assert not implicit.exists(), 'transaction created unlisted legacy model state'
