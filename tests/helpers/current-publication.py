"""Synthetic publication mechanics only; no archive qualification or live I/O.

Use the real provider value type, publisher and deployment service verifier. The
unit fixture is deliberately hand-built and confers no release/model authority.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'openhab' / 'scripts'))
def denied(*args, **kwargs):
    raise AssertionError('unit probe must never open a network connection')
class BlockedSocket(socket.socket):
    connect = denied
    connect_ex = denied
socket.socket = BlockedSocket
socket.create_connection = denied
from weather_learning.config import Site
from weather_learning.provider import _body, _freeze, load_production_forecast, TEMPERATURE
from weather_learning.production_publish import production_states, publish_cycle, DETAIL
from household_cycle_deploy import _service_contract

now = datetime(2026, 10, 24, 18, tzinfo=timezone.utc)
body = _body(now, timedelta(hours=24), Site(38.37, -105.77, 'America/Denver'), [])
unavailable = _freeze(dict(body))
body.update(status='AVAILABLE', reason='NONE', source={'synthetic_unit_fixture': True}, issue_sha256='a'*64,
    hours=[dict(at='2026-10-24T19:00:00Z', temp_f=64.5, cloud_pct=35.0, radiation_wm2=700.0,
                precip_in=0.0, wind_mph=4.5)],
    days=[dict(date='2026-10-24', high_f=65.0, low_f=40.0, precip_sum_in=0.0)])
available = _freeze(body)

def cycle(provider, *, mismatch=False, authorized=True):
    held = {'Current_US_AQI': '501', 'Forecast_AQI': 'Hazardous', 'Thermal_Advisory': 'legacy'}
    # Independent full owned inventory, seeded before acquisition/failure. A
    # missing producer key must leave a visible held value and fail the test.
    held.update({
        'Forecast_Temp': '88', 'Forecast_Cloudiness': '77', 'Forecast_Radiation': '999',
        'Forecast_Daily_High': '98', 'Forecast_Daily_Low': '44', 'Forecast_Daily_PrecipSum': '12',
        'Forecast_Tomorrow_High': '91', 'Forecast_Tomorrow_Low': '43',
        'Forecast_Hourly_JSON': '[{"held":true}]', 'Forecast_Daily_JSON': '[{"held":true}]',
        'Forecast_10Day_JSON': '{"held":true}',
    })

    writes = []
    def put(item, raw):
        writes.append([item, raw]); held[item] = raw
    def read(item):
        return '999' if mismatch and item == 'Forecast_Temp' and held[item] != 'UNDEF' else held[item]
    try:
        result = publish_cycle(provider, now=now, put_state=put, read_state=read,
                               authorize=(lambda _: True) if authorized else None)
        return dict(result=result, writes=writes, held=held)
    except ValueError as error:
        return dict(error=str(error), writes=writes, held=held)

service = '''[Service]
TimeoutStartSec=90
CPUQuota=20%
MemoryMax=256M
MemorySwapMax=0
TasksMax=24
Nice=15
IOSchedulingClass=idle
IOWeight=10
ExecStart=/usr/bin/python3 /synthetic/provisional_thermal.py --config /synthetic/config.json --publish
'''
config = Path('/synthetic/config.json')
_service_contract(service.encode(), config)
rejections = {}
for name, old, new in [
    ('unbounded memory', 'MemoryMax=256M', 'MemoryMax=infinity'),
    ('swap', 'MemorySwapMax=0', 'MemorySwapMax=256M'),
    ('extra tasks', 'TasksMax=24', 'TasksMax=128'),
    ('deadline', 'TimeoutStartSec=90', 'TimeoutStartSec=300'),
    ('CPU', 'CPUQuota=20%', 'CPUQuota=100%'),
    ('different command', '--publish', '--train'),
    ('duplicate entrypoint', '[Service]', '[Service]\nExecStart=/bin/true'),
]:
    try:
        _service_contract(service.replace(old, new).encode(), config)
    except ValueError as error:
        rejections[name] = str(error)
    else:
        raise AssertionError('unsafe contract accepted: ' + name)
try:
    production_states(available, now=now+timedelta(seconds=1))
except ValueError as error:
    shifted_clock = str(error)
else:
    raise AssertionError('changed original decision accepted')
class Archive:
    def __init__(self, failure):
        self.failure = failure
    def eligible_snapshot(self, decision, last, *, required_variables):
        assert decision == now and last == now + timedelta(hours=24)
        assert required_variables == {TEMPERATURE}
        if self.failure == 'ARCHIVE_UNAVAILABLE':
            raise OSError('synthetic inaccessible archive')
        if self.failure == 'INVALID_SOURCE':
            return {'site': {'latitude': 0, 'longitude': 0, 'timezone': 'UTC'}}
        return None
acquisition = {}
for failure in ['NO_ELIGIBLE_SOURCE', 'ARCHIVE_UNAVAILABLE', 'INVALID_SOURCE']:
    provider = load_production_forecast(Archive(failure), decision_at=now,
        required_horizon=timedelta(hours=24), site=Site(38.37, -105.77, 'America/Denver'),
        required_variables={TEMPERATURE})
    acquisition[failure] = production_states(provider, now=now)
print(json.dumps(dict(available=cycle(available), unavailable=cycle(unavailable), acquisition=acquisition,
    mismatch=cycle(available, mismatch=True), denied=cycle(available, authorized=False),
    states=production_states(available, now=now), service_rejections=rejections,
    shifted_clock=shifted_clock)))
