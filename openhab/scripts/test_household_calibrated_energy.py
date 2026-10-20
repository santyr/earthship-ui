from datetime import timedelta
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import pytest
from household.codec import canonical,identity
from household.control_contracts import instant
from test_household_energy_forecast import fixture,originals


def calibration(tmp_path,energy):
 from weather_learning.pv_directional_calibration import fit_directional
 issue=instant(energy['output']['array_pv']['origin']);rows=[]
 for day in range(8):
  for az in range(0,360,45):
   for minute in range(8):
    start=issue-timedelta(days=20-day)+timedelta(minutes=minute)
    row=dict(start=start.isoformat(),end=(start+timedelta(minutes=1)).isoformat(),origin=(start-timedelta(hours=1)).isoformat(),baseline_w=1000.,outcome_w=800.,azimuth_degrees=az+1.,lead_hours=2.,forecast_sha256='a'*64,energy_source_sha256='b'*64,potential_proxy_eligible=True)
    row['pair_sha256']=identity(row);rows.append(row)
 model=fit_directional(rows,cutoff=issue-timedelta(days=8),trained_at=issue-timedelta(hours=1))
 names=('pv_directional_calibration.py','pv_calibration.py','contracts.py','weights.py');scripts=Path(__file__).parent
 runtime={'openhab/scripts/weather_learning/'+n:sha256((scripts/'weather_learning'/n).read_bytes()).hexdigest() for n in names}
 report=dict(selected=True,model_sha256='a'*64,holdout_end=(issue-timedelta(days=1)).isoformat(),independent_target_days=5,baseline_mae_w=10.,candidate_mae_w=8.,prospective_score=False,physical_calibration_qualified=False,automatic_actuation=False);report['report_sha256']=identity(report)
 value=dict(schema='earthship-historical-pv-directional-experiment/v1',created_at=(issue-timedelta(hours=1)).isoformat(),final_model=model,training_model_sha256='a'*64,report=report,runtime_manifest=runtime,system_raw=energy['inputs']['system_source']['raw'],horizon_raw=energy['inputs']['horizon_source']['raw'],automatic_actuation=False);value['receipt_sha256']=identity(value)
 path=tmp_path/'calibration.json';path.write_bytes(canonical(value));path.chmod(0o600);return path


def test_calibrated_scenario_replays_same_issue_and_retains_originals(tmp_path,monkeypatch,originals):
 from household_calibrated_energy import seal,replay,runtime_manifest
 api,args,plan=fixture(tmp_path,monkeypatch,originals);energy=api.seal_energy_forecast(**args);path=calibration(tmp_path,energy);before=canonical(energy)
 value=seal(energy=energy,plan=plan,profiled=None,calibration_path=path,now=args['now'])
 assert canonical(energy)==before
 assert value['inputs']['original_energy_document_sha256']==identity(energy)
 assert value['output']['calibrated_potential_kwh']<energy['output']['array_pv']['potential_pv_kwh']
 assert value['output']['constant_load_storage']['status']=='conditional_nominal_simulation'
 assert value['output']['automatic_actuation'] is False
 assert replay(value,energy=energy,plan=plan,profiled=None)==value
 value['output']['calibrated_potential_kwh']+=1;value['receipt_sha256']=identity({k:v for k,v in value.items() if k!='receipt_sha256'})
 with pytest.raises(ValueError):replay(value,energy=energy,plan=plan,profiled=None)


def test_adjustment_uses_the_original_right_endpoint_for_split_steps():
 from household_calibrated_energy import adjust_steps
 from test_weather_directional_pv import rows
 from weather_learning.pv_directional_calibration import fit_directional
 from test_household_pv_window import START
 origin=START+timedelta(days=20);model=fit_directional(rows(),cutoff=START+timedelta(days=12),trained_at=origin)
 steps=[{'start':origin.isoformat(),'end':(origin+timedelta(minutes=2)).isoformat(),'potential_pv_kwh':.02},{'start':(origin+timedelta(minutes=2)).isoformat(),'end':(origin+timedelta(minutes=5)).isoformat(),'potential_pv_kwh':.03}]
 result=adjust_steps(steps,positions=[{'at':(origin+timedelta(minutes=5)).isoformat(),'azimuth_degrees':110.,'elevation_degrees':30.}],model=model,origin=origin)
 assert result[0]['potential_pv_kwh']<.02
 assert result[1]['potential_pv_kwh']/result[0]['potential_pv_kwh']==pytest.approx(1.5)
 assert steps[0]['potential_pv_kwh']==.02
 with pytest.raises(ValueError,match='geometry'):adjust_steps(steps,positions=[],model=model,origin=origin)


def test_learned_storage_initial_conditions_do_not_require_an_instantaneous_load(tmp_path,monkeypatch,originals):
 from household_calibrated_energy import storage_inputs
 from household.model_snapshot import restore_snapshot
 from types import SimpleNamespace
 api,args,plan=fixture(tmp_path,monkeypatch,originals);snapshot=restore_snapshot(plan['inputs']['snapshot'],plan['inputs']['source_contexts']);doc=deepcopy(snapshot.to_dict());origin=instant(doc['as_of'])
 doc['domains']['energy']['estimated_load_w'].update(value=None,reason='missing',evidence=None)
 original=SimpleNamespace(to_dict=lambda:doc,energy_configuration=snapshot.energy_configuration)
 result=storage_inputs(original,topology_source=args['topology_source'],origin=origin)
 assert result['reason'] is None
 assert result['current_load_w'] is None
 assert result['current_load_reason']=='required_source_unavailable'
 doc['domains']['energy']['battery_soc']['evidence']['valid_until']=(origin-timedelta(seconds=1)).isoformat()
 assert storage_inputs(original,topology_source=args['topology_source'],origin=origin)['reason']=='required_source_expired'
