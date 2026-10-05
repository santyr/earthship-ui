"""Execute the actual fan rule offline; only the openHAB API is substituted."""
from pathlib import Path
import subprocess

SOURCE = Path(__file__).resolve().parents[1] / 'openhab/file-config/automation/js/south-planter-fan.js'


def test_threshold_safety_expiry_retry_and_exclusive_actuator():
    runner = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
let clock=1800000000000,rule,writes=[],attempts=0,fail=false,missing=new Set();
const epoch='61b2c967-b217-429e-840f-eebf68a36da0';
function receipt(soc=98){return {version:1,streamEpoch:epoch,recordedAt:clock-1000,
 status:'valid',reason:'ok',observedAt:clock-2000,scaleObservedAt:clock-1000,
 validUntil:clock-2000+120000,soc}}
const state={BMS_SOC_Evidence_JSON:'',BMS_Comms_Status:'OK',
 SchneiderTelemetry_Status:'OK,chargeState=CHARGING,ages=dc:1/120',
 DCData_Voltage:'53.4 V',SouthOutlet_Outlet1_Switch:'OFF'};
function reset(soc=98,fan='OFF') {clock+=31000;state.BMS_SOC_Evidence_JSON=JSON.stringify(receipt(soc));
 state.BMS_Comms_Status='OK';state.SchneiderTelemetry_Status='OK,chargeState=CHARGING';
 state.DCData_Voltage='53.4 V';state.SouthOutlet_Outlet1_Switch=fan;writes=[];attempts=0;missing.clear();fail=false;}
const ctx={Date:class extends Date {static now(){return clock}},console:{info(){},warn(){},error(){}},
 require(name){assert.equal(name,'openhab');return {rules:{JSRule(r){assert.equal(rule,undefined);rule=r}},
 triggers:{ItemStateUpdateTrigger(itemName){return {type:'update',itemName}},
 ItemStateChangeTrigger(itemName){return {type:'change',itemName}},GenericCronTrigger(cron){return {type:'cron',cron}}},
 items:{getItem(n){assert(Object.hasOwn(state,n),'undeclared input '+n);if(missing.has(n))throw Error('missing');
 return {get state(){return state[n]},sendCommand(value){assert.equal(n,'SouthOutlet_Outlet1_Switch');
 assert(['ON','OFF'].includes(value));attempts++;if(fail)throw Error('transport');writes.push([n,value]);}}}}}}};
vm.runInNewContext(source,ctx);
assert.equal(rule.id,'hex_south_planter_fan');
assert(rule.triggers.some(t=>t.type==='update'&&t.itemName==='BMS_SOC_Evidence_JSON'));
assert(rule.triggers.some(t=>t.type==='cron'&&t.cron==='0/30 * * * * ?'));
for(const soc of [0,45,90,97,97.999,98,98.001,99,100]) {
 reset(soc,soc>=98?'OFF':'ON');rule.execute();assert.equal(writes.at(-1)[1],soc>=98?'ON':'OFF');
 state.SouthOutlet_Outlet1_Switch=soc>=98?'ON':'OFF';writes=[];rule.execute();assert.equal(writes.length,0);
}
const mutations=[r=>r.soc=-1,r=>r.soc=101,r=>r.soc='99',r=>r.status='stale',r=>r.reason='invalid',
 r=>r.version=2,r=>r.streamEpoch='invalid',r=>r.recordedAt=clock+1,r=>r.observedAt=0,
 r=>r.scaleObservedAt=0,r=>r.observedAt=r.recordedAt+1,r=>r.scaleObservedAt=r.recordedAt+1,
 r=>r.validUntil++,r=>r.extra='untrusted',r=>delete r.soc,
 r=>{r.observedAt=clock-120000;r.scaleObservedAt=clock-1000;r.validUntil=clock;}];
for(const mutate of mutations){reset(99,'ON');let r=receipt(99);mutate(r);state.BMS_SOC_Evidence_JSON=JSON.stringify(r);rule.execute();assert.equal(writes.at(-1)[1],'OFF');}
for(const raw of ['NULL','UNDEF','not JSON','[]',' '.repeat(2049),JSON.stringify(receipt(99))+'\n']) {
 reset(99,'ON');state.BMS_SOC_Evidence_JSON=raw;rule.execute();assert.equal(writes.at(-1)[1],'OFF');}
for(const value of ['STALE','NO-DATA','NULL']){reset(99,'ON');state.BMS_Comms_Status=value;rule.execute();assert.equal(writes.at(-1)[1],'OFF');}
for(const value of ['STALE,ages=dc:999','NULL','OKAY','OK']){reset(99,'ON');state.SchneiderTelemetry_Status=value;rule.execute();assert.equal(writes.at(-1)[1],'OFF');}
for(const value of ['NULL','UNDEF','NaN','39.99 V','60.01 V','53 garbage','53 V garbage','53']){
 reset(99,'ON');state.DCData_Voltage=value;rule.execute();assert.equal(writes.at(-1)[1],'OFF');}
for(const n of ['BMS_SOC_Evidence_JSON','BMS_Comms_Status','SchneiderTelemetry_Status','DCData_Voltage']){
 reset(99,'ON');missing.add(n);rule.execute();assert.equal(writes.at(-1)[1],'OFF');}
// Receipt expiry must stop an already running fan without any source update.
reset(99,'ON');clock=receipt(99).validUntil;rule.execute();assert.equal(writes.at(-1)[1],'OFF');
// Deduplicate pending commands, allow a safety OFF immediately, then bounded retry.
reset(99);rule.execute();rule.execute();assert.equal(writes.length,1);
state.SouthOutlet_Outlet1_Switch='ON';state.BMS_Comms_Status='STALE';rule.execute();assert.equal(writes.at(-1)[1],'OFF');
const count=writes.length;rule.execute();assert.equal(writes.length,count);clock+=30000;rule.execute();assert.equal(writes.length,count+1);
reset(99,'UNDEF');rule.execute();assert.equal(writes.at(-1)[1],'ON');
reset(99);fail=true;assert.doesNotThrow(()=>rule.execute());rule.execute();assert.equal(attempts,1);fail=false;clock+=30000;
state.BMS_SOC_Evidence_JSON=JSON.stringify(receipt(99));rule.execute();assert.equal(writes.at(-1)[1],'ON');
state.SouthOutlet_Outlet1_Switch='ON';state.BMS_Comms_Status='STALE';rule.execute();writes=[];clock-=1000;rule.execute();assert.equal(writes.at(-1)[1],'OFF');
console.log('threshold, source validity, expiry, safety, exclusive output and bounded retries pass');
'''
    result = subprocess.run(['node', '-e', runner, str(SOURCE)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
