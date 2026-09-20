import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { expect, it } from 'vitest';

const source = readFileSync(new URL('../../scripts/openhab-power-install-action.js', import.meta.url), 'utf8');
const resources = JSON.parse(readFileSync(new URL('../../openhab/power-observation-resources.json', import.meta.url), 'utf8'));
const evidence = JSON.parse(readFileSync(new URL('../../openhab/power-evidence-resources.json', import.meta.url), 'utf8'));
const specs = [...evidence.items, ...resources.items];
function run(phase, options = {}) {
  const values = new Map(), links = new Map(), added = [], released = [], logs = [];
  class Item {
    constructor(name) { expect(specs.map(s=>s.name)).toContain(name); this.name=name; this.label=''; this.category=''; }
    getType() { return 'String'; } getLabel() { return this.label; } setLabel(v) { this.label=v; }
    getCategory() { return this.category; } setCategory(v) { this.category=v; }
    getGroupNames() { return {isEmpty:()=>!options.groupDrift}; } getTags() { return {isEmpty:()=>true}; }
  }
  if (phase==='links') for (const s of specs) { const item=new Item(s.name); item.label=s.label; values.set(s.name,item); }
  if (options.collision) values.set(specs[1].name,new Item(specs[1].name));
  class UID { constructor(value) { this.value=value; } toString() { return this.value; } }
  class Config { constructor() { this.values={}; } put(k,v) { this.values[k]=v; } }
  class Link {
    constructor(name,channel,config) { this.name=name; this.channel=String(channel); this.config=config; }
    getUID() { return this.name+' -> '+this.channel; }
  }
  if (options.linkCollision) links.set(resources.links[0].itemName+' -> '+resources.links[0].channelUID,{});
  const services={
    'org.openhab.core.items.ItemRegistry':{get:n=>values.get(String(n))??null},
    'org.openhab.core.items.ManagedItemProvider':{get:n=>values.get(String(n))??null,add:item=>{
      if (added.length===options.failAt) throw Error('injected');
      expect(values.has(item.name)).toBe(false); values.set(item.name,item); added.push(item.name);
    }},
    'org.openhab.core.thing.ThingRegistry':{get:uid=>{
      expect(resources.things.map(t=>t.UID)).toContain(String(uid));
      return {getStatusInfo:()=>({getStatusDetail:()=>options.enabled?'NONE':'DISABLED'}),
        getConfiguration:()=>({get:()=>options.writeConfig?'unexpected':null})};
    }},
    'org.openhab.core.thing.link.ItemChannelLinkRegistry':{get:n=>links.get(String(n))??null},
    'org.openhab.core.thing.link.ManagedItemChannelLinkProvider':{get:n=>links.get(String(n))??null,add:link=>{
      if (added.length===options.failAt) throw Error('injected');
      expect(links.has(link.getUID())).toBe(false); expect(link.config.values).toEqual({profile:'system:default'});
      links.set(link.getUID(),link); added.push(link.getUID());
    }},
  };
  const context={getServiceReference:n=>{expect(Object.keys(services)).toContain(n);return options.missingService&&n.endsWith('ManagedItemProvider')?null:n;},
    getService:n=>services[n],ungetService:n=>released.push(n)};
  const java={
    'org.osgi.framework.FrameworkUtil':{getBundle:()=>({getBundleContext:()=>context})},
    'org.openhab.core.items.ItemRegistry':{class:{}},'org.openhab.core.library.items.StringItem':Item,
    'org.openhab.core.thing.ThingUID':UID,'org.openhab.core.thing.ChannelUID':UID,
    'org.openhab.core.thing.link.ItemChannelLink':Link,'org.openhab.core.config.core.Configuration':Config,
  };
  let error;
  try { vm.runInNewContext(source.replace("const PHASE = 'preflight';",`const PHASE = '${phase}';`),{
    Java:{type:n=>{if(!(n in java))throw Error('unexpected Java');return java[n];}}, console:{info:s=>logs.push(s)},
    require:()=>{throw Error('no imports');},fetch:()=>{throw Error('no network');},
  },{timeout:1000}); } catch(e) { error=e; }
  return {error,added,released,logs};
}
it('preflight is read-only and releases scoped services',()=>{
  const r=run('preflight');expect(r.error).toBeUndefined();expect(r.added).toEqual([]);expect(r.released).toHaveLength(5);
});
it('adds exactly the four named String definitions',()=>{
  const r=run('items');expect(r.error).toBeUndefined();expect(r.added).toEqual(specs.map(s=>s.name));
});
it('adds exactly three default-profile String links',()=>{
  const r=run('links');expect(r.error).toBeUndefined();expect(r.added).toEqual(resources.links.map(l=>l.itemName+' -> '+l.channelUID));
});
it.each([['items',{collision:true}],['links',{linkCollision:true}],['links',{enabled:true}],
  ['links',{writeConfig:true}],['links',{groupDrift:true}],['preflight',{missingService:true}],['unknown',{}]])
('refuses unsafe %s phase %j without writes',(phase,options)=>{
  const r=run(phase,options);expect(r.error).toBeDefined();expect(r.added).toEqual([]);
});
it.each(['items','links'])('does not hide partial %s failure or retry',phase=>{
  const r=run(phase,{failAt:1});expect(r.error).toBeDefined();expect(r.added).toHaveLength(1);expect(r.released).toHaveLength(5);
});
