"""Scheduled solar/storage scoring retains hourly originals and terminal evidence."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import importlib,os
import pytest
from household.codec import canonical,loads
from test_household_solar_outcomes import context,originals


def test_scheduled_scoring_keeps_hourly_origin_and_reuses_terminal_sources(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals);stage=tmp_path/'stage';directory=stage/'evidence';directory.mkdir(parents=True,mode=0o700);stage.chmod(0o700)
    forecast=args['forecast_receipt'];plan=args['plan_receipt'];raw=canonical(forecast)
    path=directory/(sha256(raw).hexdigest()+'.household-energy-forecast-v1.json');path.write_bytes(raw);path.chmod(0o600)
    original=directory/(sha256(canonical(plan)).hexdigest()+'.household-model-plan-v6.json');original.write_bytes(canonical(plan));original.chmod(0o600)
    issue=__import__('household.control_contracts',fromlist=['instant']).instant(forecast['output']['array_pv']['origin']);os.utime(path,(issue.timestamp()+15,issue.timestamp()+15))
    state=tmp_path/'state';state.mkdir(mode=0o700);producer=importlib.import_module('household_solar_score');calls=[]
    def reader(**kwargs):calls.append(kwargs['target_at']);return args['endpoint_sources']['1']
    result=producer.run(stage=stage,historical=[],guard=lambda:None,clock=lambda:args['assessed_at'],monotonic=lambda:0.,deadline=20.,state_root=state,reader=reader)
    assert result['status']=='solar_storage_performance_refreshed' and result['count']==1
    report=loads((state/'energy-performance.json').read_bytes());assert report['by_horizon']['1']['mae_soc_pct']['hold_soc']==5
    index=loads((state/'energy-outcomes/samples.json').read_bytes());assert len(index['samples'])==1 and len(calls)==1
    second=producer.run(stage=stage,historical=[],guard=lambda:None,clock=lambda:args['assessed_at']+timedelta(minutes=1),monotonic=lambda:0.,deadline=20.,state_root=state,reader=lambda **kwargs:pytest.fail('terminal observation queried again'))
    assert second['count']==1 and (state/'energy-performance.json').stat().st_mode&0o777==0o600
    assert path.read_bytes()==raw and original.read_bytes()==canonical(plan)


def test_publication_refuses_unrelated_target_and_keeps_original_bytes(tmp_path):
    from household_energy_state import publish_owned,REPORT
    tmp_path.chmod(0o700);path=tmp_path/'cache.json';path.write_bytes(b'{"owner":"other"}');path.chmod(0o600)
    with pytest.raises(ValueError):publish_owned(path,dict(schema=REPORT),guard=lambda:None)
    assert path.read_bytes()==b'{"owner":"other"}'


def test_compact_outcome_cli_requires_both_original_documents(tmp_path,monkeypatch,originals,capsys):
    api,args=context(tmp_path,monkeypatch,originals);score=api.seal_energy_outcomes(**args)
    paths={key:tmp_path/(key+'.json') for key in ('receipt','forecast','plan')}
    for key,value in (('receipt',score),('forecast',args['forecast_receipt']),('plan',args['plan_receipt'])):paths[key].write_bytes(canonical(value));paths[key].chmod(0o600)
    options=[arg for key,path in paths.items() for arg in ('--'+key,str(path))]
    assert api.main(options)==0 and loads(capsys.readouterr().out)==score
    paths['forecast'].write_bytes(b'{}')
    assert api.main(options)==1
    assert 'replay refused' in capsys.readouterr().err


def test_a_scenario_without_a_qualified_reference_does_not_create_matched_pairs(tmp_path,monkeypatch,originals):
    api,args=context(tmp_path,monkeypatch,originals)
    from household.model_snapshot import restore_snapshot
    from household.thermal_model import PreparedProjection
    from test_household_model_pipeline import run
    from household_energy_forecast import seal_energy_forecast,forecast_runtime_manifest
    from household.control_contracts import instant
    plan=args['plan_receipt'];inputs=plan['inputs']
    snapshot=restore_snapshot(inputs['snapshot'],inputs['source_contexts'])
    plan=run(snapshot,PreparedProjection(canonical(inputs['thermal_inputs'])),runtime_manifest=plan['runtime_manifest'],energy_persistence_source=None)
    previous=args['forecast_receipt']['inputs'];forecast=seal_energy_forecast(plan_receipt=plan,system_source=previous['system_source'],horizon_source=previous['horizon_source'],topology_source=previous['topology_source'],now=instant(previous['assessed_at']),runtime_manifest=forecast_runtime_manifest())
    assert forecast['output']['nominal_storage']['status']=='conditional_nominal_simulation'
    stage=tmp_path/'stage';directory=stage/'evidence';directory.mkdir(parents=True,mode=0o700);stage.chmod(0o700)
    for value,suffix in ((forecast,'.household-energy-forecast-v1.json'),(plan,'.household-model-plan-v6.json')):
        raw=canonical(value);path=directory/(sha256(raw).hexdigest()+suffix);path.write_bytes(raw);path.chmod(0o600)
        if suffix.startswith('.household-energy'):os.utime(path,(instant(forecast['output']['array_pv']['origin']).timestamp()+15,)*2)
    state=tmp_path/'state';state.mkdir(mode=0o700)
    result=importlib.import_module('household_solar_score').run(stage=stage,historical=[],guard=lambda:None,clock=lambda:args['assessed_at'],monotonic=lambda:0.,deadline=20.,state_root=state,reader=lambda **kw:pytest.fail('unmatched reference must not acquire outcomes'))
    assert result['status']=='waiting' and result['reason']=='current_solar_reference_unavailable'
    assert not (state/'energy-performance.json').exists()
