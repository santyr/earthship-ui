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
