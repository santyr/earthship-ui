from copy import deepcopy
import importlib
from pathlib import Path
import subprocess,sys
import pytest
sys.path.insert(0,str(Path(__file__).parent))


def tools():
    try:return importlib.import_module('sky_diagnostic_items')
    except ModuleNotFoundError:pytest.fail('sky diagnostic guards are not implemented')


def item(name, managed=True):
    d=tools();spec=d.ITEMS[name]
    return {**d.original_item(name),'editable':managed,'state':('condition=NIGHT,reason=night' if spec['type']=='String' else '2026-10-05T20:10:01.123-0600'),
        'metadata':{'stateDescription':{**d.metadata(name),'editable':managed}},
        'stateDescription':{'pattern':spec['pattern'],'readOnly':False,'options':[]}}


@pytest.mark.parametrize('managed',[True,False])
def test_exact_original_descriptors_and_metadata(managed):
    d=tools()
    for name in d.ITEMS:
        d.validate_item(item(name,managed),name,managed=managed)
        row=item(name,managed);row['category']=None;d.validate_item(row,name,managed=managed)


@pytest.mark.parametrize('damage',['type','label','group','tags','unit','metadata-value','pattern','provider','empty','metadata-extra'])
def test_changed_semantics_or_missing_state_are_rejected(damage):
    d=tools();name='SkyCondition_LastEval';row=item(name)
    if damage=='type':row['type']='String'
    elif damage=='label':row['label']='other'
    elif damage=='group':row['groupNames']=[]
    elif damage=='tags':row['tags']=['Status']
    elif damage=='unit':row['unitSymbol']='s'
    elif damage=='metadata-value':row['metadata']['stateDescription']['value']=''
    elif damage=='pattern':row['stateDescription']['pattern']='%s'
    elif damage=='provider':row['editable']=False
    elif damage=='empty':row['state']='UNDEF'
    else:row['metadata']['other']={'value':'extra'}
    with pytest.raises(ValueError):d.validate_item(row,name,managed=True)


@pytest.mark.parametrize('bad',['2026-10-05','2026-10-05T20:10:00','not-a-date','2026-13-40T20:10:00Z'])
def test_datetime_state_requires_native_aware_timestamp(bad):
    d=tools();row=item('SkyCondition_LastEval');row['state']=bad
    with pytest.raises(ValueError):d.validate_item(row,'SkyCondition_LastEval',managed=True)


def test_unlinked_scope_and_exact_definition_operations():
    d=tools();d.validate_links([])
    with pytest.raises(ValueError):d.validate_links([{'itemName':'SkyCondition_LastEval'}])
    for name in d.ITEMS:
        d.allowed_mutation('DELETE','/items/'+name,None)
        d.allowed_mutation('PUT','/items/'+name,d.original_item(name))
        d.allowed_mutation('PUT','/items/'+name+'/metadata/stateDescription',d.metadata(name))
    for method,path,body in [('PUT','/items/SkyCondition/state','NIGHT'),('POST','/rules/sky-condition-calculator/runnow',None),('DELETE','/items/WeatherData_HealthStatus',None)]:
        with pytest.raises(ValueError):d.allowed_mutation(method,path,body)


def test_canonical_definitions_keep_string_datetime_and_exact_patterns():
    d=tools();text=d.SOURCE.read_text()
    for name,spec in d.ITEMS.items():
        assert f'{spec["type"]} {name} "{spec["label"]}" (gWeatherHealth)' in text
        assert 'pattern="'+spec['pattern']+'"' in text
    assert text.count('stateDescription=" "')==2 and 'channel=' not in text


def test_actual_sky_rule_primary_decisions_survive_absent_diagnostics():
    source=Path(__file__).resolve().parents[1]/'openhab/file-config/automation/js/sky-condition-calculator.js'
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');const source=fs.readFileSync(process.argv[1],'utf8');
function run(phase,ratio,health,missing){let rule,writes=[];const states={Sun_SunPhaseName:phase,Sun_TotalRadiation:'100',AmbientWeatherWS2902A_SolarRadiation:String(100*ratio),WeatherData_HealthStatus:health,WeatherData_WH65B_AgeSeconds:'10',MoonPhaseicon:'moon',SunPhaseIcon:'sun',SkyCondition:'NULL',SkyConditionIcon:'NULL',SkyCondition_LastEval:'NULL',SkyCondition_Diagnostic:'NULL'};
const ctx={Date,console:{info(){},debug(){}},require(){return {rules:{JSRule(r){rule=r}},triggers:{ItemStateChangeTrigger(){},GenericCronTrigger(){}},items:{getItem(n){if(missing.includes(n))throw Error('absent');assert(Object.hasOwn(states,n));return {state:states[n],postUpdate(v){writes.push([n,v]);}}}}}}};vm.runInNewContext(source,ctx);assert.doesNotThrow(()=>rule.execute());return writes.filter(([n])=>n==='SkyCondition'||n==='SkyConditionIcon');}
for(const [phase,ratio,health] of [['NIGHT',0,'OK'],['DAY',0.1,'OK'],['DAY',0.5,'OK'],['DAY',1,'OK'],['DAY',1,'STALE']]){const original=run(phase,ratio,health,[]);for(const missing of [['SkyCondition_Diagnostic'],['SkyCondition_LastEval'],['SkyCondition_Diagnostic','SkyCondition_LastEval']])assert.deepStrictEqual(run(phase,ratio,health,missing),original);}
'''
    result=subprocess.run(['node','-e',script,str(source)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
