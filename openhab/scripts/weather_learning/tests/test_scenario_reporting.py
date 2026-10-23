"""Advisory report originals are private, bounded and replayed without a new fit."""
from copy import deepcopy
from datetime import timedelta
import importlib,json,socket
import pytest
from test_household_weather_scenarios import context,cases,residual_blocks,ORIGIN,ARRAY,HORIZON
from native_solar_fixtures import geometry
from weather_learning.contracts import canonical,identity
from weather_learning.shadow import ShadowStore


def api():return importlib.import_module('weather_learning.scenario_reporting')
def args():
 return dict(**context(hours=1),blocks=[],cohort_sha256='c'*64,household_inputs=dict(positions=geometry(start=ORIGIN,count=12),array=ARRAY,horizon_profile=HORIZON,initial_soc_pct=80.,nominal_bank_kwh=10.,load_ac_w=500.,thermal_context=None),prepared_at=ORIGIN+timedelta(seconds=1))


def test_original_report_retains_inputs_source_and_outputs_without_probability_claims():
 value=api().prepare_report(**args());original=value.to_dict()
 assert len(original['output']['stress'])==3 and original['output']['joint']['status']=='insufficient_evidence'
 assert original['inputs']['forcing']==args()['forcing']
 assert original['runtime']['source_package'] and original['runtime']['environment']['binary_sha256s']
 assert api().replay_report(value.content).content==value.content
 view=api().public_view(value)
 assert view['source_forecast_sha256']==args()['forcing']['forecast_sha256']
 assert len(view['stress'])==3 and view['joint']['scenario_count']==0
 assert view['probability_claim'] is view['automatic_actuation'] is False
 assert all(word not in canonical(view) for word in [b'source_original',b'bank_config_raw',b'/home/',b'/tmp/'])
 assert view['stress'][0]['minimum_nominal_soc_pct'] is not None


@pytest.mark.parametrize('damage',['output','inputs','sources','environment'])
def test_resealed_report_changes_cannot_bypass_current_math_and_original_source(damage):
 original=api().prepare_report(**args()).to_dict()
 if damage=='output':original['output']['stress'][0]['minimum_nominal_soc_pct']=0
 elif damage=='inputs':original['inputs']['household_inputs']['load_ac_w']+=100
 elif damage=='sources':original['runtime']['source_package'][next(iter(original['runtime']['source_package']))]='changed'
 else:original['runtime']['environment']['numpy']='different'
 original['report_sha256']=identity({k:v for k,v in original.items() if k!='report_sha256'})
 with pytest.raises(ValueError):api().replay_report(canonical(original))


def test_explicit_retention_preserves_original_and_current_advisory_cache(tmp_path):
 value=api().prepare_report(**args());root=tmp_path/'state'
 assert not root.exists()
 saved=api().retain_report(root,value,clock=lambda:ORIGIN+timedelta(seconds=2))
 assert saved['retained'] and saved['cached']
 original=json.loads((root/'scenario-reports'/(value.to_dict()['report_sha256']+'.json')).read_bytes())
 assert original==value.to_dict()
 cached=json.loads((root/'scenario-advisory.json').read_bytes());assert cached==api().public_view(value)
 before={p.name:p.read_bytes() for p in (root/'scenario-reports').glob('*.json')}
 api().retain_report(root,value,clock=lambda:ORIGIN+timedelta(seconds=3))
 assert {p.name:p.read_bytes() for p in (root/'scenario-reports').glob('*.json')}==before
 assert not (root/'current-model.json').exists()


def test_expired_report_can_be_retained_for_replay_but_cannot_refresh_public_cache(tmp_path):
 value=api().prepare_report(**args());root=tmp_path/'state';r=api().retain_report(root,value,clock=lambda:ORIGIN+timedelta(days=1))
 assert r['retained'] and not r['cached'] and not (root/'scenario-advisory.json').exists()


def test_new_report_namespace_counts_against_existing_shared_immutable_capacity(tmp_path):
 state=ShadowStore(tmp_path/'state');directory=state.root/'scenario-reports';directory.mkdir(mode=0o700)
 with (directory/('a'*64+'.json')).open('wb') as f:f.truncate(2*1024**3)
 value=api().prepare_report(**args())
 with pytest.raises(ValueError,match='capacity'):api().retain_report(state.root,value,clock=lambda:ORIGIN+timedelta(seconds=2))
 assert not (state.root/'scenario-advisory.json').exists()


def test_reporting_opens_no_network_or_fitting_path(monkeypatch):
 import scipy.optimize
 def forbidden(*a,**kw):pytest.fail('reporting opened a fitting or network path')
 monkeypatch.setattr(socket,'create_connection',forbidden);monkeypatch.setattr(scipy.optimize,'lsq_linear',forbidden);monkeypatch.setattr(scipy.optimize,'minimize',forbidden)
 value=api().prepare_report(**args());assert api().replay_report(value.content).content==value.content


def test_later_household_assessment_uses_retained_predictions_and_original_qualified_targets():
 from test_household_scenario_outcomes import inputs as target_inputs,END,ASSESSED
 from weather_learning.scenario_household import household_targets
 a=args();a['household_inputs']['initial_soc_pct']=70.;report=api().prepare_report(**a)
 targets=household_targets(**target_inputs());before=report.content
 score=api().assess_report(report,household_targets=targets,weather_observations=None,assessed_at=ASSESSED)
 assert score['original_report_sha256']==report.to_dict()['report_sha256']
 assert score['household']['support']['scenarios']==3 and score['household']['support']['forecast_origins']==1
 assert score['weather']['status']=='unavailable' and score['probability_claim'] is False
 assert api().replay_assessment(canonical(score),report=report)==score
 assert report.content==before


@pytest.mark.parametrize('damage',['score','target','future'])
def test_later_assessment_rederives_errors_and_refuses_future_labels(damage):
 from test_household_scenario_outcomes import inputs as target_inputs,ASSESSED
 from weather_learning.scenario_household import household_targets
 a=args();a['household_inputs']['initial_soc_pct']=70.;report=api().prepare_report(**a);targets=household_targets(**target_inputs())
 if damage=='future':
  with pytest.raises(ValueError):api().assess_report(report,household_targets=targets,weather_observations=None,assessed_at=ASSESSED-timedelta(minutes=1))
  return
 score=api().assess_report(report,household_targets=targets,weather_observations=None,assessed_at=ASSESSED)
 if damage=='score':score['household']['scenarios'][0]['errors']['captured_controller_dc_kwh']=0
 else:score['inputs']['household_targets']['targets']['captured_controller_dc_kwh']['value']=0
 score['assessment_sha256']=identity({k:v for k,v in score.items() if k!='assessment_sha256'})
 with pytest.raises(ValueError):api().replay_assessment(canonical(score),report=report)


def test_public_case_exposes_actual_total_only_fallback_instead_of_only_native_method_name():
 from native_solar_fixtures import snapshot,SITE
 from weather_learning.native_forecast import make_native_component_forecast
 a=args();a['forcing']=make_native_component_forecast(snapshot(hours=4,direct_j=None),origin=ORIGIN,horizon_hours=1,available_by=ORIGIN,site=SITE)
 view=api().public_view(api().prepare_report(**a))
 for row in view['stress']:
  assert row['solar_source_support']['native_hours']==0
  assert row['solar_source_support']['fallback_hours']==1
  assert row['solar_source_support']['fallback_reasons']['native_direct_unavailable']==1



def test_assessment_can_retain_and_replay_a_multi_receipt_outcome_over_16_mib():
 from test_household_scenario_outcomes import padded_energy_inputs
 from weather_learning.scenario_household import household_targets
 target_inputs=padded_energy_inputs(3,2400,3000);targets=household_targets(**target_inputs)
 a=args();a.update(context(hours=3));a['household_inputs'].update(initial_soc_pct=70.,positions=geometry(start=ORIGIN,count=36));report=api().prepare_report(**a)
 result=api().assess_report(report,household_targets=targets,assessed_at=target_inputs['assessed_at'])
 assert len(canonical(result))>16*1024**2
 assert result['household']['scenarios'][0]['actual']['captured_controller_dc_kwh']==pytest.approx(3.)
 assert api().replay_assessment(canonical(result),report=report)==result
