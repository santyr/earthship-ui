"""Declared resource drift never becomes measured causal or actuator authority."""
import importlib
from datetime import timedelta
from pathlib import Path
import pytest
from household.codec import canonical,identity
from household.intents import build_intent
from test_household_planning import setup,context,api as planning
from test_household_intents import document
from local_measurement_test_support import NOW

PLAN_RUNTIME={'household/planning.py':'a'*64}
RESOURCE_RUNTIME={'household/resources.py':'b'*64}


def api():return importlib.import_module('household.resources')

def scales():return dict(batteryKwh=2.,socPct=10.,thermalF=5.,water=100.,wearCost=1.,comfortDegreeHours=10.,curtailmentKwh=2.)

def original(effects=None):
    snap,registry=setup();effects=effects or [dict(batteryKwh=-2.,socPct=0.,thermalF=-5.,water=None,wearCost=1.),dict(batteryKwh=2.,socPct=0.,thermalF=5.,water=None,wearCost=1.)]
    items=[];ref=snap.to_dict()['domains']['energy']['battery_soc']['evidence']['digest']
    for device,effect in zip(('dishwasher','shureflo'),effects):
        items.append(build_intent(document(snap,type='SET_NIGHT_LOAD_DEVICE',parameters={'device':device,'command':'OFF'},evidenceRefs=[ref],predictedEffects=effect),snapshot=snap,now=NOW))
    return planning().seal_plan(snapshot=snap,registry=registry,candidates=items,coordination=context(snap),utilities={item.intent_id:10. for item in items},now=NOW,reserve_soc=10.,horizon_hours=24,runtime_manifest=PLAN_RUNTIME,model_refs=[],forecast_ref=None)

def seal(plan=None,**changes):
    args=dict(plan_receipt=original() if plan is None else plan,scales=scales(),orders=[],assessed_at=NOW,plan_runtime_manifest=PLAN_RUNTIME,analysis_runtime_manifest=RESOURCE_RUNTIME)
    args.update(changes);return api().seal_resources(**args)


def test_vectors_preserve_units_and_unknown_dimensions():
    result=seal();vectors=result['output']['candidate_vectors']
    assert len(vectors)==2
    assert {row['dimensions']['batteryKwh']['normalized'] for row in vectors}=={-1.,1.}
    assert all(row['dimensions']['batteryKwh']['unit']=='kWh' for row in vectors)
    assert all(row['dimensions']['water']['value'] is None for row in vectors)
    assert all(row['dimensions']['comfortDegreeHours']['normalized'] is None for row in vectors)
    assert result['output']['action_effects_qualified'] is False and result['output']['automatic_actuation'] is False


def test_cancellation_cannot_hide_intermediate_excursions():
    plan=original();ids=[row['intent']['intentId'] for row in plan['inputs']['candidates']]
    effects={row['intent']['intentId']:row['intent']['predictedEffects']['batteryKwh'] for row in plan['inputs']['candidates']}
    order=sorted(ids,key=effects.get)
    result=seal(plan,orders=[{'name':'consume_then_gain','intent_ids':order},{'name':'gain_then_consume','intent_ids':list(reversed(order))}])
    first,second=result['output']['order_experiments']
    a=first['dimensions']['batteryKwh'];b=second['dimensions']['batteryKwh']
    assert a['net_change']==b['net_change']==0.
    assert a['min_prefix']==-2. and a['max_prefix']==0.
    assert b['min_prefix']==0. and b['max_prefix']==2.
    assert a['gross_movement']==b['gross_movement']==4.
    assert first['prefixes'][0]['dimensions']['batteryKwh']['normalized']==-1.


def test_unknown_contribution_does_not_become_zero_or_favorable():
    plan=original([dict(batteryKwh=None,socPct=0.,thermalF=None,water=None,wearCost=1.),dict(batteryKwh=2.,socPct=0.,thermalF=None,water=None,wearCost=1.)])
    ids=[row['intent']['intentId'] for row in plan['inputs']['candidates']]
    result=seal(plan,orders=[{'name':'declared_candidate_experiment','intent_ids':ids}]);dim=result['output']['order_experiments'][0]['dimensions']['batteryKwh']
    assert dim['net_change'] is None and dim['min_prefix'] is None and dim['gross_movement'] is None
    assert dim['known_contribution']==2. and len(dim['unknown_intent_ids'])==1


def test_empty_optional_schedule_is_explicit_increment_not_known_baseline():
    plan=original();plan=planning().seal_plan(snapshot=setup()[0],registry=setup()[1],candidates=[],coordination=context(setup()[0]),utilities={},now=NOW,reserve_soc=10.,horizon_hours=24,runtime_manifest=PLAN_RUNTIME,model_refs=[],forecast_ref=None)
    result=seal(plan)
    assert result['output']['selected_order']['dimensions']['water']['net_change']==0.
    assert result['output']['basis']=='additional_declared_optional_effects'
    assert result['output']['household_baseline_qualified'] is False


@pytest.mark.parametrize('bad',[0,-1,True,float('inf'),1e-12])
def test_bad_scale_refused(bad):
    with pytest.raises(ValueError):seal(scales={**scales(),'water':bad})


@pytest.mark.parametrize('bad',[[{'name':'bad','intent_ids':['f'*64]}],[{'name':'selected','intent_ids':[]}],[{'name':'duplicate','intent_ids':[]}]*2,[{'name':str(i),'intent_ids':[]} for i in range(17)]])
def test_invalid_or_unbounded_orders_refused(bad):
    with pytest.raises(ValueError):seal(orders=bad)


def test_pure_replay_is_identical_and_performs_no_reads(monkeypatch):
    result=seal();import builtins
    def forbidden(*a,**k):pytest.fail('read inside resource replay')
    monkeypatch.setattr(builtins,'open',forbidden);monkeypatch.setattr(Path,'read_bytes',forbidden)
    assert api().replay_resources(result,plan_runtime_manifest=PLAN_RUNTIME,analysis_runtime_manifest=RESOURCE_RUNTIME)==result


@pytest.mark.parametrize('damage',['output','scales','order','plan','runtime','extra'])
def test_resealed_or_runtime_tampering_refused(damage):
    result=seal();runtime=RESOURCE_RUNTIME
    if damage=='output':result['output']['action_effects_qualified']=True
    elif damage=='scales':result['inputs']['scales']['water']=999
    elif damage=='order':result['inputs']['orders']=[{'name':'added','intent_ids':[]}]
    elif damage=='plan':result['inputs']['plan_receipt']['plan']['selected_intent_ids']=[]
    elif damage=='runtime':runtime={'household/resources.py':'c'*64}
    else:result['owner_authority']=True
    result['receipt_sha256']=identity({key:value for key,value in result.items() if key!='receipt_sha256'})
    with pytest.raises(ValueError):api().replay_resources(result,plan_runtime_manifest=PLAN_RUNTIME,analysis_runtime_manifest=runtime)


def test_future_original_plan_assessment_refused():
    with pytest.raises(ValueError):seal(assessed_at=NOW-timedelta(seconds=1))
