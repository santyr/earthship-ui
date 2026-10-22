"""Native sensitivity reuses original air/wall model and proves central parity."""
from copy import deepcopy
from datetime import timedelta
import importlib
import pytest
from test_native_thermal_artifact import originals
from test_native_thermal_forecast import context as native_case,ISSUE
from weather_learning.contracts import canonical,identity,instant
from weather_learning.config import Site
from weather_learning.native_forecast import _snapshot,_decode,make_native_component_forecast
from test_household_weather_scenarios import POLICY


def api():return importlib.import_module('weather_learning.native_scenarios')
def setup(tmp_path,monkeypatch,originals):
 import native_thermal_forecast as native
 c,inputs,kw=native_case(tmp_path,monkeypatch,originals)
 capture=native.build_capture(c,inputs,**kw)
 # Synthetic native fixtures supply original-shaped runtime/geometry. This
 # injection keeps numerical tests separate from the real producer-source probe.
 monkeypatch.setattr(api(),'current_native_runtime',lambda **kw:capture['candidate']['runtime'])
 source=_snapshot(_decode(inputs['forecast']['source_original']))
 forcing=make_native_component_forecast(source,origin=ISSUE,available_by=instant(inputs['forecast']['available_by']),horizon_hours=24,site=Site(**inputs['forecast']['site']))
 positions=[dict(at=p['at'],elevation_degrees=p['elevation_degrees'],azimuth_degrees=p['azimuth_degrees']) for cache in capture['geometry']['caches'] for p in cache['positions']]
 ctx=api().prepare_native_context(capture,runtime=kw['runtime'],expected_capture_sha256=capture['capture_sha256'],expected_artifact_sha256=c['artifact_sha256'])
 from weather_learning.scenarios import stress_cases
 return capture,ctx,stress_cases(forcing=forcing,policy=POLICY),positions,kw


def test_native_central_reproduces_all_original_hourly_air_and_north_wall_states(tmp_path,monkeypatch,originals):
 capture,ctx,scenarios,positions,kw=setup(tmp_path,monkeypatch,originals)
 result=api().project_native_scenario(scenarios[0],ctx,positions=positions)
 assert len(result['trajectory'])==24
 for actual,original in zip(result['trajectory'],capture['output']['trajectory']):
  assert actual['at']==original['at']
  assert actual['air_f']==pytest.approx(original['air_f'],abs=1e-9)
  assert actual['mass_f']==pytest.approx(original['mass_f'],abs=1e-9)
 assert result['indoor_air_f']==result['trajectory'][-1]['air_f']
 assert result['north_wall_f']==result['trajectory'][-1]['mass_f']
 assert result['model_sha256']==capture['candidate']['artifact_sha256']
 assert result['probability_claim'] is result['automatic_actuation'] is False


def test_warm_and_reduced_solar_use_fixed_original_coefficients_actions_and_initial_state(tmp_path,monkeypatch,originals):
 capture,ctx,scenarios,positions,kw=setup(tmp_path,monkeypatch,originals);before=ctx.to_dict()
 output=[api().project_native_scenario(s,ctx,positions=positions) for s in scenarios]
 assert output[2]['indoor_air_f']>output[0]['indoor_air_f']
 assert output[2]['north_wall_f']>output[0]['north_wall_f']
 assert output[1]['indoor_air_f']<=output[0]['indoor_air_f']
 assert all(o['initial']==capture['output']['initial'] and o['origin_actions']==capture['output']['origin_actions'] for o in output)
 assert ctx.to_dict()==before
 assert api().restore_native_context(before).to_dict()==before


@pytest.mark.parametrize('damage',['coefficients','output','geometry','weather'])
def test_resealed_native_capture_cannot_change_model_or_original_inputs(tmp_path,monkeypatch,originals,damage):
 capture,ctx,scenarios,positions,kw=setup(tmp_path,monkeypatch,originals);capture=deepcopy(capture)
 if damage=='coefficients':capture['candidate']['fit']['coefficients'][5]+=.01
 elif damage=='output':capture['output']['trajectory'][0]['air_f']+=1
 elif damage=='geometry':capture['geometry']['caches'][0]['positions'][0]['elevation_degrees']+=1
 else:capture['inputs']['forecast']['rows'][1]['tempF']+=1
 capture['capture_sha256']=identity({k:v for k,v in capture.items() if k!='capture_sha256'})
 with pytest.raises(ValueError):api().prepare_native_context(capture,runtime=kw['runtime'],expected_capture_sha256=capture['capture_sha256'],expected_artifact_sha256=capture['candidate']['artifact_sha256'])


def test_native_model_rejects_geometry_replacement_and_other_original_weather(tmp_path,monkeypatch,originals):
 capture,ctx,scenarios,positions,kw=setup(tmp_path,monkeypatch,originals)
 damaged=deepcopy(positions);damaged[0]['azimuth_degrees']+=1
 with pytest.raises(ValueError):api().project_native_scenario(scenarios[0],ctx,positions=damaged)
 from test_household_weather_scenarios import cases
 with pytest.raises(ValueError):api().project_native_scenario(cases(hours=1)[0],ctx,positions=positions)


def test_native_context_refuses_changed_current_producer_identity(tmp_path,monkeypatch,originals):
 capture,ctx,scenarios,positions,kw=setup(tmp_path,monkeypatch,originals)
 wrong=deepcopy(kw['runtime']);wrong['native_source_manifest']['openhab/scripts/native_thermal_forecast.py']='f'*64
 wrong['native_code_revision']=identity(wrong['native_source_manifest'])
 monkeypatch.setattr(api(),'current_native_runtime',lambda **kw:wrong)
 with pytest.raises(ValueError):api().restore_native_context(ctx.to_dict())


def test_original_conditioning_math_is_reapplied_without_relabeling_changed_rows_as_originals():
 from test_thermal_weather_conditioning import context as conditioning,ISSUE as issue
 from household.thermal_weather_conditioning import apply_conditioning
 proof=conditioning();actions=dict(indoor_shade_closed=0.,outdoor_shade_present=1.,vent_open=0.)
 from thermal_model.installed_shade_dynamics import InstalledShadeForcing
 from dataclasses import replace
 at=issue+timedelta(minutes=5);left,right=map(instant,[r['at'] for r in proof['rows']]);fraction=(at-left)/(right-left)
 raw=(InstalledShadeForcing(at,50.+fraction*1.8,500.,**actions),);capture=dict(issued_at=issue.isoformat(),inputs_available_at=(issue-timedelta(seconds=1)).isoformat(),weather_conditioning=proof)
 baseline=apply_conditioning(raw,proof,issue=issue,available=issue-timedelta(seconds=1),initial_outdoor_f=53.6)
 actual=api()._condition(raw,proof['rows'],capture,53.6)
 assert actual==baseline
 changed=deepcopy(proof['rows'])
 for row in changed:row['tempF']+=5.4;row['radiationWm2']*=1.2
 modified=tuple(replace(r,outdoor_f=r.outdoor_f+5.4,radiation_wm2=r.radiation_wm2*1.2) for r in raw);result=api()._condition(modified,changed,capture,53.6)
 fraction=(result[0].at-issue)/(instant(changed[-1]['at'])-issue)
 assert result[0].outdoor_f==pytest.approx(53.6+fraction*(60.8-53.6))
 assert result[0].radiation_wm2==pytest.approx(500.)
 assert proof==capture['weather_conditioning'] and proof['rows']!=changed


def test_common_scenario_projection_accepts_verified_native_context_and_keeps_wall_output(tmp_path,monkeypatch,originals):
 from weather_learning.scenarios import propagate
 from native_solar_fixtures import ARRAY,HORIZON
 capture,ctx,scenarios,positions,kw=setup(tmp_path,monkeypatch,originals)
 projection=propagate(scenarios[0],positions=positions,array=ARRAY,horizon_profile=HORIZON,initial_soc_pct=80.,nominal_bank_kwh=10.,load_ac_w=500.,thermal_context=ctx)
 assert projection['thermal']['north_wall_f']==pytest.approx(capture['output']['trajectory'][-1]['mass_f'],abs=1e-9)
 assert projection['thermal']['indoor_air_f']==pytest.approx(capture['output']['trajectory'][-1]['air_f'],abs=1e-9)


def test_original_report_serializes_native_context_once_and_exposes_hourly_air_wall_trajectory(tmp_path,monkeypatch,originals):
 from weather_learning.scenario_reporting import prepare_report,replay_report,public_view
 from native_solar_fixtures import ARRAY,HORIZON
 capture,ctx,scenarios,positions,kw=setup(tmp_path,monkeypatch,originals)
 report=prepare_report(forcing=scenarios[0].to_dict()['original_forecast'],policy=POLICY,blocks=[],cohort_sha256='c'*64,prepared_at=ISSUE+timedelta(seconds=3),household_inputs=dict(positions=positions,array=ARRAY,horizon_profile=HORIZON,initial_soc_pct=80.,nominal_bank_kwh=10.,load_ac_w=500.,thermal_context=ctx.to_dict()))
 assert replay_report(report.content).content==report.content
 view=public_view(report);assert len(view['stress'][0]['thermal_trajectory'])==24
 assert view['stress'][0]['thermal_method']==capture['output']['model_rule']
 assert view['stress'][0]['north_wall_f'] is not None
 assert b'native_source_paths' not in canonical(view) and b'/home/' not in canonical(view)


def test_original_producer_scalar_forcing_does_not_import_new_component_PV_package(monkeypatch):
 import builtins
 module=api();original_import=builtins.__import__
 def original_packages_only(name,*args,**kwargs):
  if name=='household_pv_components':raise ModuleNotFoundError('original native producer predates the component PV package')
  return original_import(name,*args,**kwargs)
 monkeypatch.setattr(builtins,'__import__',original_packages_only)
 start=ISSUE.replace(minute=0,second=0,microsecond=0);actions=dict(indoor_shade_closed=0.,outdoor_shade_present=1.,vent_open=0.)
 rows=[dict(at=(start+timedelta(hours=i)).isoformat(),tempF=50.+i*2,radiationWm2=500.,windMph=4.) for i in range(2)]
 forcing=module._forcings(rows,start,1,actions)
 assert len(forcing)==12 and forcing[-1].outdoor_f==52.
 from test_thermal_weather_conditioning import context as conditioning,ISSUE as issue
 from thermal_model.installed_shade_dynamics import InstalledShadeForcing
 from household.thermal_weather_conditioning import apply_conditioning
 proof=conditioning();raw=(InstalledShadeForcing(issue+timedelta(minutes=5),50.3075,500.,**actions),)
 capture=dict(issued_at=issue.isoformat(),inputs_available_at=(issue-timedelta(seconds=1)).isoformat(),weather_conditioning=proof)
 assert module._condition(raw,proof['rows'],capture,53.6)==apply_conditioning(raw,proof,issue=issue,available=issue-timedelta(seconds=1),initial_outdoor_f=53.6)


@pytest.mark.parametrize('rule,expected_radiation',[('original_ending_hour_right_selector/v1',1200.),('original_point_radiation_linear/v1',602.5)])
def test_legacy_original_forcing_versions_preserve_boundary_semantics_without_new_mean_kernel(monkeypatch,rule,expected_radiation):
 from thermal_model import installed_shade_origin
 module=api();monkeypatch.setattr(module,'_forcing_rule',lambda:rule,raising=False)
 monkeypatch.delattr(installed_shade_origin,'ending_hour_mean')
 start=ISSUE.replace(minute=0,second=0,microsecond=0);origin=start+timedelta(minutes=55,seconds=15)
 rows=[dict(at=(start+timedelta(hours=i)).isoformat(),tempF=50.+2*i,radiationWm2=600.*i,windMph=4.) for i in range(3)]
 actions=dict(indoor_shade_closed=0.,outdoor_shade_present=1.,vent_open=0.)
 forcing=module._forcings(rows,origin,1,actions)
 assert forcing[0].radiation_wm2==pytest.approx(expected_radiation)
 assert forcing[0].outdoor_f==pytest.approx(52.+2*.25/60)
