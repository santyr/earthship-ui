"""Expanded original power facts do not imply bank or household-load knowledge."""
import importlib,json
from hashlib import sha256
from datetime import timedelta
from pathlib import Path
import pytest
from household.codec import identity,canonical
from test_household_replay import bundle,build as base_build
from test_household_capabilities import originals
from test_forecast_pre_dusk import NOW

RUNTIME={'fixture.py':'d'*64}
POWER_EPOCH='00000000-0000-0000-0000-000000000002'
AC_EPOCH='00000000-0000-0000-0000-000000000003'


def api():return importlib.import_module('household.power_snapshot')

def source(kind='power',**changes):
    milliseconds=lambda at:int(at.timestamp()*1000)
    fields={'battery.dc_power_w':-500,'pv.input_power_w':2000,'pv.output_power_w':1900} if kind=='power' else {'inverter.ac_output_w':1000}
    raw=json.dumps(dict(version=1,streamEpoch=POWER_EPOCH if kind=='power' else AC_EPOCH,sequence=1,recordedAt=milliseconds(NOW-timedelta(seconds=1)),fields={name:dict(status='valid',reason='ok',observedAt=milliseconds(NOW-timedelta(seconds=5)),validUntil=milliseconds(NOW+timedelta(seconds=115 if kind=='power' else 25)),watts=value) for name,value in fields.items()},**({} if kind=='power' else {'basis':'inverter_output'})))
    return dict(kind=kind,source_identity='Power_Evidence_JSON' if kind=='power' else 'Inverter_AC_Evidence_JSON',expected_epoch=POWER_EPOCH if kind=='power' else AC_EPOCH,expected_sha256=sha256(raw.encode()).hexdigest(),persisted_at=NOW.isoformat(),raw=raw,**changes)


def inputs():
    return dict(schema='earthship-household-power-inputs/v1',base_inputs=bundle(),power_sources=[source(),source('inverter_ac')],power_policy=dict(requirements={'current_energy':['battery_soc','battery_power_w','pv_output_power_w','inverter_output_w'],'full_energy':['usable_battery_kwh','physical_bank_epoch','estimated_load_w']},max_age_seconds={'battery_power_w':120,'pv_input_power_w':120,'pv_output_power_w':120,'inverter_output_w':30},max_skew_seconds=60))


def build(value=None):
    managed,ownership=originals();return api().compile_power_inputs(inputs() if value is None else value,managed=managed,ownership=ownership,code_revision='c'*40,runtime_manifest=RUNTIME)


def test_four_fields_qualified_with_one_shared_clock_and_explicit_unknowns():
    result=build();snap=result['snapshot'];energy=snap['domains']['energy']
    assert snap['schema']=='earthship-household-snapshot/v2'
    assert energy['battery_power_w']['value']==-500 and energy['pv_output_power_w']['value']==1900
    assert energy['inverter_output_w']['value']==1000
    assert energy['estimated_load_w']['value'] is None and energy['physical_bank_epoch']['value'] is None
    assert snap['domains']['authority']['owner_rule_availability']['value'] is None
    assert snap['completeness']['current_energy'] is True and snap['completeness']['full_energy'] is False
    assert snap['as_of']==bundle()['as_of'] and snap['planner_authority']=='none'
    assert result['automatic_actuation'] is False


def test_field_specific_unavailable_does_not_erase_other_fresh_fields():
    value=inputs();row=value['power_sources'][0];raw=json.loads(row['raw']);raw['fields']['pv.input_power_w']={'status':'unavailable','reason':'input_unavailable','observedAt':None,'validUntil':None,'watts':None};row['raw']=json.dumps(raw);row['expected_sha256']=sha256(row['raw'].encode()).hexdigest()
    energy=build(value)['snapshot']['domains']['energy']
    assert energy['pv_input_power_w']['value'] is None and energy['pv_output_power_w']['value']==1900


@pytest.mark.parametrize('damage',['epoch','null','malformed','expired','age','future'])
def test_source_barriers_and_clocks_cannot_authorize_values(damage):
    value=inputs();row=value['power_sources'][0]
    if damage=='epoch':row['expected_epoch']=AC_EPOCH
    elif damage=='null':row['raw']=None;row['expected_sha256']=None
    elif damage=='malformed':row['raw']='{}';row['expected_sha256']=sha256(row['raw'].encode()).hexdigest()
    elif damage=='expired':value['base_inputs']['as_of']=(NOW+timedelta(seconds=115)).isoformat();value['base_inputs']['created_at']=value['base_inputs']['as_of']
    elif damage=='age':value['power_policy']['max_age_seconds']['battery_power_w']=1
    else:row['persisted_at']=(NOW+timedelta(seconds=1)).isoformat()
    snap=build(value)['snapshot'];assert snap['domains']['energy']['battery_power_w']['value'] is None
    assert snap['completeness']['current_energy'] is False


@pytest.mark.parametrize('damage',['digest','identity','duplicate','extra','unknown_kind','bad_policy'])
def test_closed_original_context_refuses_ambiguity(damage):
    value=inputs()
    if damage=='digest':value['power_sources'][0]['expected_sha256']='f'*64
    elif damage=='identity':value['power_sources'][0]['source_identity']='arbitrary_item'
    elif damage=='duplicate':value['power_sources'].append(value['power_sources'][0])
    elif damage=='extra':value['credential']='do-not-export'
    elif damage=='unknown_kind':value['power_sources'][0]['kind']='load'
    else:value['power_policy']['max_skew_seconds']=True
    with pytest.raises(ValueError):build(value)


def test_skew_blocks_combined_capability_but_preserves_individual_values():
    value=inputs();value['power_policy']['max_skew_seconds']=1
    snap=build(value)['snapshot'];assert snap['domains']['energy']['battery_power_w']['value']==-500
    assert snap['completeness']['current_energy'] is False and snap['capability_reasons']['current_energy']=='source_skew'


def test_v1_receipt_identity_and_returned_values_are_unchanged_and_immutable():
    before=base_build();value=inputs();result=build(value)
    value['power_sources'][0]['raw']='changed';snap=api().PowerSnapshot(canonical({key:item for key,item in result['snapshot'].items() if key!='snapshot_id'}))
    edited=snap.to_dict();edited['domains']['energy']['battery_power_w']['value']=0
    assert snap.to_dict()['domains']['energy']['battery_power_w']['value']==-500
    assert base_build()==before


def test_original_power_snapshot_replays_without_reads(monkeypatch):
    result=build();import builtins
    def forbidden(*a,**k):pytest.fail('read inside snapshot replay')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden)
    assert api().replay_power_snapshot(result,runtime_manifest=RUNTIME)==result


def test_resealed_derived_result_cannot_change_original_snapshot():
    result=build();result['snapshot']['domains']['energy']['estimated_load_w']['value']=1000
    result['receipt_sha256']=identity({key:value for key,value in result.items() if key!='receipt_sha256'})
    with pytest.raises(ValueError):api().replay_power_snapshot(result,runtime_manifest=RUNTIME)
