"""Run only the relay main AST with fake subprocess/output, never actual RF/HTTP."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path('/home/sat/bin/rtl_weather.py')


def relay(packet, observer=None):
    if not SOURCE.is_file(): pytest.skip('host relay unavailable')
    tree = ast.parse(SOURCE.read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    station = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'WH65B_STATION_ID' for target in node.targets))
    sent = []; calls = []
    def popen(*args, **kwargs):
        calls.append(args)
        if len(calls) > 1: raise FileNotFoundError('fixture stops relay loop')
        return SimpleNamespace(stdout=[json.dumps(packet)], poll=lambda: 0)
    namespace = {
        'subprocess': SimpleNamespace(Popen=popen, PIPE=-1, STDOUT=-2),
        'json': json, 'time': SimpleNamespace(sleep=lambda _: None),
        'logging': SimpleNamespace(**{name: lambda *a, **kw: None for name in ['info', 'warning', 'error', 'exception']}),
        'WH65B_STATION_ID': ast.literal_eval(station),
        '_should_send': lambda *a: True, 'send_data_to_flask': lambda payload: sent.append(payload.copy()),
        '_log_wh32b_id': lambda _: None,
        # The separately deployed project observer must never perform DB I/O
        # in this AST-only household forwarding fixture.
        '_lg_record_packet': observer,
    }
    exec(compile(ast.Module(body=[main], type_ignores=[]), str(SOURCE), 'exec'), namespace)
    namespace['main']()
    assert len(calls) == 2
    return sent


def packet(model, sensor_id):
    return {'model': model, 'id': sensor_id, 'temperature_C': 20, 'humidity': 45,
            'wind_dir_deg': 180, 'wind_avg_m_s': 1, 'wind_max_m_s': 2,
            'rain_mm': 10, 'light_lux': 12670, 'uvi': 1}


@pytest.mark.parametrize('model', ['Fineoffset-WH65B', 'Fineoffset-WH24'])
def test_actual_filtered_outdoor_identity_is_forwarded_without_value_changes(model):
    assert relay(packet(model, 206)) == [{'model': model, 'id': 206, 'tempf': 68.0, 'humidity': 45.0,
        'winddir': 180, 'windspeedmph': 2.24, 'windgustmph': 4.47, 'totalrainin': 10 * 0.03937,
        'solarradiation': 100.0, 'uv': 1.0}]


@pytest.mark.parametrize('sensor_id', [207, None, '206'])
def test_foreign_missing_or_wrong_type_outdoor_identity_remains_filtered(sensor_id):
    assert relay(packet('Fineoffset-WH65B', sensor_id)) == []


def test_optional_observer_failure_does_not_interrupt_household_forwarding():
    seen = []
    def failing_observer(_path, raw, station):
        seen.append((raw['id'], station))
        raise RuntimeError('offline observer failure')
    sent = relay(packet('Fineoffset-WH65B', 206), observer=failing_observer)
    assert seen == [(206, 206)]
    assert len(sent) == 1 and sent[0]['id'] == 206 and sent[0]['tempf'] == 68
