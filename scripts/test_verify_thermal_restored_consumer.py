"""No production connection or credentials; rejection happens before connect."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'openhab/scripts'))
from thermal_intel import _code_revision


@pytest.mark.parametrize('dsn,role', [
    ('host=127.0.0.1 port=5432 dbname=openhab user=postgres password=fixture', 'thermal_runtime'),
    ('host=192.0.2.1 port=55432 dbname=postgres user=postgres password=fixture', 'thermal_runtime'),
    ('host=127.0.0.1 port=55432 dbname=postgres user=postgres password=fixture', 'thermal_runtime'),
    ('host=127.0.0.1 port=55432 dbname=postgres user=postgres password=fixture', 'bad role'),
])
def test_non_disposable_or_writable_connection_refuses_before_connect(dsn, role):
    result = subprocess.run([sys.executable, str(ROOT/'scripts/verify-thermal-restored-consumer.py'),
        '--runtime-root', str(ROOT/'openhab/scripts'), '--expected-runtime-revision', _code_revision(),
        '--fixture-start', '2026-08-13T06:00:00+00:00', '--runtime-role', role],
        env={'PATH': '/usr/bin:/bin', 'THERMAL_RESTORE_PROBE_URL': dsn},
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {'status': 'withheld', 'error_type': 'ValueError'}
    assert not result.stderr and 'fixture' not in result.stdout
