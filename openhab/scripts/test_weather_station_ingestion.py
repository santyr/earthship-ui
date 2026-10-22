"""Corrected receiver owns freshness per field, never through a cached model."""
from datetime import datetime,timedelta,timezone
from importlib import import_module
from werkzeug.datastructures import MultiDict
import pytest

NOW=datetime(2026,10,22,17,tzinfo=timezone.utc)
def state():return import_module('weather_station_ingestion').StationState(timezone_name='America/Denver')
def observe(s,packet,seconds=0):return s.observe(MultiDict(packet),at=NOW+timedelta(seconds=seconds),tick=float(seconds))
def snap(s,seconds=0):return s.snapshot(at=NOW+timedelta(seconds=seconds),tick=float(seconds))
def outside(**fields):return dict(model='Fineoffset-WH65B',id='206',**fields)


def test_initial_health_is_degraded_and_missing_fields_are_null():
 s=state();v=snap(s)
 assert v['status']=='degraded' and v['flat']['AmbientWeatherWS2902A_WindSpeed'] is None


def test_independent_fields_expire_without_missing_or_invalid_fields_renewing_them():
 s=state();observe(s,outside(tempf='68',humidity='45'))
 observe(s,outside(tempf='bad'),100)
 v=snap(s,121)
 assert v['flat']['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature'] is None
 assert v['flat']['AmbientWeatherWS2902A_WeatherDataWs2902a_RelativeHumidity'] is None
 assert v['status']=='degraded'


def test_foreign_indoor_and_duplicate_values_never_count_as_measurements():
 s=state();assert observe(s,dict(model='Fineoffset-WH32B',id='999',tempinf='70')) is False
 p=MultiDict([('model','Fineoffset-WH65B'),('id','206'),('tempf','68'),('tempf','90')])
 s.observe(p,at=NOW,tick=0)
 assert snap(s)['flat']['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature'] is None


def test_derived_values_require_real_current_humidity_and_wind():
 s=state();observe(s,outside(tempf='95'))
 v=snap(s)['flat'];assert v['AmbientWeatherWS2902A_HeatIndex'] is None
 assert v['AmbientWeatherWS2902A_ApparentTemperature'] is None
 observe(s,outside(humidity='10',windspeedmph='5'),16)
 v=snap(s,16)['flat'];assert v['AmbientWeatherWS2902A_HeatIndex']==pytest.approx(89.5,abs=.2)
 assert v['AmbientWeatherWS2902A_ApparentTemperature'] is not None


def test_transition_apparent_temperature_keeps_real_wind_effect():
 s=state();observe(s,outside(tempf='65',humidity='50',windspeedmph='10'))
 v=snap(s)['flat']
 assert v['AmbientWeatherWS2902A_ApparentTemperature']==pytest.approx(58.4,abs=.1)


def test_huge_or_noncanonical_sensor_identity_is_a_rejection_not_an_exception():
 s=state()
 assert observe(s,dict(model='Fineoffset-WH32B',id='2'*5000,tempinf='70')) is False


def test_pressure_is_station_absolute_and_cold_trend_unavailable():
 s=state();observe(s,dict(model='Fineoffset-WH32B',id='235',baromabsin='23.89'))
 v=snap(s)
 assert v['flat']['WeatherStation_PressureAbsoluteV2']==23.89
 assert v['flat']['AmbientWeatherWS2902A_PressureTrend'] is None
 assert v['pressure']['identity']=='station_absolute'


@pytest.mark.parametrize('change,expected',[(.06,'rising'),(-.06,'falling'),(0.,'steady')])
def test_pressure_trend_uses_three_hours_not_the_last_twelve_packets(change,expected):
 s=state()
 # All change occurs more than an hour before the final receipt. The old
 # twelve-reading tail is constant and incorrectly reports steady.
 for seconds in range(0,10801,60):
  value=24.+change*min(seconds/3600,1)
  observe(s,dict(model='Fineoffset-WH32B',id='235',baromabsin=str(value)),seconds)
 assert snap(s,10800)['flat']['AmbientWeatherWS2902A_PressureTrend']==expected
 assert snap(s,10800)['pressure']['supportSeconds']==10800


def test_pressure_gap_or_short_history_withholds_trend():
 s=state()
 for seconds in range(0,1801,60):observe(s,dict(model='Fineoffset-WH32B',id='235',baromabsin=str(24+seconds/10000)),seconds)
 assert snap(s,1800)['flat']['AmbientWeatherWS2902A_PressureTrend'] is None
 observe(s,dict(model='Fineoffset-WH32B',id='235',baromabsin='24.2'),10800)
 assert snap(s,10800)['flat']['AmbientWeatherWS2902A_PressureTrend'] is None


def test_delayed_decode_cannot_extend_field_freshness_past_source_validity():
 s=state();observe(s,outside(tempf='68',radio_decode_utc=NOW.isoformat()),110)
 assert snap(s,121)['flat']['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature'] is None


def test_nws_simple_heat_index_is_averaged_with_air_temperature_below_regression_range():
 m=import_module('weather_station_ingestion')
 # NWS preliminary estimate 67.64 F, averaged with the 70 F air temperature.
 assert m.heat_index(70.,20.)==68.8


def test_solar_v2_does_not_replace_v1_inputs_and_channel_is_actual():
 s=state();observe(s,outside(light_lux='200000',solarradiation='1200',solarproxywm2_v2='1578.53'))
 observe(s,dict(model='AmbientWeather-WH31E',id='223',channel='2',tempinf='71'))
 v=snap(s);assert v['flat']['WeatherStation_SolarProxyV2']==1578.53
 assert v['flat']['AmbientWeatherWS2902A_SolarRadiation']==1200
 assert v['sensors']['bedroom']['channel']==2


def test_replayed_outdoor_decode_does_not_refresh_expiry_or_recover_invalid_field():
 s=state();source=NOW.isoformat()
 observe(s,outside(tempf='68',radio_decode_utc=source))
 observe(s,outside(tempf='68',radio_decode_utc=source),110)
 assert snap(s,121)['flat']['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature'] is None


def test_corrected_hook_runs_after_native_receipt_hooks_and_disabled_is_compatible():
 from flask import Flask
 m=import_module('weather_station_ingestion');app=Flask(__name__);seen=[]
 @app.before_request
 def native():seen.append('native')
 @app.get('/weather')
 def legacy():seen.append('legacy');return 'legacy'
 @app.get('/get_received_data')
 def get_all_received_data():return {'legacy':True}
 @app.get('/health')
 def health_check():return {'status':'ok'}
 assert m.install_station_ingestion(app,enabled=False) is None
 m.install_station_ingestion(app,enabled=True,timezone_name='America/Denver',clock=lambda:NOW,monotonic=lambda:0.)
 with app.test_client() as c:
  assert c.get('/weather',query_string=outside(tempf='68')).status_code==200
  assert seen==['native']
  assert c.get('/get_received_data').json['AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature']==68.
  assert c.get('/station_quality').json['schema']=='earthship-station-ingestion/v2'


def test_all_three_original_receipt_collectors_still_observe_before_corrected_response():
 from flask import Flask
 from weather_temperature_receiver import install_temperature_evidence
 from weather_temperature_evidence import TemperaturePolicy
 from weather_rain_receiver import install_rain_evidence
 from weather_rain_evidence import RainPolicy
 from weather_radiation_receiver import install_radiation_evidence
 from weather_radiation_evidence import RadiationPolicy
 app=Flask(__name__)
 @app.get('/weather')
 def legacy():pytest.fail('legacy mutation must be replaced')
 for endpoint in ('get_all_received_data','health_check'):
  app.add_url_rule('/'+endpoint,endpoint,lambda:'legacy')
 clocks=dict(clock=lambda:NOW,monotonic=lambda:0.)
 temp=install_temperature_evidence(app,enabled=True,policies={'outdoor':TemperaturePolicy('Fineoffset-WH65B',206,-40,140,120)},**clocks)
 rain=install_rain_evidence(app,enabled=True,policy=RainPolicy(206),**clocks)
 radiation=install_radiation_evidence(app,enabled=True,policy=RadiationPolicy(206),**clocks)
 import_module('weather_station_ingestion').install_station_ingestion(app,enabled=True,timezone_name='America/Denver',**clocks)
 with app.test_client() as c:
  assert c.get('/weather',query_string=outside(tempf='68',totalrainin='100',light_lux='200000',solarradiation='1200',solarproxywm2_v2='1578.53',radio_decode_utc=NOW.strftime('%Y-%m-%d %H:%M:%S'))).status_code==200
  assert c.get('/rain_evidence').json['record']['totalRainIn']==100.
  assert c.get('/radiation_evidence').json['record']['irradianceWm2']==1200.
  assert c.get('/temperature_evidence').json['records']['outdoor']['temperatureF']==68.


def test_explicit_enabled_bad_configuration_is_unavailable_not_legacy():
 from flask import Flask
 m=import_module('weather_station_ingestion');app=Flask(__name__)
 @app.get('/weather')
 def legacy():pytest.fail('invalid enabled configuration must not fall back')
 m.configure_station_ingestion(app,{'WEATHER_STATION_INGESTION_ENABLE':'1','WEATHER_STATION_TIMEZONE':'invalid/zone'})
 with app.test_client() as c:
  assert c.get('/weather').status_code==503
  assert c.get('/station_quality').status_code==503
