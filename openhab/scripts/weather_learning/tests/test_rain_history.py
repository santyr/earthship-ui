"""Read-only original acquisitions retain refusals and their real clocks."""
from datetime import timedelta
from importlib import import_module
import json
import pytest
from test_rain_calibration import POLICY
from test_weather_rain_day import bounds,POLICY as NATIVE
from test_weather_rain_history import Connection
from weather_learning.contracts import canonical,identity,instant


def api():return import_module('weather_learning.rain_history')


def read(connection,*,cutover=None,clock=None,guard=lambda:None):
 start,end=bounds();times=iter([end+timedelta(seconds=120),end+timedelta(seconds=121)])
 return api().read_interval(lambda:connection,start=start,end=end,cutover=start if cutover is None else cutover,policy=NATIVE,resolution_source=None,experiment_policy=POLICY,clock=(lambda:next(times)) if clock is None else clock,guard=guard)


def test_generic_rain_reader_seals_actual_acquisition_and_native_sources():
 connection=Connection();capture=read(connection);value=capture.to_dict();observation=capture.observation()
 assert value['status']=='qualified' and observation.to_dict()['observed_mm']==pytest.approx(2.54)
 assert observation.to_dict()['available_at']==value['request']['received_at']
 assert instant(value['request']['received_at'])>max(instant(at) for at,raw in value['sources']['observations'])
 assert value['source_item']=='Weather_Rain_Evidence_JSON' and connection.closed
 assert connection.session==dict(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
 assert sum('SELECT time' in q for q,p in connection.queries)==2
 assert not any(word in q for q,p in connection.queries for word in ('INSERT','UPDATE','DELETE','COMMIT'))
 assert api().RainAcquisition(capture.content).observation().content==observation.content


def test_native_quality_refusal_retains_literal_counter_rows_without_zero_rain():
 connection=Connection(missing_carry=True);capture=read(connection);v=capture.to_dict()
 assert v['status']=='withheld' and capture.observation() is None
 assert v['sources']['observations'] and v['observation_sha256'] is None
 assert v['reason'] and v['continuous_depth_mm'] is None


@pytest.mark.parametrize('kwargs',[dict(readonly=False),dict(repeatable=False),dict(status=2),dict(matches=[]),dict(fail_source=True)])
def test_transport_failure_has_no_observation_or_write_authority(kwargs):
 connection=Connection(**kwargs);capture=read(connection);v=capture.to_dict()
 assert v['status']=='withheld' and v['sources']['transport_status']=='unavailable'
 assert capture.observation() is None and connection.closed


def test_pre_cutover_is_withheld_before_any_database_read():
 connection=Connection();capture=read(connection,cutover=bounds()[0]+timedelta(seconds=1))
 assert capture.to_dict()['reason']=='interval_before_cutover_or_not_mature'
 assert connection.queries==[] and capture.observation() is None


def test_changed_original_row_or_actual_clock_cannot_keep_a_derived_total():
 capture=read(Connection());v=capture.to_dict();v['continuous_depth_mm']=0.;v['acquisition_sha256']=identity({k:x for k,x in v.items() if k!='acquisition_sha256'})
 with pytest.raises(ValueError):api().RainAcquisition(canonical(v))
 v=capture.to_dict();at,raw=v['sources']['observations'][-1];body=json.loads(raw);body['record']['totalRainIn']+=.12;v['sources']['observations'][-1]=[at,json.dumps(body)];v['acquisition_sha256']=identity({k:x for k,x in v.items() if k!='acquisition_sha256'})
 with pytest.raises(ValueError):api().RainAcquisition(canonical(v))


def test_owner_timeout_is_not_consumed_as_an_optional_data_refusal():
 connection=Connection();calls=[]
 def guard():
  calls.append(1)
  if len(calls)>1:raise TimeoutError('owner deadline')
 with pytest.raises(TimeoutError):read(connection,guard=guard)
 assert connection.closed
