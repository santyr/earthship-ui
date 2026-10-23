"""Fresh electrical coefficients belong to their exact native-component baseline."""
from datetime import timedelta
from hashlib import sha256
import copy,json
import pytest
from native_solar_fixtures import T,ARRAY,HORIZON,geometry
from test_component_pv_model import forecast,ORIGIN
from weather_learning.contracts import canonical,identity,instant
from test_production_model_admission import AUTH

SYSTEM=canonical(dict(array=ARRAY));TERRAIN=canonical(dict(profile=HORIZON))
GRID=forecast()['rows'][0]['solar']['grid_sha256']
MEASUREMENT='a'*64
COHORT=identity(dict(measurement=MEASUREMENT,solar_grid=GRID))
CONTEXT=dict(measurement_cohort_sha256=MEASUREMENT,solar_grid_sha256=GRID,system_sha256=sha256(SYSTEM).hexdigest(),horizon_sha256=sha256(TERRAIN).hexdigest(),power_policy_sha256='b'*64,timezone='UTC',training_availability_basis='retrospective_assumed_full_cycle_9h')
CUTOFF=T-timedelta(days=2);FINISHED=T-timedelta(hours=1)

def api():
 from weather_learning import production_pv
 return production_pv

def rows():
 result=[]
 for day in range(4):
  for hour in range(8):
   origin=T-timedelta(days=7-day);end=origin+timedelta(hours=2+hour)
   value=dict(start=(end-timedelta(minutes=5)).isoformat(),end=end.isoformat(),origin=origin.isoformat(),native_w=100.+hour,total_only_w=200.,outcome_w=(100.+hour)*.8,
    fixed_gain=1.5,fixed_gain_source_sha256='c'*64,forecast_sha256=identity(dict(day=day,hour=hour)),energy_source_sha256='d'*64,outcome_available_at=(end+timedelta(minutes=2)).isoformat(),
    cohort_sha256=COHORT,availability_basis=CONTEXT['training_availability_basis'],native_supported=True,fallback_reason=None,azimuth_degrees=180.)
   value['pair_sha256']=identity(value);result.append(value)
 return result

def fit(values=None,**kwargs):
 values=rows() if values is None else values
 args=dict(rows=values,context=CONTEXT,cutoff=CUTOFF,source_available_at={r['forecast_sha256']:(CUTOFF-timedelta(hours=1)).isoformat() for r in values},population_sha256='e'*64,
  pair_producer_manifest=api().baseline_manifest(),authorization=AUTH,authorization_sha256=identity(AUTH),clock=lambda:FINISHED)
 args.update(kwargs);return api().fit_calibration(**args)

def project(model,**kwargs):
 args=dict(forecast=forecast(),positions=geometry(count=36),system_raw=SYSTEM,horizon_raw=TERRAIN,measurement_cohort_sha256=MEASUREMENT,power_policy_sha256='b'*64,
  start=ORIGIN,end=ORIGIN+timedelta(hours=1),authorize=lambda m:True)
 args.update(kwargs);return api().project_calibrated(model,**args)

def test_fresh_native_gain_ignores_old_total_only_coefficients_and_retains_actual_clocks():
 model,executed=fit();body=model.to_dict()
 assert executed is True and body['model']['gain']==pytest.approx(.8)
 assert body['actual_completed_at']==FINISHED.isoformat() and body['expires_at']==(FINISHED+timedelta(days=14)).isoformat()
 assert body['model']['support']['unique_measured_targets']==32
 assert body['training_availability_basis']==CONTEXT['training_availability_basis'] and body['issued'] is False

def test_future_actual_label_or_source_arrival_cannot_enter_current_training():
 values=rows()
 for row in values[-8:]:
  row['outcome_available_at']=(T+timedelta(days=2)).isoformat();row['outcome_w']=20000.
  row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
 model,_=fit(values)
 assert model.to_dict()['model']['gain']==pytest.approx(.8)
 assert model.to_dict()['model']['support']['unique_measured_targets']==24
 sources={r['forecast_sha256']:(T+timedelta(days=2) if i>=24 else CUTOFF-timedelta(hours=1)).isoformat() for i,r in enumerate(rows())}
 assert fit(source_available_at=sources)[0].to_dict()['model']['support']['unique_measured_targets']==24

def test_same_membership_reuses_original_fit_without_renewing_its_clocks():
 model,_=fit();again,executed=fit(previous=model,cutoff=CUTOFF+timedelta(hours=1),clock=lambda:FINISHED+timedelta(minutes=5))
 assert executed is False and again.to_dict()==model.to_dict()

def test_wrong_original_pair_producer_or_mixed_cohort_refuses_a_fit():
 manifest=api().baseline_manifest();manifest[next(iter(manifest))]='f'*64
 with pytest.raises(ValueError):fit(pair_producer_manifest=manifest)
 values=rows();values[0]['cohort_sha256']='f'*64;values[0]['pair_sha256']=identity({k:v for k,v in values[0].items() if k!='pair_sha256'})
 with pytest.raises(ValueError):fit(values)

def test_selected_projection_scales_exact_component_steps_without_changing_native_inputs():
 model,_=fit();value=project(model);raw=value['raw_projection'];adjusted=value['calibrated_projection']
 assert adjusted['potential_pv_kwh']==pytest.approx(raw['potential_pv_kwh']*.8)
 assert sum(r['potential_pv_kwh'] for r in adjusted['steps'])==pytest.approx(adjusted['potential_pv_kwh'])
 assert [(r['start'],r['end']) for r in adjusted['steps']]==[(r['start'],r['end']) for r in raw['steps']]
 assert value['calibration_sha256']==model.to_dict()['calibration_sha256']
 assert value['physical_calibration_qualified'] is False and value['issued'] is False

def test_owner_source_context_or_original_expiry_refusal_is_fatal(monkeypatch):
 model,_=fit()
 with pytest.raises((ValueError,PermissionError)):project(model,authorize=lambda m:False)
 for change in [dict(power_policy_sha256='f'*64),dict(measurement_cohort_sha256='f'*64),dict(system_raw=SYSTEM+b'\n')]:
  with pytest.raises(ValueError):project(model,**change)
 body=model.to_dict()
 with pytest.raises(ValueError):api().load_calibration(body,at=instant(body['expires_at']))
 manifest=api().baseline_manifest();manifest[next(iter(manifest))]='f'*64
 monkeypatch.setattr(api(),'baseline_manifest',lambda:manifest)
 with pytest.raises(ValueError):api().load_calibration(body,at=ORIGIN)

def test_retained_component_fit_reopens_without_renewal_or_fitting(tmp_path):
 from weather_learning.shadow import ShadowStore
 model,_=fit();state=ShadowStore(tmp_path/'component-state')
 pin=api().retain_calibration(state,model);raw=(state.root/'production-models'/(pin+'.json')).read_bytes()
 assert api().read_calibration(state,pin,at=ORIGIN).to_dict()==model.to_dict()
 assert api().retain_calibration(state,model)==pin
 assert (state.root/'production-models'/(pin+'.json')).read_bytes()==raw

def test_conditional_storage_consumes_new_component_steps_and_keeps_same_original_capacity():
 from household_pv_model import simulate_storage
 model,_=fit();prepared=project(model);storage=api().storage_projection(prepared,initial_soc_pct=10.,nominal_bank_kwh=100.,load_ac_w=0.)
 raw=simulate_storage(steps=prepared['raw_projection']['steps'],initial_soc_pct=10.,nominal_bank_kwh=100.,load_ac_w=0.)
 assert storage['nominal_bank_kwh']==100.
 assert storage['modeled_captured_pv_kwh']==pytest.approx(raw['modeled_captured_pv_kwh']*.8)
 assert storage['calibration_sha256']==model.to_dict()['calibration_sha256'] and storage['physical_calibration_qualified'] is False

def test_unavailable_native_direct_keeps_raw_total_only_fallback_without_native_coefficients():
 model,_=fit();prepared=project(model,forecast=forecast(direct=None))
 assert prepared['calibrated_projection']['potential_pv_kwh']==prepared['raw_projection']['potential_pv_kwh']
 assert prepared['calibrated_projection']['calibration_scope']=='raw_total_only_fallback'
 assert prepared['calibrated_projection']['calibrated_segments']==0

def test_total_only_fallback_rows_cannot_train_the_native_gain():
 values=rows()
 for row in values[-8:]:
  row.update(native_supported=False,fallback_reason='native_direct_unavailable',native_w=1000.,outcome_w=1000.)
  row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
 model,_=fit(values)
 assert model.to_dict()['model']['gain']==pytest.approx(.8)
 assert model.to_dict()['model']['support']['unique_measured_targets']==24
