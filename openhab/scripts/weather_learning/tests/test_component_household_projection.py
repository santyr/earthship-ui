"""Both nominal-storage hypotheses consume the same new component PV steps."""
from datetime import timedelta
from copy import deepcopy
import pytest
from test_production_pv_runtime import owner_files
from test_production_pv import forecast,geometry,ORIGIN
from weather_learning.contracts import identity

def state():
 return dict(reason=None,initial_soc_pct=10.,nominal_bank_kwh=100.,current_load_reason=None,current_load_w=0.,
  battery_soc_evidence_sha256='a'*64,household_dc_scope='qualified_original_fixture')

def load():
 from household_ac_load_model import RULE
 value=dict(schema='earthship-ac-load-forecast/v1',model_rule=RULE,status='projected',origin=ORIGIN.isoformat(),model_sha256='b'*64,
  total_ac_kwh=7.2,trajectory=[dict(at=(ORIGIN+timedelta(hours=h)).isoformat(),mean_ac_w=300.,ac_kwh=.3,minimum_support_days=3,training_spread_mean_w=30.) for h in range(1,25)])
 value['forecast_sha256']=identity(value);return value


def test_same_selected_gain_feeds_component_energy_and_original_nominal_capacity(owner_files):
 from household_component_energy import project
 owner,_,_,model=owner_files
 out=project(owner,forecast=forecast(hours=24),positions=geometry(count=324),storage_inputs=state(),load_forecast=load())
 assert out['status']=='projected_provisional_calibrated_potential'
 assert out['calibration_sha256']==model.to_dict()['calibration_sha256']
 assert out['calibrated_potential_kwh']==pytest.approx(out['raw_potential_kwh']*.8)
 assert out['constant_load_storage']['nominal_bank_kwh']==100.
 assert out['profiled_storage']['status']=='conditional_nominal_simulation'
 assert out['uncalibrated_profiled_storage']['modeled_captured_pv_kwh']>out['profiled_storage']['modeled_captured_pv_kwh']
 assert out['physical_calibration_qualified'] is out['automatic_actuation'] is False


def test_missing_instantaneous_load_preserves_pv_and_the_original_learned_load_hypothesis(owner_files):
 from household_component_energy import project
 owner,*_=owner_files;initial=state();initial.update(current_load_reason='source_skew',current_load_w=None);curve=load();before=deepcopy(curve)
 out=project(owner,forecast=forecast(hours=24),positions=geometry(count=324),storage_inputs=initial,load_forecast=curve)
 assert out['calibrated_potential_kwh']>0
 assert out['constant_load_storage']==dict(status='unavailable',reason='source_skew')
 assert out['profiled_storage']['status']=='conditional_nominal_simulation'
 assert curve==before


def test_missing_qualified_initial_battery_state_does_not_withdraw_component_pv(owner_files):
 from household_component_energy import project
 owner,*_=owner_files;initial=state();initial.update(reason='battery_soc_expired',initial_soc_pct=None)
 out=project(owner,forecast=forecast(hours=24),positions=geometry(count=324),storage_inputs=initial,load_forecast=load())
 assert out['calibrated_potential_kwh']>0
 assert out['constant_load_storage']['reason']==out['profiled_storage']['reason']=='battery_soc_expired'
 assert out['uncalibrated_profiled_storage'] is None


def test_native_gain_does_not_adjust_total_only_fallback_before_storage(owner_files):
 from household_component_energy import project
 owner,*_=owner_files
 out=project(owner,forecast=forecast(hours=24,direct=None),positions=geometry(count=324),storage_inputs=state(),load_forecast=load())
 assert out['calibration_scope']=='raw_total_only_fallback'
 assert out['calibration_mode']=='raw_component_fallback'
 assert out['calibrated_potential_kwh']==out['raw_potential_kwh']
 assert out['profiled_storage']==out['uncalibrated_profiled_storage']
