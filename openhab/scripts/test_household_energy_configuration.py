"""Declared configuration remains original context, not physical calibration."""
import importlib,json
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import pytest
from household.codec import canonical,identity

AT=datetime(2026,10,11,22,40,tzinfo=timezone.utc)
BANK={'version':1,'timezone':'America/Denver','epochs':[
    {'id':'historic','start_local_date':None,'end_local_date_exclusive':'2026-07-19','current_analytics':False,'nominal_usable_kwh':None},
    {'id':'discover_4_module_2026','start_local_date':'2026-07-19','end_local_date_exclusive':None,'current_analytics':True,'nominal_usable_kwh':20.48,'nominal_capacity_ah':400.,'battery':{'declared_modules':4}}]}
TOPOLOGY={'version':1,'policy':'qualified_inverter_ac_output_v1','item_name':'Inverter_AC_Evidence_JSON',
    'cutover':'2026-09-23T20:55:12.284000Z','topology':{'basis':'inverter_only_no_bypass_or_generator',
    'effective_from':'2026-09-23T20:55:12.284000Z','effective_until':None}}


def api():return importlib.import_module('household.energy_configuration')


def args():return dict(bank_config_raw=json.dumps(BANK,indent=2),ac_policy_raw=json.dumps(TOPOLOGY,indent=2),
    bank_available_at=AT-timedelta(seconds=2),topology_available_at=AT-timedelta(seconds=1),as_of=AT,created_at=AT+timedelta(seconds=2))


def prepare(**changes):return api().prepare_energy_configuration(**{**args(),**changes})


def reseal(body):
    body['configuration_sha256']=identity({k:v for k,v in body.items() if k!='configuration_sha256'})
    return canonical(body)


def test_exact_original_configuration_and_declared_capacity_are_retained():
    context=prepare();body=context.to_dict();out=api().project_energy_configuration(context)
    assert body['bank_source']['raw']==args()['bank_config_raw']
    assert body['bank_source']['sha256']==sha256(args()['bank_config_raw'].encode()).hexdigest()
    assert body['bank_source']['source_identity']=='Solar_PV/config/system-epochs.json'
    assert body['load_topology_source']['source_identity']=='Solar_PV/config/ac-evidence.json'
    assert out['bank']=={'status':'declared','reason':None,'epoch_id':'discover_4_module_2026',
        'effective_from':'2026-07-19T06:00:00+00:00','effective_until':None,
        'nominal_usable_kwh':20.48,'nominal_capacity_ah':400.,'basis':'original_declared_configuration','physical_calibration_qualified':False}
    assert out['load_topology']['status']=='attested' and out['load_topology']['valid_at_origin'] is True
    assert out['load_topology']['effective_until'] is None
    assert out['usable_energy_qualified'] is False and out['action_effects_qualified'] is False and out['automatic_actuation'] is False


@pytest.mark.parametrize('missing',['bank','topology','both'])
def test_missing_source_preserves_the_other_original(missing):
    changes={}
    if missing in ('bank','both'):changes['bank_config_raw']=None
    if missing in ('topology','both'):changes['ac_policy_raw']=None
    out=api().project_energy_configuration(prepare(**changes))
    assert out['bank']['status']==('unavailable' if missing in ('bank','both') else 'declared')
    assert out['load_topology']['status']==('unavailable' if missing in ('topology','both') else 'attested')
    for kind in ('bank','load_topology'):
        if out[kind]['status']=='unavailable':assert out[kind]['reason']=='missing_source'


@pytest.mark.parametrize('damage',['overlap','two_current','invalid_capacity','future_epoch','ended_epoch','malformed'])
def test_invalid_or_out_of_window_bank_is_not_current_capacity(damage):
    bank=json.loads(json.dumps(BANK))
    if damage=='overlap':bank['epochs'][0]['end_local_date_exclusive']='2026-07-20'
    elif damage=='two_current':bank['epochs'][0]['current_analytics']=True
    elif damage=='invalid_capacity':bank['epochs'][1]['nominal_usable_kwh']=True
    elif damage=='future_epoch':bank['epochs'][1]['start_local_date']='2026-10-12'
    elif damage=='ended_epoch':bank['epochs'][1]['end_local_date_exclusive']='2026-10-11'
    raw='not JSON' if damage=='malformed' else json.dumps(bank)
    out=api().project_energy_configuration(prepare(bank_config_raw=raw))
    assert out['bank']['status']=='unavailable' and 'nominal_usable_kwh' not in out['bank']
    assert out['load_topology']['status']=='attested'


@pytest.mark.parametrize('damage',['wrong_basis','wrong_item','before_cutover','future_period','ended_period'])
def test_topology_does_not_authorize_load_outside_its_original_contract(damage):
    policy=json.loads(json.dumps(TOPOLOGY))
    if damage=='wrong_basis':policy['topology']['basis']='inferred_from_watts'
    elif damage=='wrong_item':policy['item_name']='BMS_SOC'
    elif damage=='before_cutover':policy['topology']['effective_from']='2026-09-22T20:55:12+00:00'
    elif damage=='future_period':policy['topology']['effective_from']='2026-10-12T00:00:00+00:00'
    else:policy['topology']['effective_until']=AT.isoformat()
    out=api().project_energy_configuration(prepare(ac_policy_raw=json.dumps(policy)))
    assert out['load_topology']['status']=='unavailable' and out['bank']['status']=='declared'


@pytest.mark.parametrize('damage',['future_available','created_before','created_late','unaware','oversized_bank','oversized_topology'])
def test_collection_clocks_and_original_byte_bounds_are_strict(damage):
    changes={}
    if damage=='future_available':changes['bank_available_at']=AT+timedelta(seconds=1)
    elif damage=='created_before':changes['created_at']=AT-timedelta(seconds=1)
    elif damage=='created_late':changes['created_at']=AT+timedelta(seconds=16)
    elif damage=='unaware':changes['as_of']=AT.replace(tzinfo=None)
    elif damage=='oversized_bank':changes['bank_config_raw']='x'*65537
    else:changes['ac_policy_raw']='x'*4097
    with pytest.raises(ValueError):prepare(**changes)


@pytest.mark.parametrize('damage',['digest','identity','null_digest','extra'])
def test_resealed_context_requires_exact_fixed_original_sources(damage):
    body=prepare().to_dict();row=body['bank_source']
    if damage=='digest':row['raw']+=' '
    elif damage=='identity':row['source_identity']='different-file.json'
    elif damage=='null_digest':row['raw']=None
    else:body['calibrated']=True
    with pytest.raises(ValueError):api().PreparedEnergyConfiguration(reseal(body))


def test_resealed_invalid_raw_cannot_become_qualified_bank():
    body=prepare().to_dict();row=body['bank_source'];bank=json.loads(row['raw']);bank['epochs'][1]['nominal_usable_kwh']=-1
    row['raw']=json.dumps(bank);row['sha256']=sha256(row['raw'].encode()).hexdigest()
    out=api().project_energy_configuration(api().PreparedEnergyConfiguration(reseal(body)))
    assert out['bank']['status']=='unavailable' and out['usable_energy_qualified'] is False


def test_projection_preserves_originals_and_performs_no_reads(monkeypatch):
    context=prepare();expected=api().project_energy_configuration(context)
    copy=context.to_dict();copy['bank_source']['raw']='changed'
    returned=api().project_energy_configuration(context);returned['bank']['nominal_usable_kwh']=999
    import builtins,psycopg2
    def forbidden(*args,**kwargs):pytest.fail('I/O within frozen configuration boundary')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden);monkeypatch.setattr(psycopg2,'connect',forbidden)
    restored=api().PreparedEnergyConfiguration(canonical(context.to_dict()))
    assert api().project_energy_configuration(restored)==expected


def test_later_projection_rechecks_topology_boundary_without_backdating():
    policy=json.loads(json.dumps(TOPOLOGY));policy['topology']['effective_until']=(AT+timedelta(seconds=10)).isoformat()
    context=prepare(ac_policy_raw=json.dumps(policy))
    assert api().project_energy_configuration(context)['load_topology']['status']=='attested'
    assert api().project_energy_configuration(context,as_of=AT+timedelta(seconds=10))['load_topology']['status']=='unavailable'
    with pytest.raises(ValueError):api().project_energy_configuration(context,as_of=AT-timedelta(seconds=1))


@pytest.mark.parametrize('source',['bank','topology'])
def test_bounded_nested_json_failure_preserves_independent_source(source):
    depth=4000 if source=='bank' else 2000
    raw='{"nested":'+ '['*depth+'0'+']'*depth+'}'
    context=prepare(**{('bank_config_raw' if source=='bank' else 'ac_policy_raw'):raw})
    import sys
    previous=sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(1000)
        out=api().project_energy_configuration(context)
    finally:sys.setrecursionlimit(previous)
    broken='bank' if source=='bank' else 'load_topology'
    other='load_topology' if source=='bank' else 'bank'
    assert out[broken]=={'status':'unavailable','reason':'invalid_configuration'}
    assert out[other]['status']==('attested' if other=='load_topology' else 'declared')
    assert context.to_dict()[('bank_source' if source=='bank' else 'load_topology_source')]['raw']==raw


def test_bank_date_overflow_preserves_valid_topology():
    bank=json.loads(json.dumps(BANK));bank['epochs'][1]['start_local_date']='9999-12-31'
    out=api().project_energy_configuration(prepare(bank_config_raw=json.dumps(bank)))
    assert out['bank']=={'status':'unavailable','reason':'invalid_configuration'}
    assert out['load_topology']['status']=='attested'


@pytest.mark.parametrize('source',['bank','topology'])
def test_source_local_parser_recursion_failure_keeps_other_projection(source,monkeypatch):
    context=prepare();raw=context.to_dict()['bank_source' if source=='bank' else 'load_topology_source']['raw']
    original=api().loads
    def bounded_parser(value):
        if value==raw:raise RecursionError('parser nesting limit')
        return original(value)
    monkeypatch.setattr(api(),'loads',bounded_parser)
    out=api().project_energy_configuration(context)
    assert out['bank' if source=='bank' else 'load_topology']=={'status':'unavailable','reason':'invalid_configuration'}
    assert out['load_topology' if source=='bank' else 'bank']['status']==('attested' if source=='bank' else 'declared')
