import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, it, expect } from 'vitest';
const source = readFileSync(new URL('../../openhab/rules/living-room-circadian.js', import.meta.url), 'utf8');
const ids = ['tplinksmarthome:kl125:E7FA31','tplinksmarthome:kl125:E62B6D','tplinksmarthome:kl125:E7CAD9'];
const switches = ['living_room_1_Switch','living_room_2_Switch','LED_living_room_1_Switch'];
const actuals = [1,2,3].map(n => `LivingRoomCircadian_LivingRoom${n}_ActualK`);
const svc = 'smartlife.iot.smartbulb.lightingservice';
function harness(options = {}) {
  let now = 1000000;
  const cache = new Map();
  const states = {LivingRoomCircadian_Enable:'ON',Sun_Circadian_Temperature:'4500 K',Sun_Position_Elevation:'25 °',...options.states};
  switches.forEach(s => { states[s] ??= 'ON'; });
  let solarTime = now;
  const online = Object.fromEntries(['astro:sun:local', ...ids].map(i => [i,'ONLINE']));
  const bulbs = ids.map(() => ({on_off:1,color_temp:3000,brightness:42,hue:0,saturation:0,mode:'normal'}));
  const calls = [], posts = [];
  let behavior = options.behavior ?? (() => undefined);
  function query(index, method, payload) {
    calls.push({index,method,payload});
    const override = behavior({index,method,payload,states,bulbs});
    if (override !== undefined) return override;
    if (method === 'transition_light_state') {
      // Real firmware characterization: CT-only writes while OFF are ignored;
      // explicitly setting on_off would resurrect the light.
      if ('on_off' in payload) bulbs[index].on_off = payload.on_off;
      if (bulbs[index].on_off) Object.assign(bulbs[index], payload);
    }
    const b = bulbs[index];
    const state = b.on_off ? {...b} : {on_off:0,dft_on_state:{color_temp:b.color_temp,brightness:b.brightness}};
    return JSON.stringify({[svc]:{[method]:{...state,err_code:0}}});
  }
  const openhab = {
    items:{getItem(name) {return {get state(){return states[name] ?? 'NULL';},get lastStateUpdateTimestamp(){return {toInstant:()=>({toEpochMilli:()=>solarTime})};},postUpdate(value){posts.push({name,value:String(value)});states[name]=String(value);}};}},
    things:{getThing(uid){return {status:online[uid]};}},
    cache:{private:{get(key,supplier){if(!cache.has(key)&&supplier)cache.set(key,supplier());return cache.get(key)??null;},put:(k,v)=>cache.set(k,v),remove:k=>cache.delete(k)}},
    actions:{get(scope,uid){if(scope!=='tplinksmarthome')throw Error('wrong action');const index=ids.indexOf(uid);if(index<0)throw Error('wrong device');return {send(raw){const command=JSON.parse(raw)[svc];const method=Object.keys(command)[0];return query(index,method,command[method]);}};},
      Exec:{executeCommandLine(_duration,_bin,_host,ip,_type,_bulb,cmd){const index=['192.168.1.130','192.168.1.96','192.168.1.235'].indexOf(ip);const b=bulbs[index];calls.push({index,method:cmd,payload:{}});return cmd==='state'?`Device state: ${b.on_off?'True':'False'}\nColor temperature: ${b.color_temp}`:'Setting color temperature to 4500\nError: timeout';}}},
  };
  const ctx = vm.createContext({require:()=>openhab,console:{info(){},warn(){},error(){}},Java:{type(name){
    if(name==='java.time.Instant')return {now:()=>({toEpochMilli:()=>now,toString:()=>new Date(now).toISOString()})};
    if(name==='java.time.Duration')return {ofSeconds:n=>n};
    if(name==='java.util.concurrent.atomic.AtomicBoolean')return class {constructor(v){this.v=v;}compareAndSet(a,b){if(this.v!==a)return false;this.v=b;return true;}set(v){this.v=v;}};
    throw Error(name);
  }}});
  return {states,online,bulbs,calls,posts,cache,setBehavior(fn){behavior=fn;},advance(ms){now+=ms;solarTime=now;},stale(){solarTime=now-120001;},run(event){ctx.event=event;vm.runInContext(`(function(){${source}\n})()`,ctx);},writes(){return calls.filter(c=>c.method==='transition_light_state'||c.method==='temperature');}};
}
describe('living room circadian owner', () => {
  it('uses native Astro temperature and confirms actual bulb state without power or brightness writes',()=>{
    const h=harness();h.run();expect(h.states.LivingRoomCircadian_TargetK).toBe('4500');
    expect(h.writes()).toHaveLength(3);
    for(const c of h.writes()){expect(c.payload.color_temp).toBe(4500);expect(c.payload).not.toHaveProperty('on_off');expect(c.payload).not.toHaveProperty('brightness');}
    expect(h.states[actuals[0]]).toBe('4500');expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^healthy/);
  });
  it.each([['2500 K','2500'],['4237 K','4237'],['5500 K','5500']])('uses the native target %s without recalculating from elevation',(raw,want)=>{const h=harness({states:{Sun_Circadian_Temperature:raw,Sun_Position_Elevation:'NULL'}});h.run();expect(h.states.LivingRoomCircadian_TargetK).toBe(want);});
  it.each(['NULL','UNDEF','NaN','4500','4500 °F','Infinity K','2499 K','5501 K'])('fails closed for invalid native target %s',value=>{const h=harness({states:{Sun_Circadian_Temperature:value}});h.run();expect(h.writes()).toHaveLength(0);expect(h.states.LivingRoomCircadian_TargetK).toBe('UNDEF');expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^unavailable/);});
  it('rejects stale Astro data',()=>{const h=harness();h.stale();h.run();expect(h.writes()).toHaveLength(0);expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^unavailable/);});
  it('rejects an offline Astro provider',()=>{const h=harness();h.online['astro:sun:local']='OFFLINE';h.run();expect(h.writes()).toHaveLength(0);});
  it('does no device work while disabled',()=>{const h=harness({states:{LivingRoomCircadian_Enable:'OFF'}});h.run();expect(h.calls).toHaveLength(0);expect(h.states.LivingRoomCircadian_LastResult).toBe('disabled');});
  it('treats a bulb OFF at the device as normal and clears its actual temperature',()=>{const h=harness();h.bulbs[0].on_off=0;h.run();expect(h.writes().filter(c=>c.index===0)).toHaveLength(0);expect(h.states[actuals[0]]).toBe('UNDEF');expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^healthy/);});
  it('honors an explicit manual OFF item even before device polling catches up',()=>{const h=harness({states:{[switches[0]]:'OFF'}});h.run();expect(h.writes().filter(c=>c.index===0)).toHaveLength(0);});
  it('preserves an OFF occurring between live query and CT request',()=>{const h=harness({behavior:({index,method,bulbs})=>{if(index===0&&method==='transition_light_state')bulbs[0].on_off=0;}});h.run();expect(h.bulbs[0].on_off).toBe(0);expect(h.states[actuals[0]]).toBe('UNDEF');expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^healthy/);});
  it('checks disablement again after a blocking device query',()=>{const h=harness({behavior:({method,states})=>{if(method==='get_light_state')states.LivingRoomCircadian_Enable='OFF';}});h.run();expect(h.writes()).toHaveLength(0);expect(h.states.LivingRoomCircadian_LastResult).toBe('disabled');});
  it('honors an OFF item arriving during query',()=>{const h=harness({behavior:({index,method,states})=>{if(index===0&&method==='get_light_state')states[switches[0]]='OFF';}});h.run();expect(h.writes().filter(c=>c.index===0)).toHaveLength(0);});
  it('never reports a successful write when only an optimistic acknowledgement arrived',()=>{const h=harness({behavior:({index,method})=>method==='transition_light_state'&&index===0?JSON.stringify({[svc]:{[method]:{err_code:0}}}):undefined});h.run();expect(h.states[actuals[0]]).toBe('3000');expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^degraded/);});
  it('requires err_code zero for write acknowledgement',()=>{const h=harness({behavior:({index,method})=>index===0&&method==='transition_light_state'?JSON.stringify({[svc]:{[method]:{err_code:-1,color_temp:4500}}}):undefined});h.run();expect(h.states[actuals[0]]).not.toBe('4500');expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^degraded/);});
  it.each(['','not json',JSON.stringify({[svc]:{get_light_state:{on_off:1,color_temp:3000}}})])('rejects malformed query response %s',response=>{const h=harness({behavior:({index,method})=>index===0&&method==='get_light_state'?response:undefined});h.run();expect(h.writes().filter(c=>c.index===0)).toHaveLength(0);expect(h.states[actuals[0]]).toBe('UNDEF');expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^degraded/);});
  it('backs off repeated write failures even when state queries succeed, then recovers on ONLINE',()=>{
    const h=harness({behavior:({index,method})=>{if(index===0&&method==='transition_light_state')throw Error('transport');}});
    h.run();h.advance(300000);h.run();h.calls.length=0;h.advance(300000);h.run();expect(h.calls.filter(c=>c.index===0)).toHaveLength(0);
    h.setBehavior(()=>undefined);h.run({thingUID:ids[0],status:'ONLINE'});expect(h.states[actuals[0]]).toBe('4500');
  });
  it('updates immediately on bulb ON despite the global query throttle',()=>{const h=harness();h.bulbs[0].on_off=0;h.run();h.bulbs[0].on_off=1;h.calls.length=0;h.run({itemName:switches[0],itemState:'ON'});expect(h.writes().filter(c=>c.index===0)).toHaveLength(1);});
  it('rate limits small native target changes and recovers after the interval',()=>{const h=harness();h.run({itemName:'Sun_Circadian_Temperature'});h.calls.length=0;h.states.Sun_Circadian_Temperature='4540 K';h.run({itemName:'Sun_Circadian_Temperature'});expect(h.calls).toHaveLength(0);h.advance(300000);h.run({itemName:'Sun_Circadian_Temperature'});expect(h.calls.length).toBeGreaterThan(0);});
  it('does not write when actual CT is within 100 K',()=>{const h=harness();h.bulbs.forEach(b=>{b.color_temp=4450;});h.run();expect(h.writes()).toHaveLength(0);expect(h.states[actuals[0]]).toBe('4450');});
  it('marks an offline bulb degraded without network work',()=>{const h=harness();h.online[ids[0]]='OFFLINE';h.run();expect(h.calls.filter(c=>c.index===0)).toHaveLength(0);expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^degraded/);});
  it('rechecks solar freshness after query before any write',()=>{const h=harness({behavior:({method})=>{if(method==='get_light_state')h.stale();}});h.run();expect(h.writes()).toHaveLength(0);expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^unavailable/);});
  it('releases the run lock after a failure so later triggers can recover',()=>{const h=harness({states:{Sun_Circadian_Temperature:'NULL'}});h.run();h.states.Sun_Circadian_Temperature='4500 K';h.run();expect(h.writes()).toHaveLength(3);});
  it('never infers a white temperature from RGB mode',()=>{const h=harness();h.bulbs[0].color_temp=0;h.run();expect(h.writes().filter(c=>c.index===0)).toHaveLength(1);expect(h.states[actuals[0]]).toBe('4500');});

  it('retries optimistic ON on the next actual provider update, without querying on every steady ON update',()=>{
    const h=harness();h.bulbs[0].on_off=0;h.run({itemName:switches[0],newState:'ON',eventType:'change'});
    h.bulbs[0].on_off=1;h.calls.length=0;h.run({itemName:switches[0],receivedState:'ON',eventType:'update'});
    expect(h.writes().filter(c=>c.index===0)).toHaveLength(1);
    h.calls.length=0;h.run({itemName:switches[0],receivedState:'ON',eventType:'update'});expect(h.calls).toHaveLength(0);
  });
  it('clears ActualK when a write times out after the device may already have changed',()=>{
    const h=harness({behavior:({index,method})=>{if(index===0&&method==='transition_light_state')throw Error('timeout');}});h.run();expect(h.states[actuals[0]]).toBe('UNDEF');
  });
  it('retains an overlapping recovery event for the next evaluation',()=>{
    const h=harness();h.run();h.bulbs[0].color_temp=3000;
    const lock=h.cache.get('lrCircadianBindingLock');lock.set(true);h.run({thingUID:ids[0],newStatus:'ONLINE'});lock.set(false);
    h.calls.length=0;h.run({itemName:'Sun_Circadian_Temperature'});expect(h.writes().filter(c=>c.index===0)).toHaveLength(1);
  });

  it('recovers immediately after invalid Astro data becomes fresh again',()=>{
    const h=harness();h.run();h.states.Sun_Circadian_Temperature='NULL';h.run();expect(h.states.LivingRoomCircadian_TargetK).toBe('UNDEF');
    h.states.Sun_Circadian_Temperature='4500 K';h.calls.length=0;h.run();expect(h.calls.length).toBeGreaterThan(0);expect(h.states.LivingRoomCircadian_TargetK).toBe('4500');expect(h.states.LivingRoomCircadian_LastResult).toMatch(/^healthy/);
  });

});
