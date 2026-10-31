import { existsSync, readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = new URL('../../openhab/file-config/automation/js/shade-provider-history.js', import.meta.url);
const mapping = new URL('../../openhab/file-config/shade-provider-history.mapping.example.json', import.meta.url);
const entry = (slot=1, statusItem=`Shade_${String(slot).padStart(2,'0')}_ProviderStatus`) => ({
  slot, thingUID:'mqtt:topic:synthetic:shadeProvider', statusItem,
});
function factory() {
  expect(existsSync(source)).toBe(true);
  const module={ exports:{} };
  vm.runInNewContext(readFileSync(source,'utf8'),{ module, console,
    require:() => { throw new Error('prepared empty collector touched runtime'); } });
  return module.exports;
}
function fixture(current='ONLINE', type='String') {
  const updates=[],definitions=[],commands=[],statuses=new Map([[entry().thingUID,current]]);
  const api={
    things:{getThing:uid=>{ if(!statuses.has(uid))throw new Error('SECRET registry details'); return {status:statuses.get(uid)}; }},
    items:{getItem:name=>({type,postUpdate:value=>updates.push({name,value}),sendCommand:value=>commands.push({name,value})})},
    rules:{JSRule:rule=>definitions.push(rule)},
    triggers:{ThingStatusChangeTrigger:uid=>({kind:'thing',uid}),SystemStartlevelTrigger:level=>({kind:'startup',level})},
  };
  return {api,updates,definitions,commands,statuses};
}

describe('prepared provider history observation collector',()=>{
  it('exports callable software with an empty separate mapping and zero default runtime writes',()=>{
    const module=factory();
    expect(module.PREPARED_PROVIDER_HISTORY_MAPPINGS).toEqual([]);
    expect(JSON.parse(readFileSync(mapping,'utf8'))).toEqual([]);
    expect(module.registerShadeProviderHistory({},[])).toEqual([]);
  });
  it.each(['ONLINE','OFFLINE','UNINITIALIZED',null])('reconciles actual startup %s through an unknown barrier',status=>{
    const module=factory(), f=fixture(status);
    module.registerShadeProviderHistory(f.api,[entry()]);
    expect(f.updates).toEqual([{name:entry().statusItem,value:'UNDEF'},
      {name:entry().statusItem,value:status==='ONLINE'||status==='OFFLINE'?status:'UNDEF'}]);
    expect(f.definitions[0].triggers).toEqual([{kind:'thing',uid:entry().thingUID},{kind:'startup',level:100}]);
    expect(f.commands).toEqual([]);
  });
  it('captures an OFFLINE event even if a later ONLINE is already in the registry',()=>{
    const module=factory(), f=fixture(); module.registerShadeProviderHistory(f.api,[entry()]);
    f.updates.length=0;
    f.definitions[0].execute({thingUID:entry().thingUID,newStatus:'OFFLINE'});
    expect(f.updates).toEqual([{name:entry().statusItem,value:'OFFLINE'}]);
    f.definitions[0].execute({thingUID:entry().thingUID,newStatus:'ONLINE'});
    expect(f.updates.at(-1).value).toBe('ONLINE');
    expect(f.commands).toEqual([]);
  });
  it('cannot restore ONLINE from an old event when actual provider is now offline',()=>{
    const module=factory(), f=fixture('OFFLINE'); module.registerShadeProviderHistory(f.api,[entry()]);
    f.updates.length=0; f.definitions[0].execute({thingUID:entry().thingUID,newStatus:'ONLINE'});
    expect(f.updates).toEqual([{name:entry().statusItem,value:'OFFLINE'}]);
  });
  it('withholds unknown/missing sources and ignores foreign event targets',()=>{
    const module=factory(), f=fixture(); f.statuses.clear();
    module.registerShadeProviderHistory(f.api,[entry()]); expect(f.updates.at(-1).value).toBe('UNDEF');
    f.updates.length=0; f.definitions[0].execute({thingUID:'mqtt:topic:synthetic:foreign',newStatus:'ONLINE'});
    expect(f.updates).toEqual([]);
    f.definitions[0].execute({thingUID:entry().thingUID,newStatus:'UNINITIALIZED'});
    expect(f.updates.at(-1).value).toBe('UNDEF');
  });
  it('accepts a shared actual provider with distinct logical slots and status Items',()=>{
    const module=factory(), f=fixture(); module.registerShadeProviderHistory(f.api,[entry(1),entry(2)]);
    expect(f.definitions).toHaveLength(2);
    expect(new Set(f.updates.map(row=>row.name))).toEqual(new Set([entry(1).statusItem,entry(2).statusItem]));
  });
  it.each([0,27,-1,1.5,true,'1'])('refuses invalid slot %s before any runtime writes',slot=>{
    const module=factory(),f=fixture();
    expect(()=>module.registerShadeProviderHistory(f.api,[entry(slot)])).toThrow('invalid_provider_history_mapping');
    expect(f.updates).toEqual([]); expect(f.definitions).toEqual([]);
  });
  it.each(['OverrideSwitch','Greywater_Pump','Shade_01_Command','Shade_*_ProviderStatus'])('refuses non-observational target %s',name=>{
    const module=factory(),f=fixture();
    expect(()=>module.registerShadeProviderHistory(f.api,[entry(1,name)])).toThrow('invalid_provider_history_mapping');
    expect(f.updates).toEqual([]);
  });
  it('requires String targets, unique slots/Items and at most26 explicit mappings',()=>{
    const module=factory();
    for(const rows of [[entry(),entry()],[entry(1),entry(2,entry().statusItem)],Array.from({length:27},(_,index)=>entry(index+1)),
      [{...entry(),thingUID:'mqtt:topic:synthetic:*'}]]) {
      const f=fixture(); expect(()=>module.registerShadeProviderHistory(f.api,rows)).toThrow('invalid_provider_history_mapping');
      expect(f.updates).toEqual([]); expect(f.definitions).toEqual([]);
    }
    const f=fixture('ONLINE','Switch');
    expect(()=>module.registerShadeProviderHistory(f.api,[entry()])).toThrow('provider_history_target_unavailable');
    expect(f.updates).toEqual([]);
  });
  it('reads only the separate closed mapping JSON and refuses owner keys or duplicate keys',()=>{
    const module=factory(), path='/synthetic/private/provider-mapping.json',reads=[];
    const loaded=module.readShadeProviderHistoryMappings(path, value=>{reads.push(value);return JSON.stringify([entry()]);});
    expect(loaded).toEqual([entry()]); expect(reads).toEqual([path]);
    for(const raw of ['[{"slot":1,"slot":2,"thingUID":"mqtt:topic:synthetic:shadeProvider","statusItem":"Shade_01_ProviderStatus"}]',
      JSON.stringify([{...entry(),ownerKey:'must-not-be-a-mapping'}]),'{"mqtt_password":"not-a-mapping"}']) {
      expect(()=>module.readShadeProviderHistoryMappings(path,()=>raw)).toThrow('invalid_provider_history_mapping');
    }
  });
  it('copies its exact target mapping so later mutation cannot redirect updates',()=>{
    const module=factory(),f=fixture(),row=entry(); module.registerShadeProviderHistory(f.api,[row]);
    row.statusItem='OverrideSwitch'; f.updates.length=0;
    f.definitions[0].execute({thingUID:entry().thingUID,newStatus:'OFFLINE',itemName:'OverrideSwitch'});
    expect(f.updates).toEqual([{name:entry().statusItem,value:'OFFLINE'}]); expect(f.commands).toEqual([]);
  });
  it('relies on the preserved JDBC everyChange strategy and defines only26 unlinked example String Items',()=>{
    factory();
    const jdbc=readFileSync(new URL('../../openhab/file-config/persistence/jdbc.persist',import.meta.url),'utf8');
    expect(jdbc).toContain('*, !Shade_RecommendationAutomationSession');
    expect(jdbc).toContain('strategy = everyChange, restoreOnStartup');
    const proposed=readFileSync(new URL('../../openhab/file-config/items/shade-provider-history.items.example',import.meta.url),'utf8');
    expect(proposed.match(/^String Shade_\d{2}_ProviderStatus /gm)).toHaveLength(26);
    expect(proposed).not.toMatch(/channel=|sendCommand|Rollershutter|^Switch /m);
  });
});
