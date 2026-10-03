"""Offline exact-body and output checks for the uninstalled display writer."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'openhab/file-config/automation/js/battery-icon.js'
BASELINE = '834544eb8a9648a6c3082a8a135b3d22b5ef5ae0922a86fb9ee3e4f4fb110e2f'
BEGIN = '// BEGIN EXACT MANAGED ACTION\n'
END = '\n// END EXACT MANAGED ACTION'


def test_exact_original_action_and_rehearsal_contract():
    source = SOURCE.read_text()
    body = source.split(BEGIN)[1].split(END)[0]
    assert sha256(body.encode()).hexdigest() == BASELINE
    assert source.count(BEGIN) == source.count(END) == 1
    spec = importlib.util.spec_from_file_location('battery_display_qualifier',
        ROOT / 'scripts/qualify-season-rule-provider.py')
    q = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = q
    spec.loader.exec_module(q)
    config = q.RULES['battery-icon']
    assert config.uid == 'UpdateBatteryIcon'
    assert config.source == SOURCE and config.baseline == BASELINE
    assert config.triggers == (('timer.GenericCronTrigger',
                               (('cronExpression', '0/30 * * * * ?'),)),)
    assert b'BatteryIcon' in config.items and b'BatteryChargingStatus' in config.items
    spec = importlib.util.spec_from_file_location('battery_display_migration',
        ROOT / 'scripts/migrate-season-countdown-rule.py')
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    candidate = m.RULES['battery-icon']
    assert candidate.source == SOURCE
    assert candidate.source_sha == sha256(SOURCE.read_bytes()).hexdigest()
    assert candidate.script_sha == BASELINE and candidate.triggers == config.triggers
    assert candidate.outputs == ('BatteryIcon', 'BatteryChargingStatus')
    assert not m.RELEASE_READY['battery-icon']
    assert not candidate.outputs_must_hold


def test_original_and_file_outputs_match_at_boundaries_and_across_hysteresis():
    # No mocks of the algorithm: execute both actual JavaScript bodies. Only
    # openHAB's Item/registration APIs are replaced; no network or household I/O.
    runner = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
const original = source.split('// BEGIN EXACT MANAGED ACTION\n')[1]
                       .split('\n// END EXACT MANAGED ACTION')[0];
const quiet = {warn(){}, info(){}};
function fixture(soc, current, charging, icon) {
  const writes = [], state = {BMS_SOC:soc, DCData_Current:current,
                             BatteryChargingStatus:charging, BatteryIcon:icon};
  return {writes, state, items:{getItem(name){
    assert(Object.hasOwn(state,name), 'undeclared Item access');
    return {get state(){return state[name]}, postUpdate(value){
      assert(['BatteryIcon','BatteryChargingStatus'].includes(name));
      writes.push([name,value]); state[name]=value;
    }};
  }}};
}
function executions(f, candidate){
  const ctx = {items:f.items, console:quiet};
  if (!candidate) return () => vm.runInNewContext(original,ctx);
  let rule;
  ctx.require = name => {assert.equal(name,'openhab'); return {
    items:f.items, rules:{JSRule(value){assert.equal(rule,undefined); rule=value}},
    triggers:{GenericCronTrigger(cron){return {cron}}}
  }};
  vm.runInNewContext(source,ctx);
  assert.equal(rule.id,'UpdateBatteryIcon');
  assert.equal(rule.name,'Update Battery Icon');
  assert.deepEqual(rule.triggers,[{cron:'0/30 * * * * ?'}]);
  return rule.execute;
}
let cases=0;
for(const soc of ['NULL','UNDEF','NaN','invalid',null,0,5,5.1,10,10.1,20,
                   30,40,50,60,70,80,90,97,97.1,100,'75 %']) {
  for(const current of ['NULL','UNDEF','invalid',null,-1,0,0.99,1,1.01,2.5,2.51,'3 A']) {
    for(const status of ['ON','OFF']) {
      const a=fixture(soc,current,status,'iconify:mdi:battery-70');
      const b=fixture(soc,current,status,'iconify:mdi:battery-70');
      executions(a,false)(); executions(b,true)();
      assert.deepEqual(b.writes,a.writes); assert.deepEqual(b.state,a.state);
      assert(b.writes.every(([name]) => ['BatteryIcon','BatteryChargingStatus'].includes(name)));
      cases++;
    }
  }
}
const f=fixture(75,2.5,'OFF','iconify:mdi:battery-70');
const run=executions(f,true);
run(); assert.equal(f.state.BatteryChargingStatus,'OFF');
f.state.DCData_Current=2.51; run(); assert.equal(f.state.BatteryChargingStatus,'ON');
f.state.DCData_Current=1; run(); assert.equal(f.state.BatteryChargingStatus,'ON');
f.state.DCData_Current=0.99; run(); assert.equal(f.state.BatteryChargingStatus,'OFF');
const count=f.writes.length; run(); assert.equal(f.writes.length,count);
f.state.BMS_SOC='UNDEF'; f.state.BatteryChargingStatus='ON'; run();
assert.equal(f.state.BatteryIcon,'iconify:mdi:battery-unknown');
assert.equal(f.state.BatteryChargingStatus,'ON'); // preserve legacy invalid-SoC behavior
console.log(JSON.stringify({cases,hysteresis:true,changed_only:true,invalid_soc_preserved:true}));
'''
    run = subprocess.run(['node', '-e', runner, str(SOURCE)],
                         capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(run.stdout) == {'cases': 528, 'hysteresis': True,
                                      'changed_only': True, 'invalid_soc_preserved': True}
