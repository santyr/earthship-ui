"""The expected rain cohort comes from an actual current native receipt."""
from datetime import timedelta
from importlib import import_module
import pytest
from weather_learning.contracts import canonical,identity
from test_rain_calibration import POLICY,observed_inputs,resolution_document
from test_weather_rain_day import POLICY as NATIVE,snapshot,EPOCH
from weather_learning.rain_calibration import make_observation


def api():return import_module('weather_learning.rain_origin')


def test_current_native_origin_matches_the_observation_cohort_without_claiming_calibration():
 args=observed_inputs();at=args['requested_at'];raw=snapshot(at-timedelta(seconds=2),10,10.)[1]
 value=api().make_origin(raw=raw,requested_at=at,received_at=at+timedelta(seconds=1),policy=NATIVE,cutover=args['cutover'],resolution_source=None,experiment_policy=POLICY)
 assert value['status']=='available' and value['stream_epoch']==EPOCH
 assert value['cohort_sha256']==make_observation(**args).to_dict()['cohort_sha256']
 assert value['physical_calibration_qualified'] is False
 assert api().validate_origin(value)==value


def test_stale_missing_and_malformed_current_receipts_keep_context_unknown():
 args=observed_inputs();at=args['requested_at']
 for raw in [None,'{broken',snapshot(at-timedelta(seconds=121),10,10.)[1]]:
  value=api().make_origin(raw=raw,requested_at=at,received_at=at+timedelta(seconds=1),policy=NATIVE,cutover=args['cutover'],resolution_source=None,experiment_policy=POLICY)
  assert value['status']=='unavailable' and value['stream_epoch'] is None
  assert value['cohort_sha256']!=make_observation(**args).to_dict()['cohort_sha256']


def test_only_independently_available_resolution_can_define_the_origin_cohort():
 args=observed_inputs();doc=resolution_document(args);args['resolution_source']=doc;at=args['requested_at'];raw=snapshot(at-timedelta(seconds=2),10,10.)[1]
 value=api().make_origin(raw=raw,requested_at=at,received_at=at+timedelta(seconds=1),policy=NATIVE,cutover=args['cutover'],resolution_source=doc,experiment_policy=POLICY)
 assert value['cohort_sha256']==make_observation(**args).to_dict()['cohort_sha256'] and value['resolution_source_sha256']==identity(doc)
 doc=dict(doc,available_at=(at+timedelta(days=1)).isoformat())
 refused=api().make_origin(raw=raw,requested_at=at,received_at=at+timedelta(seconds=1),policy=NATIVE,cutover=args['cutover'],resolution_source=doc,experiment_policy=POLICY)
 assert refused['resolution_source_sha256'] is None and refused['resolution_reason']


def test_resealed_origin_cannot_change_its_native_epoch_or_acquisition_clock():
 args=observed_inputs();at=args['requested_at'];value=api().make_origin(raw=snapshot(at-timedelta(seconds=2),10,10.)[1],requested_at=at,received_at=at+timedelta(seconds=1),policy=NATIVE,cutover=args['cutover'],resolution_source=None,experiment_policy=POLICY)
 value['stream_epoch']='00000000-0000-4000-8000-000000000001';value['context_sha256']=identity({k:v for k,v in value.items() if k!='context_sha256'})
 with pytest.raises(ValueError):api().validate_origin(value)
 with pytest.raises(ValueError):api().make_origin(raw=None,requested_at=at,received_at=at-timedelta(seconds=1),policy=NATIVE,cutover=args['cutover'],resolution_source=None,experiment_policy=POLICY)
