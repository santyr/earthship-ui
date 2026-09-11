"""Run only the relay main AST with fake subprocess/output, never actual RF/HTTP."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path('/home/sat/bin/rtl_weather.py')


def relay(packet):
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
