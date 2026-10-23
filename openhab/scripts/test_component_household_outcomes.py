"""New method cohorts and actual publication eligibility in the existing actor."""
from copy import deepcopy
from datetime import timedelta
import pytest
from household.codec import canonical,identity
from test_household_calibrated_outcomes import context
from test_native_thermal_artifact import originals

def test_new_component_origin_is_distinct_by_procedure_baseline_and_measurement(tmp_path,monkeypatch,originals):
 from household_calibrated_outcomes import _predictions
 _,args=context(tmp_path,monkeypatch,originals);forecast=args['forecast'];energy=args['energy'];plan=args['plan'];profiled=args['profiled']
 old=_predictions(forecast,plan,profiled)
 forecast['schema']='earthship-household-calibrated-energy-receipt/v2'
 forecast['output'].update(calibration_model_sha256='a'*64,procedure_sha256='b'*64,baseline_rule='native_component_fixture',
  measurement_cohort_sha256='c'*64,power_policy_sha256='d'*64,solar_grid_sha256='e'*64)
 forecast['inputs'].pop('calibration_raw')
 new=_predictions(forecast,plan,profiled)
 assert new['calibration_model_sha256']=='a'*64 and new['cohort']['procedure_sha256']=='b'*64
 assert new['cohort']['baseline_rule']=='native_component_fixture'
 assert new['cohort']['measurement_cohort_sha256']=='c'*64
 assert new['cohort_id']!=old['cohort_id'] and new['by_horizon']==old['by_horizon']

def test_prepared_new_receipt_never_enters_the_actual_published_inventory(tmp_path):
 from household_calibrated_score import _inventory
 from household_native_training import directory
 from test_component_household_worker import ISSUE
 store=directory(tmp_path/'forecasts');raw=canonical(dict(schema='earthship-household-calibrated-energy-receipt/v2',issued=False,output={'issued_at':ISSUE.isoformat()}))
 from hashlib import sha256
 path=store/(sha256(raw).hexdigest()+'.component-energy-v2.json');path.write_bytes(raw);path.chmod(0o600)
 assert _inventory(store,now=ISSUE+timedelta(seconds=30),guard=lambda:None)==[]

def test_component_forecast_sampling_does_not_require_a_legacy_directional_model():
 from household_calibrated_score import sample_key
 forecast=dict(schema='earthship-household-calibrated-energy-receipt/v2',inputs={},output=dict(issued_at='2026-06-21T12:00:00+00:00',
  calibration_model_sha256='a'*64,calibration_policy_sha256='b'*64,procedure_sha256='c'*64))
 assert sample_key(forecast)[1:] == ('a'*64,'b'*64,'c'*64)
