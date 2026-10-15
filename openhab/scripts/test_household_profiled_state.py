"""Curated profile observations preserve source clocks and owned publication."""
from pathlib import Path
from datetime import timedelta
from test_household_profiled_outcomes import case,originals
from household.codec import canonical,loads
from household.control_contracts import instant
import importlib
import pytest


def test_curated_profile_and_constant_scenarios_have_no_private_originals(tmp_path,monkeypatch,originals):
    _,args=case(tmp_path,monkeypatch,originals);api=importlib.import_module('household_profiled_state');forecast=args['profiled_receipt'];energy=args['energy_receipt'];at=instant(forecast['inputs']['assessed_at'])
    view=api.project_observation(forecast,energy_receipt=energy,generated_at=at)
    assert view['schema']=='earthship-household-profiled-energy-observation/v1' and view['status']=='conditional'
    assert view['trained_through']==forecast['inputs']['load_source']['artifact']['profile']['latest_qualified_hour_end']
    assert len(view['trajectory'])==24 and view['trajectory'][0]['constant_ac_w']==1000
    assert view['trajectory'][0]['profiled_ac_w']==forecast['output']['load_forecast']['trajectory'][0]['mean_ac_w']
    assert view['profiled_captured_pv_24h_kwh']==forecast['output']['profiled_storage']['modeled_captured_pv_kwh']
    assert instant(view['valid_until'])==instant(view['issued_at'])+timedelta(minutes=15)
    assert all(token not in canonical(view).decode() for token in ('/home/','runtime_manifest','hourly_rows','admission','sources','raw'))


def test_private_publication_preserves_another_owner_and_original_on_guard_failure(tmp_path):
    api=importlib.import_module('household_profiled_state');path=tmp_path/'state.json';value=dict(schema=api.INDEX,samples={})
    api.publish_owned(path,value,guard=lambda:None)
    assert path.read_bytes()==canonical(value) and path.stat().st_mode&0o777==0o600
    def failed():raise ValueError('selection changed')
    with pytest.raises(ValueError):api.publish_owned(path,dict(value,samples={'new':1}),guard=failed)
    assert path.read_bytes()==canonical(value)
    path.write_bytes(b'{"schema":"another-owner"}')
    with pytest.raises(ValueError):api.publish_owned(path,value,guard=lambda:None)
    assert loads(path.read_bytes())==dict(schema='another-owner')
    assert not list(tmp_path.glob('.profiled-*'))


def test_actual_curated_backend_values_pass_public_client_contract(tmp_path,monkeypatch,originals):
    scores,args=case(tmp_path,monkeypatch,originals)
    import household_profiled_state as state
    from household_profiled_samples import summarize_verified_score,build_performance
    import subprocess,json,shutil
    view=state.project_observation(args['profiled_receipt'],energy_receipt=args['energy_receipt'],generated_at=instant(args['profiled_receipt']['inputs']['assessed_at']))
    score=scores.seal_profiled_outcomes(**args);sample=summarize_verified_score(score,verified_at=args['assessed_at'])
    report=build_performance([sample],cohort=score['output']['cohort'],generated_at=args['assessed_at'],next_mature_at=None)
    node=shutil.which('node')
    if node is None:pytest.skip('Node required for public cross-language contract')
    script="import fs from 'node:fs';import {parseProfiledObservation,parseProfiledPerformance} from './src/lib/household/profiledObservation.js';const d=JSON.parse(fs.readFileSync(0,'utf8'));if(!parseProfiledObservation(JSON.stringify(d.view),{nowMs:Date.parse(d.view.generated_at)})||!parseProfiledPerformance(JSON.stringify(d.report),{nowMs:Date.parse(d.report.generated_at)}))process.exit(1);"
    result=subprocess.run([node,'--v8-pool-size=2','--input-type=module','-e',script],cwd=Path(__file__).resolve().parents[2],input=json.dumps(dict(view=view,report=report)),capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr


def test_expired_model_publishes_fresh_unavailability_without_renewing_model_age(tmp_path,monkeypatch,originals):
    _,args=case(tmp_path,monkeypatch,originals)
    from test_household_profiled_forecast import supported_source
    import household_profiled_forecast as forecast
    import household_profiled_state as state
    issue=instant(args['profiled_receipt']['output']['issued_at']);old,lr=supported_source(issue-timedelta(days=2));at=instant(args['profiled_receipt']['inputs']['assessed_at'])
    record=forecast.seal_profiled_forecast(energy_receipt=args['energy_receipt'],plan_receipt=args['plan_receipt'],load_source=old,now=at,
        runtime_manifest=forecast.profiled_runtime_manifest(),energy_runtime_manifest=args['energy_runtime_manifest'],load_runtime_manifest=lr)
    assert record['output']['reason']=='load_model_expired'
    view=state.project_observation(record,energy_receipt=args['energy_receipt'],generated_at=at)
    assert view['status']=='unavailable' and view['reason']=='load_model_expired' and view['trajectory']==[]
    assert instant(view['model_valid_until'])<issue and instant(view['valid_until'])==issue+timedelta(minutes=15)
    assert view['trained_through']==old['artifact']['profile']['latest_qualified_hour_end']
