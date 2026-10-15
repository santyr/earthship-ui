"""PV/load storage forecasts use matched original SoC outcomes and references."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import importlib
import pytest
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from test_household_native_weather import originals
from test_household_energy_forecast import fixture
from test_forecast_pre_dusk import evidence
from household.battery_outcomes import build_endpoint_source


def context(tmp_path,monkeypatch,originals):
    forecast_api,args,plan=fixture(tmp_path,monkeypatch,originals);forecast=forecast_api.seal_energy_forecast(**args)
    issue=instant(forecast['output']['array_pv']['origin']);target=issue+timedelta(hours=1);now=target+timedelta(minutes=5,seconds=2)
    epoch=plan['inputs']['snapshot']['domains']['energy']['battery_soc']['evidence']['source_epoch']
    raw=loads(evidence(target-timedelta(seconds=20),soc=95));raw['streamEpoch']=epoch
    packet=build_endpoint_source(rows=[(target-timedelta(seconds=2),canonical(raw).decode())],target_at=target,requested_at=now-timedelta(seconds=2),received_at=now-timedelta(seconds=1),item_id=613)
    api=importlib.import_module('household_solar_outcomes')
    return api,dict(forecast_receipt=forecast,plan_receipt=plan,endpoint_sources={'1':packet},assessed_at=now,
        forecast_runtime_manifest=forecast_api.forecast_runtime_manifest(),outcome_runtime_manifest=api.energy_outcome_runtime_manifest())


def test_new_scenario_compares_the_same_atomic_endpoint_and_original_references(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals);score=api.seal_energy_outcomes(**args);row=score['output']['by_horizon']['1']
    original=args['forecast_receipt']['output']['nominal_storage']['trajectory'][0]['nominal_soc_pct']
    assert row['status']=='scored' and row['actual_soc_pct']==95
    assert row['predictions_soc_pct']['pv_load_scenario']==original
    assert row['errors_soc_pct']['pv_load_scenario']==pytest.approx(original-95)
    assert row['predictions_soc_pct']['hold_soc']==100 and row['errors_soc_pct']['hold_soc']==5
    assert score['output']['by_horizon']['6']['status']=='not_mature'
    assert score['output']['pv_energy_accuracy']=='unavailable_unmatched_meter_scope'
    assert score['output']['automatic_actuation'] is False
    replay={k:v for k,v in args.items() if k not in ('endpoint_sources','assessed_at')}
    assert api.replay_energy_outcomes(score,**replay)==score


@pytest.mark.parametrize('damage',['latest_barrier','epoch','expired','immature','changed_forecast','changed_output'])
def test_unqualified_or_changed_evidence_never_becomes_an_accuracy_pair(tmp_path,monkeypatch,originals,damage):
    api,args=context(tmp_path,monkeypatch,originals)
    if damage in ('changed_forecast','changed_output'):
        score=api.seal_energy_outcomes(**args)
        if damage=='changed_output':score['output']['by_horizon']['1']['errors_soc_pct']['hold_soc']=0
        else:args['forecast_receipt']=deepcopy(args['forecast_receipt']);args['forecast_receipt']['output']['nominal_storage']['trajectory'][0]['nominal_soc_pct']=0
        score['receipt_sha256']=identity({k:v for k,v in score.items() if k!='receipt_sha256'})
        with pytest.raises(ValueError):api.replay_energy_outcomes(score,**{k:v for k,v in args.items() if k not in ('endpoint_sources','assessed_at')})
        return
    if damage=='immature':
        args['assessed_at']-=timedelta(minutes=1)
        with pytest.raises(ValueError):api.seal_energy_outcomes(**args)
        return
    source=args['endpoint_sources']['1'];target=instant(source['target_at']);raw=loads(source['rows'][0][1])
    if damage=='epoch':raw['streamEpoch']='00000000-0000-0000-0000-000000000002'
    if damage=='expired':raw=loads(evidence(target-timedelta(seconds=120),soc=95));raw['streamEpoch']=args['plan_receipt']['inputs']['snapshot']['domains']['energy']['battery_soc']['evidence']['source_epoch']
    args['endpoint_sources']['1']=build_endpoint_source(rows=[(target-timedelta(seconds=2),None if damage=='latest_barrier' else canonical(raw).decode())],
        target_at=target,requested_at=instant(source['requested_at']),received_at=instant(source['received_at']),item_id=613)
    row=api.seal_energy_outcomes(**args)['output']['by_horizon']['1']
    assert row['status']=='source_unavailable' and row['actual_soc_pct'] is None and row['errors_soc_pct'] is None


def test_report_matches_pairs_deduplicates_hours_and_reports_real_day_counts(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals);score=api.seal_energy_outcomes(**args)
    report=api.build_energy_performance([score,score],cohort=score['output']['cohort'],generated_at=args['assessed_at'],next_mature_at=None)
    row=report['by_horizon']['1'];assert row['count']==1 and row['attempted_count']==1 and row['unique_origin_days']==1
    assert row['mae_soc_pct']['hold_soc']==5 and row['rmse_soc_pct']['hold_soc']==5
    assert row['rmse_soc_pct']['pv_load_scenario']==pytest.approx(abs(score['output']['by_horizon']['1']['errors_soc_pct']['pv_load_scenario']))
    assert report['by_horizon']['6']['count']==0 and report['by_horizon']['6']['mae_soc_pct'] is None
    assert report['graduated'] is False and report['pv_energy_accuracy']=='unavailable_unmatched_meter_scope'


def test_original_energy_cache_contains_only_curated_forecast_values(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals)
    state=importlib.import_module('household_energy_state');forecast=args['forecast_receipt'];at=instant(forecast['inputs']['assessed_at'])
    view=state.project_energy_observation(forecast,plan_receipt=args['plan_receipt'],generated_at=at)
    assert len(view['trajectory'])==24 and view['potential_pv_24h_kwh']>0
    assert view['captured_pv_24h_kwh']==forecast['output']['nominal_storage']['modeled_captured_pv_kwh']
    assert view['household_ac_load_w_assumption']==1000 and view['physical_calibration_qualified'] is False
    text=canonical(view).decode()
    assert 'runtime_manifest' not in text and 'source_contexts' not in text and '/home/' not in text and 'available_at' not in text
    assert instant(view['valid_until'])==instant(view['issued_at'])+timedelta(minutes=15)
    assert view['issued_at']==forecast['output']['array_pv']['origin']


@pytest.mark.parametrize('source',['household_solar_score.py','household_energy_state.py'])
def test_resealed_runtime_cannot_omit_executing_producer_or_publication_source(tmp_path,monkeypatch,originals,source):
    api,args=context(tmp_path,monkeypatch,originals);args['outcome_runtime_manifest'].pop('openhab/scripts/'+source)
    with pytest.raises(ValueError):api.seal_energy_outcomes(**args)


def test_public_parsers_accept_actual_curated_backend_forecast_and_matched_report(tmp_path,monkeypatch,originals):
    import subprocess,json,shutil
    from pathlib import Path
    from household_energy_state import project_energy_observation
    api,args=context(tmp_path,monkeypatch,originals);score=api.seal_energy_outcomes(**args)
    forecast=args['forecast_receipt'];view=project_energy_observation(forecast,plan_receipt=args['plan_receipt'],generated_at=instant(forecast['inputs']['assessed_at']))
    report=api.build_energy_performance([score],cohort=score['output']['cohort'],generated_at=args['assessed_at'],next_mature_at=None)
    script="import fs from 'node:fs';import {parseEnergyObservation,parseEnergyPerformance} from './src/lib/household/energyObservation.js';const d=JSON.parse(fs.readFileSync(0,'utf8'));if(!parseEnergyObservation(JSON.stringify(d.view),{nowMs:Date.parse(d.view.generated_at)})||!parseEnergyPerformance(JSON.stringify(d.report),{nowMs:Date.parse(d.report.generated_at)}))process.exit(1);"
    node=shutil.which('node')
    if node is None:pytest.skip('Node is required for the cross-language public contract')
    result=subprocess.run([node,'--v8-pool-size=2','--input-type=module','-e',script],cwd=Path(__file__).resolve().parents[2],input=json.dumps(dict(view=view,report=report)),capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr


def test_supplied_endpoint_corruption_refuses_even_when_solar_scenario_is_unavailable(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals)
    from household_energy_forecast import seal_energy_forecast
    inputs=args['forecast_receipt']['inputs']
    args['forecast_receipt']=seal_energy_forecast(plan_receipt=args['plan_receipt'],system_source=None,horizon_source=inputs['horizon_source'],topology_source=inputs['topology_source'],now=instant(inputs['assessed_at']),runtime_manifest=args['forecast_runtime_manifest'])
    args['endpoint_sources']['1']['source_sha256']='f'*64
    with pytest.raises(ValueError):api.seal_energy_outcomes(**args)


def test_resealed_plan_cannot_supply_an_unreplayed_constant_power_reference(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals)
    from household_energy_forecast import seal_energy_forecast
    plan=args['plan_receipt'];reference=plan['output']['projections']['energy_persistence']
    reference['trajectory'][1]['nominal_soc_pct']=0
    reference['projection_sha256']=identity({k:v for k,v in reference.items() if k!='projection_sha256'})
    plan['receipt_sha256']=identity({k:v for k,v in plan.items() if k!='receipt_sha256'})
    inputs=args['forecast_receipt']['inputs']
    args['forecast_receipt']=seal_energy_forecast(plan_receipt=plan,system_source=inputs['system_source'],horizon_source=inputs['horizon_source'],topology_source=inputs['topology_source'],now=instant(inputs['assessed_at']),runtime_manifest=args['forecast_runtime_manifest'])
    with pytest.raises(ValueError,match='reference'):api.seal_energy_outcomes(**args)


def test_cohort_binds_the_complete_forecast_numerical_source_closure(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals);forecast=args['forecast_receipt'];before=api.cohort_for(forecast,args['plan_receipt'])
    for source in ('household/power_flows.py','household/energy_configuration.py','household/energy_persistence.py'):
        changed=deepcopy(forecast);changed['runtime_manifest']['openhab/scripts/'+source]='f'*64
        assert api.cohort_for(changed,args['plan_receipt'])!=before


@pytest.mark.parametrize('hours',[6,12])
def test_shorter_original_reference_is_explicitly_unavailable_instead_of_indexing_past_it(tmp_path,monkeypatch,originals,hours):
    api,args=context(tmp_path,monkeypatch,originals)
    from household.energy_persistence import project_persistence
    from household.model_snapshot import restore_snapshot
    from household_energy_forecast import seal_energy_forecast
    plan=args['plan_receipt'];inputs=plan['inputs'];inputs['config']['horizon_hours']=hours
    snapshot=restore_snapshot(inputs['snapshot'],inputs['source_contexts'])
    plan['output']['projections']['energy_persistence']=project_persistence(snapshot=snapshot,metric_source=inputs['energy_persistence_source'],horizon_hours=hours,now=instant(inputs['now']))
    plan['receipt_sha256']=identity({k:v for k,v in plan.items() if k!='receipt_sha256'})
    original=args['forecast_receipt']['inputs'];args['forecast_receipt']=seal_energy_forecast(plan_receipt=plan,system_source=original['system_source'],horizon_source=original['horizon_source'],topology_source=original['topology_source'],now=instant(original['assessed_at']),runtime_manifest=args['forecast_runtime_manifest'])
    score=api.seal_energy_outcomes(**args)
    assert score['output']['cohort'] is None and score['output']['by_horizon']['1']['status']=='scenario_or_reference_unavailable'
