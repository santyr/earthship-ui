"""Maintained, opt-in WS-2902 adapter; original receipt hooks run first.

No disk cache seeds measurement freshness. All times are HTTP receipt clocks;
radio decode clocks, when available, are distinct and cannot renew on replay.
"""
from datetime import datetime, timedelta, timezone
import math
import os
from threading import RLock
import time
from uuid import uuid4

from weather_station_rain import RainProducts

UTC = timezone.utc
OUTDOOR = 'Fineoffset-WH65B'
IDENTITIES = {(OUTDOOR, 206): 'outdoor', ('Fineoffset-WH24', 206): 'outdoor',
              ('Fineoffset-WH32B', 235): 'indoor',
              ('AmbientWeather-WH31E', 193): 'north_wall',
              ('AmbientWeather-WH31E', 223): 'bedroom'}
OUT_FIELDS = {
    'tempf': ('AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature', -40, 149),
    'humidity': ('AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity', 0, 100),
    'windspeedmph': ('AmbientWeatherWS2902A_WindSpeed', 0, 112),
    'windgustmph': ('AmbientWeatherWS2902A_WindGust', 0, 112),
    'winddir': ('AmbientWeatherWS2902A_WindDirectionDegrees', 0, 360),
    'totalrainin': ('AmbientWeatherWS2902A_RainFallTotal', 0, 100000),
    'solarradiation': ('AmbientWeatherWS2902A_SolarRadiation', 0, 1200),
    'light_lux': ('WeatherStation_LightLuxV2', 0, 200000),
    'solarproxywm2_v2': ('WeatherStation_SolarProxyV2', 0, 1600),
    'uv': ('AmbientWeatherWS2902A_UVIndex', 0, 15),
}
INDOOR_FIELDS = {
    'tempinf': ('AmbientWeatherWS2902A_IndoorSensor_Temperature', -40, 140),
    'humidityin': ('AmbientWeatherWS2902A_IndoorSensor_RelativeHumidity', 0, 100),
    'baromabsin': ('WeatherStation_PressureAbsoluteV2', 300*.02953, 1100*.02953),
}
DERIVED = ['DewPointTemperature', 'HeatIndex', 'WindChill', 'ApparentTemperature',
           'WindDirectionCardinal', 'UVDanger', 'PressureTrend', 'OutdoorBatteryStatus',
           'MaxDailyWindGust', 'MaxDailyOutdoorTemp', 'MinDailyOutdoorTemp',
           'MaxDailyOutdoorHumidity', 'MinDailyOutdoorHumidity',
           'RainFallHourlyRate', 'RainFallDay', 'RainFallWeek', 'RainFallMonth', 'RainFallEvent']


def _one(packet, key):
    values = packet.getlist(key) if hasattr(packet, 'getlist') else ([packet[key]] if key in packet else [])
    return values[0] if len(values) == 1 else None


def _number(value, minimum, maximum):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    if isinstance(value, str) and len(value) > 64:
        return None
    try:
        value = float(value)
    except (ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and minimum <= value <= maximum else None


def heat_index(t, rh):
    """NWS preliminary simple equation, then Rothfusz and humidity corrections."""
    if t is None or rh is None:
        return None
    simple = .5*(t+61+(t-68)*1.2+rh*.094)
    if (simple+t)/2 < 80:
        return round((simple+t)/2, 1)
    hi = (-42.379+2.04901523*t+10.14333127*rh-.22475541*t*rh
          -.00683783*t*t-.05481717*rh*rh+.00122874*t*t*rh
          +.00085282*t*rh*rh-.00000199*t*t*rh*rh)
    if rh < 13 and 80 <= t <= 112:
        hi -= ((13-rh)/4)*math.sqrt((17-abs(t-95))/17)
    elif rh > 85 and 80 <= t <= 87:
        hi += ((rh-85)/10)*((87-t)/5)
    return round(hi, 1)


class StationState:
    def __init__(self, *, timezone_name, validity_seconds=120):
        self.timezone_name = timezone_name
        self.validity = validity_seconds
        self.lock = RLock()
        self.last_clock = None
        self._reset()

    def _reset(self):
        self.epoch = str(uuid4())
        self.fields = {}
        self.sources = {}
        self.channels = {}
        self.pressures = []
        self.rain = RainProducts(timezone_name=self.timezone_name,
                                 validity_seconds=self.validity, maximum_counter_in=100000.)

    def _clock(self, at, tick):
        if not isinstance(at, datetime) or at.utcoffset() is None or type(tick) not in (int, float) or not math.isfinite(tick):
            raise ValueError('aware receipt clocks required')
        at = at.astimezone(UTC)
        if self.last_clock and (at < self.last_clock[0] or tick < self.last_clock[1]):
            self._reset()
        self.last_clock = at, tick
        return at

    def _mapping(self, role, sid=None):
        if role == 'outdoor':
            return OUT_FIELDS
        if role == 'indoor':
            return INDOOR_FIELDS
        return {'tempinf': (f'AmbientWeatherWS2902A_WH31E_{sid}_Temperature', -40, 140),
                'humidityin': (f'AmbientWeatherWS2902A_WH31E_{sid}_RelativeHumidity', 0, 100)}

    def observe(self, packet, *, at, tick):
        with self.lock:
            at = self._clock(at, tick)
            model, raw_id = _one(packet, 'model'), _one(packet, 'id')
            if not isinstance(raw_id, (str, int)) or isinstance(raw_id, bool) or not str(raw_id).isdigit():
                return False
            sid = int(raw_id)
            role = IDENTITIES.get((model, sid))
            if role is None:
                return False
            mapping = self._mapping(role, sid)
            source = _one(packet, 'radio_decode_utc')
            decoded = None
            if 'radio_decode_utc' in packet:
                try:
                    decoded = datetime.fromisoformat(source.replace('Z', '+00:00'))
                    # rtl_433 -M utc renders an explicitly configured UTC clock
                    # without a suffix; it is never interpreted as local time.
                    if decoded.utcoffset() is None:
                        decoded = decoded.replace(tzinfo=UTC)
                    decoded = decoded.astimezone(UTC)
                    if not -5 <= (at-decoded).total_seconds() <= self.validity:
                        raise ValueError('expired radio decode')
                except (ValueError, TypeError, AttributeError):
                    for name in mapping.values():
                        self.fields.pop(name[0], None)
                    if role == 'outdoor':
                        self.rain.invalidate()
                    return False
                prior = self.sources.get(role)
                if prior is not None and decoded <= prior:
                    return False
                self.sources[role] = decoded
            any_valid = False
            for key, (name, minimum, maximum) in mapping.items():
                if key not in packet:
                    continue
                value = _number(_one(packet, key), minimum, maximum)
                if value is not None and key in ('solarradiation', 'solarproxywm2_v2'):
                    lux = _number(_one(packet, 'light_lux'), 0, 200000)
                    expected = None if lux is None else round(min(lux/126.7, maximum), 2)
                    if value != expected:
                        value = None
                if value is None:
                    self.fields.pop(name, None)
                    if key == 'totalrainin':
                        self.rain.invalidate()
                    continue
                if key == 'totalrainin':
                    self.rain.observe(value, at=at, tick=tick)
                    if self.rain.broken:
                        self.fields.pop(name, None)
                        continue
                deadline = at+timedelta(seconds=self.validity)
                if decoded is not None:
                    deadline = min(deadline, decoded+timedelta(seconds=self.validity))
                self.fields[name] = dict(value=value, receivedAt=at.isoformat(),
                    validUntil=deadline.isoformat(),
                    radioDecodedAt=decoded.isoformat() if decoded else None,
                    role=role, tick=tick, expiresTick=tick+(deadline-at).total_seconds())
                any_valid = True
                if key == 'baromabsin':
                    if self.pressures and (at-self.pressures[-1][0]).total_seconds() > self.validity:
                        self.pressures.clear()
                    self.pressures.append((at, value))
                    cutoff = at-timedelta(hours=3)
                    while len(self.pressures) > 2 and self.pressures[1][0] <= cutoff:
                        del self.pressures[0]
                    if len(self.pressures) > 2048:
                        self.pressures = [(at, value)]
            if model == 'AmbientWeather-WH31E':
                channel = _number(_one(packet, 'channel'), 1, 8)
                if channel is not None and channel.is_integer():
                    self.channels[role] = int(channel)
            return any_valid

    def snapshot(self, *, at, tick):
        with self.lock:
            at = self._clock(at, tick)
            names = [v[0] for v in OUT_FIELDS.values()]+[v[0] for v in INDOOR_FIELDS.values()]
            for sid in (193, 223):
                names.extend(v[0] for v in self._mapping('extra', sid).values())
            flat = dict.fromkeys(names)
            flat.update({'AmbientWeatherWS2902A_'+name: None for name in DERIVED})
            # Retired misnamed alias does not claim relative/sea-level pressure.
            flat['AmbientWeatherWS2902A_WeatherDataWs2902A_PressureRelative'] = None
            evidence = {}
            for name, record in self.fields.items():
                fresh = (at < datetime.fromisoformat(record['validUntil']) and
                         0 <= tick-record['tick'] and tick < record['expiresTick'])
                evidence[name] = {k:v for k,v in record.items() if k not in ('tick','expiresTick')}
                evidence[name]['status'] = 'fresh' if fresh else 'stale'
                if fresh:
                    flat[name] = record['value']
            t, rh, speed, gust, direction, rain, solar, lux, proxy, uv = [flat[v[0]] for v in OUT_FIELDS.values()]
            hi = heat_index(t, rh)
            flat['AmbientWeatherWS2902A_HeatIndex'] = hi
            if t is not None and rh is not None and rh > 0:
                c = (t-32)/1.8
                gamma = math.log(rh/100)+17.62*c/(243.12+c)
                flat['AmbientWeatherWS2902A_DewPointTemperature'] = round(243.12*gamma/(17.62-gamma)*1.8+32, 1)
            if t is not None and speed is not None:
                flat['AmbientWeatherWS2902A_WindChill'] = round(35.74+.6215*t-35.75*speed**.16+.4275*t*speed**.16, 1) if t <= 50 and speed > 3 else round(t, 1)
            if t is not None and rh is not None and speed is not None:
                flat['AmbientWeatherWS2902A_ApparentTemperature'] = (flat['AmbientWeatherWS2902A_WindChill'] if t <= 50 else hi)
            if direction is not None:
                flat['AmbientWeatherWS2902A_WindDirectionCardinal'] = ('N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW')[int((direction+11.25)/22.5)%16]
            if uv is not None:
                flat['AmbientWeatherWS2902A_UVDanger'] = 'low' if uv < 3 else 'moderate' if uv < 6 else 'high' if uv < 8 else 'very high' if uv < 11 else 'extreme'
            pressure_method = dict(identity='station_absolute', method='three_hour_boundary_bracket_change_0.01inHg/v1', supportSeconds=0)
            if self.pressures and flat['WeatherStation_PressureAbsoluteV2'] is not None:
                duration = (self.pressures[-1][0]-self.pressures[0][0]).total_seconds()
                pressure_method['supportSeconds'] = duration
                if duration >= 10800:
                    start = self.pressures[-1][0]-timedelta(hours=3)
                    left = self.pressures[0]
                    right = left if left[0] == start else self.pressures[1]
                    lower = self.pressures[-1][1]-max(left[1],right[1])
                    upper = self.pressures[-1][1]-min(left[1],right[1])
                    pressure_method['changeBoundsInHg'] = [lower,upper]
                    flat['AmbientWeatherWS2902A_PressureTrend'] = ('rising' if lower > .01 else 'falling' if upper < -.01 else 'steady' if lower >= -.01 and upper <= .01 else None)
            sensors = {}
            for (model, sid), role in IDENTITIES.items():
                required = [v[0] for v in self._mapping(role, sid).values()]
                sensors[role] = dict(status='fresh' if all(flat[n] is not None for n in required) else 'degraded',
                                     channel=self.channels.get(role))
            return dict(schema='earthship-station-ingestion/v2', streamEpoch=self.epoch,
                generatedAt=at.isoformat(), status='ok' if all(s['status']=='fresh' for s in sensors.values()) else 'degraded',
                flat=flat, fields=evidence, sensors=sensors, pressure=pressure_method,
                rain=self.rain.snapshot(at=at, tick=tick),
                consoleCalibration='unknown', solarIdentity='lux_proxy_126.7_v2_not_calibrated_irradiance')


def install_station_ingestion(app, *, enabled=False, timezone_name=None, clock=None, monotonic=None):
    if enabled is not True:
        return None
    from flask import jsonify, request
    if 'station_quality' in app.view_functions:
        raise ValueError('station adapter already installed')
    state = StationState(timezone_name=timezone_name)
    clock = clock or (lambda: datetime.now(UTC))
    monotonic = monotonic or time.monotonic
    def current():
        return state.snapshot(at=clock(), tick=monotonic())
    @app.before_request
    def corrected_station_receipt():
        if request.path == '/weather' and request.method == 'GET':
            accepted = state.observe(request.args, at=clock(), tick=monotonic())
            return ('OK', 200) if accepted else ('No valid owned measurements', 400)
    app.view_functions['get_all_received_data'] = lambda: jsonify(current()['flat'])
    app.view_functions['health_check'] = lambda: jsonify({k:v for k,v in current().items() if k in ('schema','status','sensors','generatedAt','streamEpoch')})
    app.add_url_rule('/station_quality', 'station_quality', lambda: jsonify(current()), methods=['GET'])
    @app.after_request
    def station_no_cache(response):
        if request.path in ('/station_quality','/get_received_data','/health'):
            response.headers['Cache-Control'] = 'no-store'
        return response
    return state


def configure_station_ingestion(app, environ=None):
    """Default off. An explicitly enabled bad setup cannot claim old data is v2."""
    env = os.environ if environ is None else environ
    if env.get('WEATHER_STATION_INGESTION_ENABLE', '0') == '0':
        return None
    try:
        if env.get('WEATHER_STATION_INGESTION_ENABLE') != '1':
            raise ValueError('explicit station ingestion activation required')
        return install_station_ingestion(app, enabled=True,
            timezone_name=env.get('WEATHER_STATION_TIMEZONE'))
    except (ValueError, TypeError, KeyError):
        from flask import jsonify, request
        app.logger.error('enabled station ingestion configuration unavailable')
        def unavailable():
            response = jsonify(schema='earthship-station-ingestion/v2',status='unavailable')
            response.status_code = 503
            response.headers['Cache-Control'] = 'no-store'
            return response
        @app.before_request
        def station_configuration_unavailable():
            if request.path in ('/weather','/get_received_data','/health','/station_quality'):
                return unavailable()
        if 'station_quality' not in app.view_functions:
            app.add_url_rule('/station_quality','station_quality',unavailable,methods=['GET'])
        return None
