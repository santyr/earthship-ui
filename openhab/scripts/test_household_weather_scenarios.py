"""Constructed weather is advisory and cannot impersonate original forecasts."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import importlib,json
import pytest
from native_solar_fixtures import T,SITE,ARRAY,HORIZON,snapshot,geometry
from weather_learning.native_forecast import make_native_component_forecast,validate_native_forecast
from weather_learning.contracts import canonical,identity,instant

ROOT=Path(__file__).resolve().parents[2]
POLICY=json.loads((ROOT/'docs/operations/weathernext3-capabilities/scenario-protocol.json').read_bytes())
THERMAL_POLICY=json.loads((ROOT/'docs/operations/weathernext3-capabilities/thermal-solar-protocol.json').read_bytes())
ORIGIN=T+timedelta(hours=1)
def api():return importlib.import_module('weather_learning.scenarios')
def context(hours=3):
 return dict(forcing=make_native_component_forecast(snapshot(hours=hours+3),origin=ORIGIN,horizon_hours=hours,available_by=ORIGIN,site=SITE),policy=deepcopy(POLICY))
def cases(hours=3):return api().stress_cases(**context(hours))


def test_three_fixed_cases_retain_original_forecast_and_distinct_constructed_identities():
 c=context();before=canonical(c['forcing']);result=api().stress_cases(**c)
 assert [s.to_dict()['recipe']['name'] for s in result]==['central','reduced_solar','warm_high_gain']
 for scenario in result:
  value=scenario.to_dict();assert value['original_forecast']==c['forcing'] and canonical(c['forcing'])==before
  assert value['probability_claim'] is value['automatic_actuation'] is value['release_authorized'] is False
  assert api().validate_scenario(scenario)==value
  with pytest.raises(ValueError):validate_native_forecast(value)
  assert value['forecast_sha256']!=c['forcing']['forecast_sha256']
 base,low,warm=[s.to_dict() for s in result]
 assert low['rows'][1]['solar']['total_j_m2']==base['rows'][1]['solar']['total_j_m2']*.5
 assert warm['rows'][1]['tempF']==pytest.approx(base['rows'][1]['tempF']+5.4)
 assert warm['rows'][1]['solar']['direct_j_m2']==base['rows'][1]['solar']['direct_j_m2']*1.2


def test_original_replay_refuses_resealed_changed_rows_or_unapproved_stress_recipe():
 value=cases()[0].to_dict()
 for field in ['rows','recipe','original_forecast','policy']:
  damaged=deepcopy(value)
  if field=='rows':damaged[field][1]['tempF']+=1
  elif field=='recipe':damaged[field]['solar_multiplier']=8
  elif field=='policy':damaged[field]['stress_cases'][0]['temperature_delta_c']=99
  else:damaged[field]['rows'][0]['tempF']+=1
  damaged['forecast_sha256']=identity({k:v for k,v in damaged.items() if k!='forecast_sha256'})
  with pytest.raises(ValueError):api().ScenarioForcing(canonical(damaged))


def test_same_shared_component_PV_arithmetic_for_central_and_night_zero_for_all_cases():
 from household_pv_components import project_window_components
 positions=geometry(start=ORIGIN,count=36,elevation=lambda i:-10. if i<=12 else 30.)
 original=context()['forcing'];arguments=dict(array=ARRAY,positions=positions,start=ORIGIN,end=ORIGIN+timedelta(hours=3),timezone_name='UTC',horizon_profile=HORIZON)
 central=project_window_components(forecast=original,**arguments)
 projections=[project_window_components(forecast=s,**arguments) for s in cases()]
 assert projections[0]['potential_pv_kwh']==pytest.approx(central['potential_pv_kwh'])
 assert projections[1]['potential_pv_kwh']<projections[0]['potential_pv_kwh']<projections[2]['potential_pv_kwh']
 for projection in projections:
  assert all(r['potential_dc_w']==0 for r in projection['segments'][:12])
  assert projection['evidence_class']=='constructed_unqualified_weather_sensitivity'


def test_storage_propagation_uses_current_model_with_explicit_fixed_uncertainty_scope():
 from household_pv_components import project_window_components
 from household_pv_model import simulate_storage
 arguments=dict(positions=geometry(start=ORIGIN,count=36),array=ARRAY,horizon_profile=HORIZON,initial_soc_pct=80.,nominal_bank_kwh=10.,load_ac_w=500.,thermal_context=None)
 result=api().propagate(cases()[1],**arguments);pv=result['pv'];expected=simulate_storage(steps=pv['steps'],initial_soc_pct=80.,nominal_bank_kwh=10.,load_ac_w=500.)
 assert result['nominal_storage']==expected
 assert result['minimum_nominal_soc_pct']==min(80.,*(r['nominal_soc_pct'] for r in expected['trajectory']))
 assert result['thermal']['status']=='unavailable' and result['thermal']['reason']=='compatible_component_response_model_not_supplied'
 assert result['uncertainty_scope']==POLICY['uncertainty_scope']
 assert result['reserve_breach_probability'] is result['overheating_probability'] is None
 assert result['probability_claim'] is result['automatic_actuation'] is False


@pytest.mark.parametrize('damage',['geometry_gap','solar_proxy_model','future_model'])
def test_incomplete_geometry_or_incompatible_thermal_response_is_refused(damage):
 arguments=dict(positions=geometry(start=ORIGIN,count=36),array=ARRAY,horizon_profile=HORIZON,initial_soc_pct=80.,nominal_bank_kwh=10.,load_ac_w=500.,thermal_context=None)
 if damage=='geometry_gap':arguments['positions'].pop()
 elif damage=='solar_proxy_model':arguments['thermal_context']={'schema':'legacy-proxy','coefficients':[1.]*6}
 else:arguments['thermal_context']={'schema':'earthship-component-thermal-scenario-context/v1','available_at':(ORIGIN+timedelta(days=1)).isoformat()}
 with pytest.raises(ValueError):api().propagate(cases()[0],**arguments)


def residual_blocks(*,count=10,late=False,hours=3,proxy=False):
 from unittest.mock import patch
 import native_solar_fixtures as fixtures
 result=[]
 for day in range(1,count+1):
  past=T-timedelta(days=day);origin=past+timedelta(hours=1)
  with patch.object(fixtures,'T',past):source=fixtures.snapshot(hours=hours+3)
  forecast=make_native_component_forecast(source,origin=origin,horizon_hours=hours,available_by=origin,site=SITE)
  observations=[]
  for i,row in enumerate(forecast['rows']):
   at=instant(row['at']);sign=(-1)**day;offset=sign*(i+1)*.2
   observations.append(dict(at=row['at'],temperature_c=(row['tempF']-32)/1.8+offset,wind_m_s=row['windMph']*.44704+offset*.5,ghi_wm2=row['radiationWm2']+offset*30,solar_quantity='reported_local_proxy' if proxy else 'physical_global_horizontal_irradiance',available_at=(at+timedelta(minutes=5,days=20 if late else 0)).isoformat(),measurement_cohort_sha256='c'*64,original_sha256=identity(('synthetic-observation',day,i))))
  result.append(api().make_residual_block(forcing=forecast,observations=observations,cohort_sha256='c'*64))
 return result


def test_joint_method_reuses_whole_issue_available_multivariate_blocks_with_fixed_seed():
 c=context();blocks=residual_blocks();before=[b.content for b in blocks]
 result=api().joint_scenarios(**c,blocks=blocks,cohort_sha256='c'*64)
 assert result['status']=='unqualified_joint_scenarios' and len(result['scenarios'])==6
 assert result['probability_claim'] is result['automatic_actuation'] is False
 again=api().joint_scenarios(**c,blocks=list(reversed(blocks)),cohort_sha256='c'*64)
 assert [s.content for s in again['scenarios']]==[s.content for s in result['scenarios']]
 by_pin={b.to_dict()['block_sha256']:b.to_dict() for b in blocks}
 for scenario in result['scenarios']:
  value=scenario.to_dict();block=by_pin[value['recipe']['residual_block_sha256']]
  assert value['block_original']==block and instant(block['available_at'])<=ORIGIN
  for point,central,residual in zip(value['rows'],c['forcing']['rows'],block['residuals']):
   assert (point['tempF']-central['tempF'])/1.8==pytest.approx(residual['temperature_c'])
   assert (point['windMph']-central['windMph'])*.44704==pytest.approx(residual['wind_m_s'])
   assert point['radiationWm2']-central['radiationWm2']==pytest.approx(residual['ghi_wm2'])
  assert api().validate_scenario(scenario)==value
 assert [b.content for b in blocks]==before


@pytest.mark.parametrize('damage',['future_labels','sparse_dates','cohort','phase'])
def test_joint_template_failures_withhold_candidates_without_fabricating_independence(damage):
 c=context();blocks=residual_blocks(count=7 if damage=='sparse_dates' else 10,late=damage=='future_labels');cohort='f'*64 if damage=='cohort' else 'c'*64
 if damage=='phase':
  c['forcing']=make_native_component_forecast(snapshot(hours=8),origin=ORIGIN+timedelta(hours=1),horizon_hours=3,available_by=ORIGIN+timedelta(hours=1),site=SITE)
 value=api().joint_scenarios(**c,blocks=blocks,cohort_sha256=cohort)
 assert value['status']=='insufficient_evidence' and value['scenarios']==[]
 assert value['support']['local_dates']<8 and value['probability_claim'] is False


def test_reported_proxy_cannot_be_silently_treated_as_physical_joint_solar_residual():
 with pytest.raises(ValueError,match='physical'):
  residual_blocks(count=1,proxy=True)


def test_resealed_joint_residual_or_missing_original_observation_cannot_replay():
 block=residual_blocks(count=1)[0].to_dict();block['residuals'][0]['temperature_c']+=1
 block['block_sha256']=identity({k:v for k,v in block.items() if k!='block_sha256'})
 with pytest.raises(ValueError):api().ResidualBlock(canonical(block))
 block=residual_blocks(count=1)[0].to_dict();block['observations'].pop();block['block_sha256']=identity({k:v for k,v in block.items() if k!='block_sha256'})
 with pytest.raises(ValueError):api().ResidualBlock(canonical(block))


def test_compatible_component_response_projects_indoor_air_without_reusing_proxy_weights():
 from test_thermal_solar_experiment import response_rows
 from weather_learning.thermal_solar_experiment import fit_response,predict_response,component_features
 protocol=json.loads((ROOT/'docs/operations/weathernext3-capabilities/evaluation-protocol.json').read_bytes())
 rows=response_rows()
 for row in rows:
  for name in ['origin','target_at']:row[name]=(instant(row[name])-timedelta(days=14)).isoformat()
  row['available_at']=(instant(row['target_at'])+timedelta(minutes=5)).isoformat()
  row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
 model=fit_response(rows,method='native',cutoff=ORIGIN-timedelta(days=1),fitted_at=ORIGIN-timedelta(minutes=5),policy=THERMAL_POLICY,protocol=protocol)
 assert model is not None
 scenario=cases(hours=1)[2];state=dict(air_f=70.,north_wall_f=72.,indoor_shade_closed=0.,outdoor_shade_present=0.,vent_open=1.,passive_fit_allowed=True)
 ctx=dict(schema='earthship-component-thermal-scenario-context/v1',model=model,policy=THERMAL_POLICY,origin_state=state,available_at=(ORIGIN-timedelta(minutes=5)).isoformat())
 positions=geometry(start=ORIGIN,count=12)
 out=api().propagate(scenario,positions=positions,array=ARRAY,horizon_profile=HORIZON,initial_soc_pct=80.,nominal_bank_kwh=10.,load_ac_w=500.,thermal_context=ctx)
 features=component_features(forcing=scenario,positions=positions,origin_state=state,origin=ORIGIN,horizon_hours=1,horizon_profile=HORIZON,policy=THERMAL_POLICY)
 assert out['thermal']['indoor_air_f']==predict_response(model,features=features['features'],origin_air_f=70.,policy=THERMAL_POLICY)
 assert out['thermal']['uses_legacy_proxy_coefficients'] is False and out['thermal']['north_wall_f'] is None
 assert out['probability_claim'] is False



@pytest.mark.parametrize('observed_wind,expected_cases',[(70.,6),(100.,0)])
def test_joint_reconciliation_refuses_wind_outside_shared_component_model_domain(observed_wind,expected_cases):
 c=context();c['forcing']=make_native_component_forecast(snapshot(hours=6,wind_m_s=80*.44704),origin=ORIGIN,horizon_hours=3,available_by=ORIGIN,site=SITE)
 blocks=[]
 for original in residual_blocks():
  value=original.to_dict()
  for observation in value['observations']:observation['wind_m_s']=observed_wind
  blocks.append(api().make_residual_block(forcing=value['original_forecast'],observations=value['observations'],cohort_sha256='c'*64))
 result=api().joint_scenarios(**c,blocks=blocks,cohort_sha256='c'*64)
 assert len(result['scenarios'])==expected_cases
 if not expected_cases:
  assert result['status']=='insufficient_evidence' and result['reason']=='all_constructed_trajectories_refused'
  assert result['construction_refusals']=={'constructed_trajectory_outside_supported_domain':6}
 else:
  arguments=dict(positions=geometry(start=ORIGIN,count=36),array=ARRAY,horizon_profile=HORIZON,initial_soc_pct=80.,nominal_bank_kwh=10.,load_ac_w=500.,thermal_context=None)
  projection=api().propagate(result['scenarios'][0],**arguments)
  assert projection['pv']['potential_pv_kwh']>=0
  assert all(0<=row['windMph']<=250 for row in result['scenarios'][0].to_dict()['rows'])
