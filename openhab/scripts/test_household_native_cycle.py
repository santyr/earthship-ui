"""Native cycle adapters replay original delivery and preserve observer isolation."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from household.codec import canonical
from test_household_native_thermal import context,originals,CODE


def archive(tmp_path,monkeypatch,originals):
    import native_thermal_forecast as forecast
    from test_native_thermal_score import issued
    import native_thermal_artifact as artifacts
    c,r,k=issued(tmp_path,monkeypatch,originals)
    monkeypatch.setattr(artifacts,'current_native_runtime',lambda **kw:deepcopy(k['runtime']))
    directory=tmp_path/'delivery';directory.mkdir(mode=0o700)
    origin=directory/(c['capture_sha256']+'.native-provisional-origin-v2.json')
    origin.write_bytes(canonical(c));origin.chmod(0o600)
    d=dict(schema='earthship-provisional-thermal-delivery/v2',issued_at=c['issued_at'],capture_path=str(origin),
        capture_sha256=c['capture_sha256'],artifact_sha256=k['expected_artifact_sha256'],
        runtime_sha256=c['candidate']['runtime_sha256'],geometry_series_sha256=c['geometry_series_sha256'],receipts=r)
    d['delivery_sha256']=forecast.digest(d,'delivery_sha256')
    delivery=directory/(d['delivery_sha256']+'.native-provisional-delivery-v2.json')
    delivery.write_bytes(canonical(d));delivery.chmod(0o600)
    p=dict(status='published',delivery_verified=True,origin_path=str(origin),delivery_path=str(delivery))
    return c,r,k,p,d


def test_native_cycle_archive_replays_original_capture_and_both_persisted_receipts(tmp_path,monkeypatch,originals):
    import household_cycle as cycle
    c,r,k,p,d=archive(tmp_path,monkeypatch,originals)
    loaded=cycle.load_cycle_delivery(p,issue=c['issued_at'],guard=lambda:None,**k)
    assert loaded['capture']==c and loaded['receipts']==r
    loaded['verify_unchanged']()
    Path(p['origin_path']).unlink()
    with pytest.raises((ValueError,OSError)):loaded['verify_unchanged']()


@pytest.mark.parametrize('damage',['schema','capture_root','artifact','runtime','geometry','receipt','suffix','precision','issue','missing_pin'])
def test_native_delivery_refuses_resealed_detachment(tmp_path,monkeypatch,originals,damage):
    import household_cycle as cycle
    import native_thermal_forecast as forecast
    c,r,k,p,d=archive(tmp_path,monkeypatch,originals)
    if damage=='schema':d['schema']='earthship-provisional-thermal-delivery/v1'
    elif damage=='capture_root':d['capture_sha256']='f'*64
    elif damage in ('artifact','runtime','geometry'):d[damage+('_series' if damage=='geometry' else '')+'_sha256']='f'*64
    elif damage=='receipt':next(iter(d['receipts'].values()))['state']='{}'
    elif damage=='precision':d['issued_at']=d['issued_at'].replace('+00:00','.0000009+00:00')
    elif damage=='missing_pin':k.pop('expected_artifact_sha256')
    issue=c['issued_at'] if damage!='issue' else (datetime.fromisoformat(c['issued_at'])+timedelta(minutes=5)).isoformat()
    d['delivery_sha256']=forecast.digest(d,'delivery_sha256')
    old=Path(p['delivery_path']);old.unlink()
    suffix='.provisional-delivery-v1.json' if damage=='suffix' else '.native-provisional-delivery-v2.json'
    new=old.parent/(d['delivery_sha256']+suffix);new.write_bytes(canonical(d));new.chmod(0o600);p['delivery_path']=str(new)
    with pytest.raises(ValueError):cycle.load_cycle_delivery(p,issue=issue,guard=lambda:None,**k)


def test_native_complete_cycle_dispatches_native_preparation_before_pure_derivation(tmp_path,monkeypatch,originals):
    import household_cycle as cycle
    import household.weather_context as weather
    import household_pipeline,household_observation
    c,r,k,p,d=archive(tmp_path,monkeypatch,originals);calls=[]
    real=weather.prepare_native_cycle_contexts
    def prepare(*args,**kwargs):calls.append('prepare');return real(*args,**kwargs)
    monkeypatch.setattr(weather,'prepare_native_cycle_contexts',prepare)
    def derive(**kwargs):
        calls.append('derive')
        assert kwargs['thermal'].to_dict()['schema']=='earthship-household-prepared-thermal/v2'
        assert kwargs['weather'].original_capture==c and kwargs['receipts']==r
        return {'fixture_record':True}
    monkeypatch.setattr(cycle,'derive_cycle',derive)
    monkeypatch.setattr(household_pipeline,'verify_source_closure',lambda *a:None)
    monkeypatch.setattr(cycle,'_retain_original',lambda *a:Path(p['origin_path']))
    monkeypatch.setattr(household_observation,'materialize',lambda *a,**kw:{'status':'fixture_materialized'})
    result=cycle.complete_cycle(publication=p,collection={'status':'collected','issue':c['issued_at'],'originals':{}},
        parameter_record=None,runtime_manifest=None,code_revision=CODE,evidence_directory=None,observation_cache=None,
        guard=lambda:None,clock=lambda:datetime.fromisoformat(c['published_at']),**k)
    assert result=={'status':'fixture_materialized'} and calls==['prepare','derive']


@pytest.mark.parametrize("policy",[False,True])
def test_native_cycle_derivation_preserves_original_forecast_and_measured_sources(tmp_path,monkeypatch,originals,policy,capsys):
    from household.weather_context import prepare_native_cycle_contexts
    from household.energy_configuration import prepare_energy_configuration
    from household.measured_weather import prepare_measured_weather
    from household.control_contracts import instant
    from household.pipeline import replay_pipeline
    from test_household_measured_weather import sources
    from test_household_model_snapshot import source_at
    from test_household_model_pipeline import RUNTIME
    from test_household_models import FIXTURE
    from test_household_energy_source_pipeline import make
    import household_cycle as cycle
    c,r,k,p,d=archive(tmp_path,monkeypatch,originals)
    thermal,weather=prepare_native_cycle_contexts(c,code_revision=CODE,**k)
    # Retain the independently qualified bank/topology bytes from the existing
    # source fixture; native thermal output is never cast to a legacy forecast.
    configuration_dir=tmp_path/'configuration';configuration_dir.mkdir(mode=0o700)
    _,configuration,_,_=make(configuration_dir,monkeypatch)
    issue=instant(c['issued_at']);at=issue-timedelta(seconds=1);body=configuration.to_dict()
    configuration=prepare_energy_configuration(bank_config_raw=body['bank_source']['raw'],ac_policy_raw=body['load_topology_source']['raw'],
        bank_available_at=at,topology_available_at=at,as_of=at,created_at=at)
    measured=prepare_measured_weather(sources=sources(at),as_of=at,created_at=at)
    retained=dict(schema='earthship-household-cycle-sources/v1',issue=issue.isoformat(),captured_at=at.isoformat(),
        power_receipt=source_at(at),energy_configuration=configuration.to_dict(),measured_weather=measured.to_dict(),
        owner_bindings={'before':{},'after':{}},automatic_actuation=False)
    runtime=RUNTIME
    if policy:
        from household_pipeline import pipeline_runtime_manifest
        from household.power_snapshot import compile_power_inputs
        runtime=pipeline_runtime_manifest(expanded=True,configured=True,measured=True)
        original_inputs=retained['power_receipt']['inputs']
        retained['power_receipt']=compile_power_inputs(original_inputs['bundle'],managed=original_inputs['managed'],ownership=original_inputs['ownership'],
            code_revision=original_inputs['code_revision'],runtime_manifest=runtime)
    params=dict(collected_at=(issue-timedelta(days=1)).isoformat(),record={'household_energy_inputs':FIXTURE['cases'][0]['inputs']})
    record=cycle.derive_cycle(originals=retained,capture=c,receipts=r,thermal=thermal,weather=weather,
        parameter_record=params,runtime_manifest=runtime,code_revision=CODE,now=instant(c['published_at']))
    if policy:
        # Full native geometry plus original installed rule/status evidence must
        # fit the private plan and survive replay; the public view stays small.
        from household.pipeline import seal_pipeline,_restore
        from household.model_snapshot import restore_snapshot
        from household.energy_model import PreparedEnergyInputs
        from household.capabilities import CapabilityRegistry
        from household.owner_sources import coordination_from_policy
        from test_household_owner_policy import original
        from hashlib import sha256
        source=original(now=issue)
        # OpenHAB also includes descriptive metadata. Exercise valid responses
        # near the existing 64 KiB source bound, rather than tiny rule stubs.
        for name in ('rule_before','rule_after'):
            body=json.loads(source[name]['raw']);body['description']='M'*(64000-len(canonical(body)))
            raw=canonical(body).decode()
            assert len(raw.encode())<65536
            source[name].update(raw=raw,sha256=sha256(raw.encode()).hexdigest())
        raw=canonical([json.loads(source['rule_before']['raw'])]).decode()
        owner=dict(schema='earthship-household-owner-source/v1',endpoint='/rules?summary=true',raw=raw,
            sha256=sha256(raw.encode()).hexdigest(),requested_at=(issue-timedelta(seconds=3)).isoformat(),
            received_at=(issue-timedelta(seconds=1)).isoformat())
        inputs=record['inputs'];snapshot=restore_snapshot(inputs['snapshot'],inputs['source_contexts'])
        registry=_restore(inputs['registry'],CapabilityRegistry,'registry_id')
        coordination=coordination_from_policy(owner,source,snapshot_id=snapshot.snapshot_id,registry=registry,horizon_hours=24,as_of=issue)
        record=seal_pipeline(snapshot=snapshot,registry=registry,energy_inputs=PreparedEnergyInputs(canonical(inputs['energy_inputs'])),
            thermal_inputs=thermal,thermal_runtime=thermal.to_dict()['executing_runtime'],coordination=coordination,
            config=inputs['config'],now=instant(inputs['now']),runtime_manifest=runtime)
        from household.resources import seal_resources,replay_resources,UNITS
        analysis=seal_resources(plan_receipt=record['output']['plan_receipt'],scales={name:1. for name in UNITS},orders=[],
            assessed_at=instant(inputs['now']),plan_runtime_manifest=runtime,analysis_runtime_manifest=runtime)
        assert replay_resources(analysis,plan_runtime_manifest=runtime,analysis_runtime_manifest=runtime)==analysis
        import household_plan
        path=tmp_path/'native-owner-plan.json';path.write_bytes(canonical(record['output']['plan_receipt']));path.chmod(0o600)
        assert household_plan.main(['--receipt',str(path)])==0
        assert json.loads(capsys.readouterr().out)==record['output']['plan_receipt']
        assert record['inputs']['coordination']['policy_source']==source
        assert record['inputs']['coordination']['policy_observations']['hex_southoutlet_cycle']['reason']=='after_dark'
    assert record['output']['projections']['thermal']['output']==c['output']
    assert record['output']['projections']['weather']['schema']=='earthship-household-weather-projection/v3'
    assert record['output']['automatic_actuation'] is False
    assert replay_pipeline(record,runtime_manifest=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])==record
