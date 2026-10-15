"""Versioned load scenarios retain both original constant-load and model receipts."""
from copy import deepcopy
from datetime import timedelta
import importlib
import pytest
from household.codec import identity,canonical
from household.control_contracts import instant
from test_household_energy_forecast import fixture,originals
from test_household_ac_load_store import prepared,NOW


def setup(tmp_path,monkeypatch,originals):
    old,args,plan=fixture(tmp_path,monkeypatch,originals);energy=old.seal_energy_forecast(**args)
    return importlib.import_module('household_profiled_forecast'),old,args,plan,energy


def test_missing_load_model_keeps_original_forecast_and_explicit_new_unavailability(tmp_path,monkeypatch,originals):
    api,old,args,plan,energy=setup(tmp_path,monkeypatch,originals);before=canonical(energy)
    value=api.seal_profiled_forecast(energy_receipt=energy,plan_receipt=plan,load_source=None,now=args['now'],
        runtime_manifest=api.profiled_runtime_manifest(),energy_runtime_manifest=old.forecast_runtime_manifest(),load_runtime_manifest={})
    assert value['schema']=='earthship-household-profiled-energy-receipt/v1'
    assert value['output']['status']=='unavailable' and value['output']['reason']=='load_model_unavailable'
    assert value['inputs']['original_energy_receipt_sha256']==energy['receipt_sha256']
    assert canonical(energy)==before and value['output']['automatic_actuation'] is False
    assert api.replay_profiled_forecast(value,energy_receipt=energy,plan_receipt=plan,runtime_manifest=api.profiled_runtime_manifest(),
        energy_runtime_manifest=old.forecast_runtime_manifest(),load_runtime_manifest={})==value


def test_insufficient_supported_load_does_not_relabel_it_as_current_load(tmp_path,monkeypatch,originals):
    api,old,args,plan,energy=setup(tmp_path,monkeypatch,originals)
    root=tmp_path/'load';root.mkdir(mode=0o700);store,_,_=prepared(root,monkeypatch)
    # The original fixture's issue predates this deliberately sparse profile.
    source=store.read_current(root,assessed_at=NOW,guard=lambda:None)
    with pytest.raises(ValueError,match='available'):
        api.seal_profiled_forecast(energy_receipt=energy,plan_receipt=plan,load_source=source,now=args['now'],runtime_manifest=api.profiled_runtime_manifest(),
            energy_runtime_manifest=old.forecast_runtime_manifest(),load_runtime_manifest=store.runtime_manifest())


@pytest.mark.parametrize('damage',['original','plan','numerics','runtime','load_pin'])
def test_resealed_new_receipt_cannot_change_originals_or_derived_values(tmp_path,monkeypatch,originals,damage):
    api,old,args,plan,energy=setup(tmp_path,monkeypatch,originals)
    runtime=api.profiled_runtime_manifest();er=old.forecast_runtime_manifest()
    value=api.seal_profiled_forecast(energy_receipt=energy,plan_receipt=plan,load_source=None,now=args['now'],runtime_manifest=runtime,energy_runtime_manifest=er,load_runtime_manifest={})
    if damage=='original':energy['output']['array_pv']['potential_pv_kwh']+=1
    elif damage=='plan':plan['inputs']['now']=(args['now']+timedelta(seconds=1)).isoformat()
    elif damage=='runtime':value['runtime_manifest'][next(iter(runtime))]='f'*64
    elif damage=='load_pin':value['inputs']['original_energy_receipt_sha256']='f'*64
    else:value['output']['status']='conditional_nominal_simulation'
    value['receipt_sha256']=identity({k:v for k,v in value.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):api.replay_profiled_forecast(value,energy_receipt=energy,plan_receipt=plan,runtime_manifest=runtime,energy_runtime_manifest=er,load_runtime_manifest={})


def supported_source(issue):
    """Original synthetic thirty-second measurements, three supported full days."""
    from datetime import timezone
    from zoneinfo import ZoneInfo
    from household_ac_load_artifact import build_artifact,runtime_manifest
    from household_ac_load_sources import build_day_source
    from test_household_ac_load_sources import raw
    import json
    zone=ZoneInfo('America/Denver');local=issue.astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0);cutoff=local.astimezone(timezone.utc)
    sources=[]
    for offset in range(14,0,-1):
        start=(local-timedelta(days=offset)).astimezone(timezone.utc);end=(local-timedelta(days=offset-1)).astimezone(timezone.utc);rows=[]
        if offset<=3:
            at=start
            while at<end:
                payload=json.loads(raw(at,int(at.timestamp()//30)));payload['fields']['inverter.ac_output_w']['watts']=300+at.astimezone(zone).hour*10
                rows.append((at,json.dumps(payload)));at+=timedelta(seconds=30)
        sources.append(build_day_source(rows=rows,start=start,end=end,requested_at=end+timedelta(seconds=1),received_at=end+timedelta(seconds=2),item_id=613))
    runtime=runtime_manifest();model=build_artifact(sources=sources,cutoff=cutoff,trained_at=cutoff+timedelta(minutes=1),runtime_manifest=runtime)
    assert model['profile']['status']=='profiled'
    admission=dict(schema='earthship-ac-load-admission/v1',verified_at=(cutoff+timedelta(minutes=2)).isoformat(),
        artifact=dict(name=model['artifact_sha256']+'.load-model.json',document_sha256=identity(model),artifact_sha256=model['artifact_sha256']),runtime_sha256=identity(runtime),
        sources=[dict(name=instant(day['window_start']).astimezone(zone).date().isoformat()+'.ac-day.json.gz',file_sha256=identity(source),source_sha256=source['source_sha256']) for source,day in zip(sources,model['days'])])
    admission['admission_sha256']=identity(admission)
    source=dict(schema='earthship-ac-load-admitted-source/v1',available_at=admission['verified_at'],artifact=model,admission=admission,automatic_actuation=False)
    source['source_sha256']=identity(source)
    return source,runtime


def test_source_bound_supported_profile_changes_only_separate_storage_scenario(tmp_path,monkeypatch,originals):
    api,old,args,plan,energy=setup(tmp_path,monkeypatch,originals);source,lr=supported_source(instant(energy['output']['array_pv']['origin']));before=canonical(energy)
    params=dict(energy_receipt=energy,plan_receipt=plan,load_source=source,now=args['now'],runtime_manifest=api.profiled_runtime_manifest(),energy_runtime_manifest=old.forecast_runtime_manifest(),load_runtime_manifest=lr)
    value=api.seal_profiled_forecast(**params);out=value['output']
    assert out['status']=='conditional_nominal_simulation' and len(out['profiled_storage']['trajectory'])==24
    assert out['load_forecast']['trajectory'][0]['minimum_support_days']==3 and out['current_load_persistence_w']==1000
    assert out['profiled_storage']['modeled_captured_pv_kwh']!=energy['output']['nominal_storage']['modeled_captured_pv_kwh']
    assert canonical(energy)==before and value['inputs']['load_source']==source
    assert api.replay_profiled_forecast(value,**{k:v for k,v in params.items() if k not in {'load_source','now'}})==value
    # Advancing only the decision time never grants an old profile a fresh age.
    source['artifact']['profile']['hours']['0']['median_ac_w']+=1
    source['source_sha256']=identity({k:v for k,v in source.items() if k!='source_sha256'})
    with pytest.raises(ValueError):api.seal_profiled_forecast(**params)


def test_file_only_CLI_replays_external_originals_without_refitting(tmp_path,monkeypatch,originals,capsys):
    api,old,args,plan,energy=setup(tmp_path,monkeypatch,originals)
    value=api.seal_profiled_forecast(energy_receipt=energy,plan_receipt=plan,load_source=None,now=args['now'],runtime_manifest=api.profiled_runtime_manifest(),energy_runtime_manifest=old.forecast_runtime_manifest(),load_runtime_manifest={})
    paths=[]
    for name,record in (('profile',value),('energy',energy),('plan',plan)):
        path=tmp_path/(name+'.json');path.write_bytes(canonical(record));path.chmod(0o600);paths.append(path)
    command=['--receipt',str(paths[0]),'--energy',str(paths[1]),'--plan',str(paths[2])]
    assert api.main(command)==0
    import json
    assert json.loads(capsys.readouterr().out)==value
    paths[1].write_bytes(b'{}')
    assert api.main(command)==1 and 'replay refused' in capsys.readouterr().err
