"""Whole-night outcomes retain original atomic evidence and independent bindings."""
from datetime import date,timedelta,timezone
import importlib,json
from zoneinfo import ZoneInfo
import pytest
from advisory_windows import trough_window
from household.codec import identity
from local_measurement_test_support import bms_soc_evidence as evidence

DAY=date(2026,10,9)
WINDOW=trough_window(DAY,'America/Denver')
PHASE='00000000-0000-0000-0000-000000000001'
BANK=json.dumps({'version':1,'timezone':'America/Denver','epochs':[{
    'id':'physical_bank','start_local_date':'2026-07-19','end_local_date_exclusive':None,
    'current_analytics':True,'nominal_capacity_ah':400.,'nominal_usable_kwh':20.48}]})


def api():
    assert importlib.util.find_spec('household.energy_outcome_sources') is not None,'original energy outcome sources missing'
    return importlib.import_module('household.energy_outcome_sources')


def inputs():
    return dict(rows=[(WINDOW.start+timedelta(minutes=m),evidence(WINDOW.start+timedelta(minutes=m),soc=80 if m==300 else 90)) for m in range(900)],
        prediction_day=DAY,assessed_at=WINDOW.end+timedelta(minutes=1),bank_config_raw=BANK,
        expected_bank_epoch='physical_bank',expected_stream_epoch=PHASE)


def test_original_whole_night_measurement_replays_without_reads(monkeypatch):
    mod=api();args=inputs();packet=mod.build_night_source(**args)
    assert packet['rows'][300][1]==args['rows'][300][1]
    assert packet['assessment']['min_soc_pct']==80 and packet['assessment']['coverage']==1
    assert packet['bank_config_raw']==BANK
    import builtins
    from pathlib import Path
    monkeypatch.setattr(builtins,'open',lambda *a,**k:pytest.fail('pure measurement read'))
    monkeypatch.setattr(Path,'read_bytes',lambda *a,**k:pytest.fail('pure measurement read'))
    assert mod.replay_night_source(packet)==packet['assessment']


@pytest.mark.parametrize('mode',['sparse','null_barrier','malformed_barrier','unavailable_barrier','incomplete','cutover'])
def test_missing_or_unqualified_night_never_supplies_minimum(mode):
    mod=api();args=inputs()
    if mode=='sparse':args['rows']=args['rows'][:1]
    elif mode in ('null_barrier','malformed_barrier','unavailable_barrier'):
        raw=None if mode=='null_barrier' else '{}' if mode=='malformed_barrier' else evidence(WINDOW.start+timedelta(minutes=1),status='unavailable')
        args['rows']=[args['rows'][0],(WINDOW.start+timedelta(minutes=1),raw)]
    elif mode=='incomplete':args['assessed_at']=WINDOW.end-timedelta(seconds=1);args['rows']=[]
    else:
        bank=json.loads(BANK);bank['epochs'][0]['end_local_date_exclusive']='2026-10-10';args['bank_config_raw']=json.dumps(bank)
    packet=mod.build_night_source(**args);result=mod.replay_night_source(packet)
    assert result['status']!='measured' and result['min_soc_pct'] is None
    if mode=='null_barrier':assert packet['rows'][1][1] is None


@pytest.mark.parametrize('damage',['wrong_phase','future','wrong_bank','unknown_start','overlap','oversize','too_many','tie'])
def test_original_night_refuses_changed_bindings_and_context(damage):
    mod=api();args=inputs()
    if damage=='wrong_phase':args['expected_stream_epoch']='00000000-0000-0000-0000-000000000002'
    elif damage=='future':args['rows'].append((args['assessed_at']+timedelta(seconds=1),'{}'))
    elif damage=='wrong_bank':args['expected_bank_epoch']='other_bank'
    elif damage=='unknown_start':
        b=json.loads(BANK);b['epochs'][0]['start_local_date']=None;args['bank_config_raw']=json.dumps(b)
    elif damage=='overlap':
        b=json.loads(BANK);b['epochs'].append({**b['epochs'][0],'id':'other','current_analytics':False});args['bank_config_raw']=json.dumps(b)
    elif damage=='oversize':args['rows'][0]=(args['rows'][0][0],'x'*4097)
    elif damage=='too_many':args['rows']*=12
    else:args['rows'].insert(1,args['rows'][0])
    with pytest.raises(ValueError):mod.build_night_source(**args)


def test_resealed_changed_minimum_refuses():
    mod=api();packet=mod.build_night_source(**inputs());packet['assessment']['min_soc_pct']=0
    packet['source_sha256']=identity({k:v for k,v in packet.items() if k!='source_sha256'})
    with pytest.raises(ValueError):mod.replay_night_source(packet)


def fetch(connection,**changes):
    mod=api();assert hasattr(mod,'fetch_night_source'),'bounded night collector missing'
    args=inputs();args.pop('rows');args.update(changes)
    return mod.fetch_night_source(lambda:connection,remaining=lambda:15.,**args)


def test_night_database_read_preserves_raw_rows_and_readonly_bounds():
    from test_weather_temperature_history import Connection
    args=inputs();rows=[(at,raw,len(raw.encode())) for at,raw in args['rows']]
    connection=Connection(rows=rows);packet=fetch(connection)
    assert packet['assessment']['min_soc_pct']==80
    assert connection.closed and connection.session['readonly'] is True
    assert all(q.startswith(('SET LOCAL','SHOW ','SELECT ')) for q,_ in connection.calls)
    query,params=connection.calls[-1]
    assert 'LIMIT 10001' in query and 'octet_length' in query and 'ORDER BY time' in query
    assert params==(WINDOW.start-timedelta(seconds=120),WINDOW.end)
    assert ('BMS_SOC_Evidence_JSON',) in [p for _,p in connection.calls]


@pytest.mark.parametrize('damage',['mapping','write','isolation','too_many','oversize','outside','tie','transport','null'])
def test_night_database_refuses_unbounded_context_and_retains_null(damage):
    from test_weather_temperature_history import Connection
    at,raw=inputs()['rows'][0];options={'rows':[(at,raw,len(raw.encode()))]}
    if damage=='mapping':options['mapping']=[(613,),(614,)]
    elif damage=='write':options['read_only']='off'
    elif damage=='isolation':options['isolation']='read committed'
    elif damage=='too_many':options['rows']*=10001
    elif damage=='oversize':options['rows']=[(at,None,4097)]
    elif damage=='outside':options['rows']=[(WINDOW.end,raw,len(raw.encode()))]
    elif damage=='tie':options['rows']*=2
    elif damage=='transport':options['fail']='public.items'
    else:options['rows'].append((at+timedelta(minutes=1),None,None))
    connection=Connection(**options)
    if damage=='null':
        packet=fetch(connection);assert packet['rows'][1][1] is None and packet['assessment']['min_soc_pct'] is None
    else:
        with pytest.raises(ValueError):fetch(connection)
    assert connection.closed


def test_immature_night_does_not_open_database():
    mod=api();assert hasattr(mod,'fetch_night_source'),'bounded night collector missing'
    args=inputs();args.pop('rows');args['assessed_at']=WINDOW.end-timedelta(seconds=1)
    packet=mod.fetch_night_source(lambda:pytest.fail('partial night acquired'),remaining=lambda:15.,**args)
    assert packet['assessment']['status']=='pending' and packet['rows']==[]


def scoring_api():
    assert importlib.util.find_spec('household.energy_outcomes') is not None,'original energy scoring missing'
    return importlib.import_module('household.energy_outcomes')


def scoring_inputs():
    from test_household_pipeline import pipeline
    from household.control_contracts import instant
    from hashlib import sha256
    from test_household_pipeline import setup,context,config,energy_inputs,NOW
    from household.snapshot import HouseholdSnapshot
    from household.codec import canonical
    from household.energy_model import bind_energy_inputs
    original,registry=setup();document=original.to_dict()
    document['domains']['energy']['battery_soc']['evidence']['source_identity']='BMS_SOC_Evidence_JSON'
    snapshot=HouseholdSnapshot(canonical({k:v for k,v in document.items() if k!='snapshot_id'}))
    plan=pipeline(snapshot=snapshot,registry=registry,coordination=context(snapshot),
        energy_inputs=bind_energy_inputs(energy_inputs().numerical,snapshot=snapshot))
    snap=plan['inputs']['snapshot'];ref=snap['domains']['energy']['battery_soc']['evidence']
    day=instant(snap['as_of']).astimezone(ZoneInfo('America/Denver')).date()
    window=trough_window(day,'America/Denver');at=instant(snap['as_of'])
    source=inputs();source.update(prediction_day=day,assessed_at=window.end+timedelta(minutes=1),
        rows=[(window.start+timedelta(minutes=m),evidence(window.start+timedelta(minutes=m),soc=80 if m==300 else 90)) for m in range(900)])
    origin=dict(version=1,assessedAtMs=int(at.timestamp()*1000),recordedAtMs=int(instant(ref['received_at']).timestamp()*1000),
        validUntilMs=int(instant(ref['valid_until']).timestamp()*1000),streamEpoch=ref['source_epoch'],evidenceSha256=ref['digest'],socPct=100.)
    raw=json.dumps(dict(version=1,predictionDay=day.isoformat(),issuedAt=at.isoformat(),pvTodayKwh=1.,curtailmentHoursToday=0.,
        overnightTroughSocPct=plan['output']['projections']['energy']['output']['trough_pred'],thermalAdvisory='none',energySocOrigin=origin))
    forecast=dict(source_identity='Forecast_Prediction_Receipt_JSON',persisted_at=(at+timedelta(seconds=1)).isoformat(),raw=raw,sha256=sha256(raw.encode()).hexdigest())
    return dict(plan_receipt=plan,forecast_source=forecast,night_source=api().build_night_source(**source),
        plan_runtime_manifest=plan['runtime_manifest'],outcome_runtime_manifest={'household/energy_outcomes.py':'b'*64},thermal_runtime=None)


def test_original_energy_plan_and_delivery_score_whole_night_without_reads(monkeypatch):
    mod=scoring_api();args=scoring_inputs();receipt=mod.seal_energy_outcomes(**args)
    assert receipt['output']['status']=='scored' and receipt['output']['actual_min_soc_pct']==80
    assert receipt['output']['error_soc_pct']==receipt['output']['predicted_min_soc_pct']-80
    assert receipt['output']['causal_benefit_qualified'] is False and receipt['output']['automatic_actuation'] is False
    assert receipt['output']['evaluation_scope']=='retrospective_planner_from_original_delivered_forecast'
    import builtins
    monkeypatch.setattr(builtins,'open',lambda *a,**k:pytest.fail('energy score replay read'))
    assert mod.replay_energy_outcomes(receipt,plan_runtime_manifest=args['plan_runtime_manifest'],outcome_runtime_manifest=args['outcome_runtime_manifest'],thermal_runtime=None)==receipt


@pytest.mark.parametrize('damage',['value','phase','digest','future_delivery','day','origin_clock','bank_capacity','assessment','derived_error'])
def test_energy_score_refuses_wrong_original_binding_even_when_resealed(damage):
    mod=scoring_api();args=scoring_inputs();source=args['forecast_source'];raw=json.loads(source['raw'])
    if damage=='value':raw['overnightTroughSocPct']+=1
    elif damage=='phase':raw['energySocOrigin']['streamEpoch']='00000000-0000-0000-0000-000000000002'
    elif damage=='digest':raw['energySocOrigin']['evidenceSha256']='e'*64
    elif damage=='future_delivery':source['persisted_at']=args['night_source']['assessment']['window_start']
    elif damage=='day':raw['predictionDay']='2026-09-28'
    elif damage=='origin_clock':raw['energySocOrigin']['assessedAtMs']+=1000
    elif damage=='bank_capacity':
        packet=args['night_source'];bank=json.loads(packet['bank_config_raw']);bank['epochs'][0]['nominal_usable_kwh']=40.
        packet['bank_config_raw']=json.dumps(bank)
        from hashlib import sha256
        packet['bank_config_sha256']=sha256(packet['bank_config_raw'].encode()).hexdigest();packet['source_sha256']=identity({k:v for k,v in packet.items() if k!='source_sha256'})
    elif damage=='assessment':args['night_source']['assessment']['min_soc_pct']=0
    else:
        receipt=mod.seal_energy_outcomes(**args);receipt['output']['error_soc_pct']=0;receipt['receipt_sha256']=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'})
        with pytest.raises(ValueError):mod.replay_energy_outcomes(receipt,plan_runtime_manifest=args['plan_runtime_manifest'],outcome_runtime_manifest=args['outcome_runtime_manifest'],thermal_runtime=None)
        return
    from hashlib import sha256
    source['raw']=json.dumps(raw);source['sha256']=sha256(source['raw'].encode()).hexdigest()
    with pytest.raises(ValueError):mod.seal_energy_outcomes(**args)


@pytest.mark.parametrize('missing',['model','delivery','outcome','incomplete'])
def test_energy_scoring_missing_evidence_never_becomes_zero_error(missing):
    mod=scoring_api();args=scoring_inputs()
    if missing=='model':
        from test_household_pipeline import pipeline
        from household.pipeline import seal_pipeline
        from household.snapshot import HouseholdSnapshot
        from household.capabilities import CapabilityRegistry
        from household.codec import canonical
        from household.control_contracts import instant
        original=args['plan_receipt'];source=original['inputs']
        args['plan_receipt']=seal_pipeline(snapshot=HouseholdSnapshot(canonical({k:v for k,v in source['snapshot'].items() if k!='snapshot_id'})),
            registry=CapabilityRegistry(canonical({k:v for k,v in source['registry'].items() if k!='registry_id'})),energy_inputs=None,
            thermal_inputs=None,thermal_runtime=None,coordination=source['coordination'],config=source['config'],now=instant(source['now']),
            runtime_manifest=args['plan_runtime_manifest'])
    elif missing=='delivery':args['forecast_source']=None
    elif missing=='outcome':args['night_source']=None
    else:
        packet=args['night_source']
        from household.control_contracts import instant
        args['night_source']=api().build_night_source(rows=[],prediction_day=date.fromisoformat(packet['prediction_day']),
            assessed_at=instant(packet['assessment']['window_end'])-timedelta(seconds=1),bank_config_raw=packet['bank_config_raw'],
            expected_bank_epoch=packet['expected_bank_epoch'],expected_stream_epoch=packet['expected_stream_epoch'])
    result=mod.seal_energy_outcomes(**args)['output']
    assert result['status']!='scored' and result['error_soc_pct'] is None


def test_energy_outcome_cli_refuses_public_special_and_changed_source(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    script=Path(__file__).with_name('household_energy_outcomes.py')
    assert script.exists(),'private energy outcome CLI missing'
    fifo=tmp_path/'fifo';os.mkfifo(fifo,0o600)
    public=tmp_path/'public.json';public.write_text('{"private":"must-stay-private"}');public.chmod(0o644)
    for path in (fifo,public):
        result=subprocess.run([sys.executable,str(script),'--receipt',str(path)],capture_output=True,text=True,timeout=5)
        assert result.returncode==1 and not result.stdout and 'must-stay-private' not in result.stderr and 'Traceback' not in result.stderr


def test_energy_outcome_cli_replays_actual_source_closure(tmp_path):
    import subprocess,sys
    from pathlib import Path
    script=Path(__file__).with_name('household_energy_outcomes.py')
    assert script.exists(),'private energy outcome CLI missing'
    from household_energy_outcomes import energy_outcome_runtime_manifest
    from household_pipeline import pipeline_runtime_manifest
    from household.pipeline import seal_pipeline
    from household.snapshot import HouseholdSnapshot
    from household.capabilities import CapabilityRegistry
    from household.energy_model import PreparedEnergyInputs
    from household.codec import canonical
    from household.control_contracts import instant
    args=scoring_inputs();old=args['plan_receipt'];source=old['inputs'];args['plan_runtime_manifest']=pipeline_runtime_manifest()
    args['plan_receipt']=seal_pipeline(snapshot=HouseholdSnapshot(canonical({k:v for k,v in source['snapshot'].items() if k!='snapshot_id'})),
        registry=CapabilityRegistry(canonical({k:v for k,v in source['registry'].items() if k!='registry_id'})),
        energy_inputs=PreparedEnergyInputs(canonical(source['energy_inputs'])),thermal_inputs=None,thermal_runtime=None,
        coordination=source['coordination'],config=source['config'],now=instant(source['now']),runtime_manifest=args['plan_runtime_manifest'])
    args['outcome_runtime_manifest']=energy_outcome_runtime_manifest();receipt=scoring_api().seal_energy_outcomes(**args)
    path=tmp_path/'score.json';path.write_bytes(canonical(receipt));path.chmod(0o600)
    result=subprocess.run([sys.executable,str(script),'--receipt',str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)==receipt
    receipt['outcome_runtime_manifest']['companion/earthship_energy/trough_assessment.py']='f'*64
    receipt['receipt_sha256']=identity({k:v for k,v in receipt.items() if k!='receipt_sha256'});path.write_bytes(canonical(receipt))
    result=subprocess.run([sys.executable,str(script),'--receipt',str(path)],capture_output=True,text=True,timeout=15)
    assert result.returncode==1 and not result.stdout


def restarted_night(args,damage=None):
    from hashlib import sha256
    from household.control_contracts import instant
    packet=args['night_source'];phase='00000000-0000-0000-0000-000000000002';assessed=instant(packet['assessed_at'])
    rows=[]
    for at,raw in packet['rows']:
        value=json.loads(raw);value['streamEpoch']=phase;rows.append((instant(at),json.dumps(value)))
    now=assessed-timedelta(seconds=1);raw=json.loads(evidence(now,soc=85));raw['streamEpoch']=phase
    if damage=='expired':raw=json.loads(evidence(assessed-timedelta(seconds=120),soc=85));raw['streamEpoch']=phase
    elif damage=='wrong_phase':raw['streamEpoch']='00000000-0000-0000-0000-000000000003'
    binding=dict(source_identity='BMS_SOC_Evidence_JSON',raw=json.dumps(raw),available_at=assessed.isoformat(),sha256=sha256(json.dumps(raw).encode()).hexdigest())
    if damage=='future':binding['available_at']=(assessed+timedelta(seconds=1)).isoformat()
    return api().build_night_source(rows=rows,prediction_day=date.fromisoformat(packet['prediction_day']),assessed_at=assessed,
        bank_config_raw=packet['bank_config_raw'],expected_bank_epoch=packet['expected_bank_epoch'],expected_stream_epoch=phase,
        owner_binding=None if damage=='missing' else binding)


def test_producer_restart_can_score_with_independent_later_owner_binding():
    args=scoring_inputs();args['night_source']=restarted_night(args)
    result=scoring_api().seal_energy_outcomes(**args)['output']
    assert result['status']=='scored' and result['actual_min_soc_pct']==80
    assert result['producer_stream_changed'] is True and result['original_bank_provenance_qualified'] is False
    assert result['causal_benefit_qualified'] is False


@pytest.mark.parametrize('damage',['expired','wrong_phase','future','missing'])
def test_unbound_producer_restart_cannot_score(damage):
    args=scoring_inputs()
    with pytest.raises(ValueError):
        args['night_source']=restarted_night(args,damage)
        scoring_api().seal_energy_outcomes(**args)


@pytest.mark.parametrize('horizon',[6,12,24])
def test_normal_0640_daily_energy_target_is_independent_of_optional_planner_horizon(horizon):
    from datetime import datetime
    from hashlib import sha256
    from household.adapters import battery_soc
    from household.snapshot import build_snapshot
    from household.energy_model import PreparedEnergyInputs,bind_energy_inputs
    from household.pipeline import seal_pipeline
    from household.capabilities import CapabilityRegistry
    from household.codec import canonical
    from household.control_contracts import instant
    args=scoring_inputs();source=args['plan_receipt']['inputs'];old=source['snapshot'];day=date.fromisoformat(args['night_source']['prediction_day'])
    issued=datetime.combine(day,datetime.min.time().replace(hour=6,minute=40),ZoneInfo('America/Denver')).astimezone(timezone.utc)
    raw=evidence(issued,soc=100);observation=battery_soc(raw=raw,expected_sha256=sha256(raw.encode()).hexdigest(),source_identity='BMS_SOC_Evidence_JSON',
        expected_epoch=PHASE,persisted_at=issued,as_of=issued)
    policy=old['temporal_policy'];snapshot=build_snapshot([observation],as_of=issued,created_at=issued,
        code_revision=old['code_revision'],config_revision=old['config_revision'],**policy)
    registry=CapabilityRegistry(canonical({k:v for k,v in source['registry'].items() if k!='registry_id'}))
    numerical=PreparedEnergyInputs(canonical(source['energy_inputs'])).numerical
    args['plan_receipt']=seal_pipeline(snapshot=snapshot,registry=registry,energy_inputs=bind_energy_inputs(numerical,snapshot=snapshot),
        thermal_inputs=None,thermal_runtime=None,coordination=dict(schema='earthship-shadow-coordination/v1',snapshotId=snapshot.snapshot_id,horizonHours=horizon,baseline_soc_floor=None,facts={}),
        config={**source['config'],'horizon_hours':horizon},now=issued,runtime_manifest=args['plan_runtime_manifest'])
    ref=snapshot.to_dict()['domains']['energy']['battery_soc']['evidence'];forecast=json.loads(args['forecast_source']['raw']);forecast['issuedAt']=issued.isoformat()
    forecast['energySocOrigin']=dict(version=1,assessedAtMs=int(issued.timestamp()*1000),recordedAtMs=int(instant(ref['received_at']).timestamp()*1000),
        validUntilMs=int(instant(ref['valid_until']).timestamp()*1000),streamEpoch=ref['source_epoch'],evidenceSha256=ref['digest'],socPct=100.)
    source=args['forecast_source'];source['raw']=json.dumps(forecast);source['sha256']=sha256(source['raw'].encode()).hexdigest();source['persisted_at']=(issued+timedelta(seconds=1)).isoformat()
    result=scoring_api().seal_energy_outcomes(**args)['output']
    assert result['status']=='scored' and result['actual_min_soc_pct']==80
    assert result['daily_model_target']['window_end']==args['night_source']['assessment']['window_end']
    assert result['outcome_within_planner_horizon'] is False
    assert result['planner_horizon_hours']==horizon and result['automatic_actuation'] is False
