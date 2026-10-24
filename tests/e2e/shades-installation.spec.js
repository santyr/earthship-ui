import { test as base, expect } from '@playwright/test';
import { createServer } from 'vite';
import { SHADE_SLOTS } from '../../src/lib/shades/catalog.js';
import { emptyShadeInstallation } from '../../src/lib/shades/installation.js';

process.env.OPENHAB_PROXY_TARGET='http://127.0.0.1:9';
delete process.env.OPENHAB_TOKEN;
delete process.env.EARTHSHIP_SHADE_OWNER_PROFILE;
const COMMISSIONED_EPOCH='b79b68d3-4242-446a-b9c8-127dbbe206a9';
const sourceIdentity=number=>(number===1?'a':'b').repeat(64);
let server,baseURL;
const test=base.extend({
 isolatedShadeNetwork:[async({context},use)=>{
  const errors=[],violations=[];
  context.on('page',page=>page.on('pageerror',error=>errors.push(error.message)));
  await context.route('**/*',async route=>{
   const request=route.request(),url=new URL(request.url());
   if(!baseURL||url.origin!==new URL(baseURL).origin||!['GET','HEAD'].includes(request.method())){
    violations.push(`${request.method()} ${url.pathname}`);return route.abort('blockedbyclient');
   }
   if(url.pathname==='/config.json')return route.fulfill({json:{openhabUrl:'/fixture-openhab',apiToken:'',staleBannerSeconds:90}});
   if(url.pathname.startsWith('/api/'))return route.fulfill({status:503,json:{error:'fixture unavailable'}});
   if(url.pathname.startsWith('/fixture-openhab/'))return route.fulfill({json:[]});
   return route.continue();
  });
  await use();expect(errors,'page errors').toEqual([]);expect(violations,'escaped fixture mutation/network').toEqual([]);
 },{auto:true}],
});
test.use({hasTouch:true,httpCredentials:{username:'synthetic-manual',password:'synthetic-fixture-only'}});
test.beforeAll(async()=>{server=await createServer({root:process.cwd(),logLevel:'error',server:{port:0,strictPort:false}});await server.listen();baseURL=server.resolvedUrls.local[0];});
test.afterAll(async()=>{await server?.close();});

function installation(count=1,released=false){
 const value=emptyShadeInstallation();value.contextId='fixture-installation-1';value.manualOwnerAvailable=released;
 for(let i=0;i<count;i++)value.slots[i]={...SHADE_SLOTS[i],positionItem:`Shade${i+1}_Position`,availabilityItem:`Shade${i+1}_Available`,stateItem:`Shade${i+1}_State`,serviceAvailabilityItem:'Shade_Service',bridgeAvailabilityItem:'Shade_Bridge',serviceStateItem:'Shade_ServiceState',bridgeStateItem:'Shade_BridgeState',serviceThingUID:'mqtt:topic:fixture:shades',sourceIdentity:sourceIdentity(i+1),commissionedEpoch:COMMISSIONED_EPOCH,commissioned:true,manualReleased:released,operations:['UP','DOWN','STOP'],percentage:true};
 return value;
}
function stateFixture(count=1){
 const now=Date.now()/1000,identity={adapter_session_id:'synthetic-adapter-session',source_generation:1};
 const states={Shade_Service:'ON',Shade_Bridge:'ON',Shade_ServiceState:JSON.stringify({schema_version:2,...identity,ready:true,emitted_at:now}),Shade_BridgeState:JSON.stringify({schema_version:2,...identity,bridge_id:'SYNTHETIC_BRIDGE',reachable:true,emitted_at:now})};
 for(let i=1;i<=count;i++){
  const position=25;
  states[`Shade${i}_Position`]=String(position);states[`Shade${i}_Available`]='ON';
  states[`Shade${i}_State`]=JSON.stringify({schema_version:2,...identity,source:'motor_report',reported_position:position,current_position:position,report_received_at:now,stale:false,usable:true,movement_state:'stationary_reported',requested_target:null,observation:{...identity,commissioned_epoch:COMMISSIONED_EPOCH,source_identity_sha256:sourceIdentity(i),id:`synthetic-report-${i}`,received_at:now,validated_at:now,measurement_time_known:false,hardware_boot_known:false,origin:'unknown',bridge_id:'SYNTHETIC_BRIDGE',device_id:`SYNTHETIC_DEVICE_${i}`,device_type:'10000000'}});
 }
 return states;
}
async function setup(page,manifest=installation(),options={}){
 const writes=[],requests=[],states=stateFixture(options.count??1);
 page.on('request',request=>{if(!['GET','HEAD'].includes(request.method()))writes.push({url:new URL(request.url()).pathname,body:request.postDataJSON()});});
 await page.addInitScript(()=>{
  window.shadeFixtureSources=[];
  window.EventSource=class extends EventTarget {
   constructor(url){super();this.url=String(url);this.closed=false;window.shadeFixtureSources.push(this);setTimeout(()=>{if(!this.closed)this.onopen?.(new Event('open'));},0);}
   close(){this.closed=true;}
  };
 });
 await page.route('**/api/shades-installation',route=>route.fulfill({json:manifest}));
 await page.route('**/fixture-openhab/rest/items?*',route=>route.fulfill({json:Object.entries(states).map(([name,state])=>({name,state,type:name.endsWith('_Position')?'Rollershutter':name.endsWith('_State')||name.endsWith('State')?'String':'Switch'}))}));
 await page.route('**/fixture-openhab/rest/things',route=>route.fulfill({json:[{UID:'mqtt:topic:fixture:shades',label:'Synthetic adapter',statusInfo:{status:'ONLINE'}}]}));
 await page.route('**/api/shades/manual',async route=>{
  expect(route.request().method()).toBe('POST');const body=route.request().postDataJSON();requests.push(body);
  if(options.hold)await options.hold;
  if(options.status===401)return route.fulfill({status:401,json:{error:'authentication_required'}}).catch(()=>{});
  const results=body.slots?.map((slot,index)=>({slot,request_id:crypto.randomUUID(),status:options.none||options.partial&&index===1?'rejected':'published_awaiting_adapter_result'}));
  return route.fulfill({json:{request_id:body.request_id,status:options.uncertain?'publication_uncertain_no_retry':options.none?'not_published':options.partial?'partially_published':'published_awaiting_adapter_result',...(results?{results}: {})}}).catch(()=>{});
 });
 return {writes,requests,states,manifest};
}
async function emit(page,name,value){await page.evaluate(({name,value})=>{
 const message={topic:`openhab/items/${name}/statechanged`,payload:JSON.stringify({value})};
 for(const source of window.shadeFixtureSources)if(source.url.includes('/fixture-openhab/rest/events')&&!source.closed)source.onmessage?.({data:JSON.stringify(message)});
},{name,value});}
const firstCard=page=>page.getByRole('article',{name:/^Kitchen Shade 01:/});

for(const size of [{width:1340,height:800},{width:1280,height:720}]){
 test(`${size.width}x${size.height}: one current synthetic report and25 unmapped slots stay observation-only`,async({page})=>{
  const fixture=await setup(page);await page.setViewportSize(size);await page.goto(`${baseURL}#/shades`);
  await expect(page.getByText('26 planned · 1 mapped · 1 reporting')).toBeVisible();
  await expect(firstCard(page).locator('.position-value')).toHaveText('75%');
  await expect(firstCard(page).locator('.position-caption')).toHaveText('reported open');
  await expect(page.getByRole('article',{name:'Kitchen Shade 02: Awaiting Item mapping'}).locator('.position-caption')).toHaveText('unmapped');
  await expect(page.locator('.master-card .position-value')).toHaveText('—');
  await expect(page.locator('input[type=range]:not(:disabled)')).toHaveCount(0);
  const readOnlySlider=firstCard(page).getByRole('slider');
  await readOnlySlider.dispatchEvent('pointerdown',{pointerType:'touch',pointerId:7,clientY:200});
  await readOnlySlider.dispatchEvent('pointercancel',{pointerType:'touch',pointerId:7,clientY:250});
  await expect(page.getByRole('button',{name:'Open all',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Manual control',exact:true})).toHaveCount(0);
  const previewSources=await page.evaluate(()=>window.shadeFixtureSources.filter(source=>source.url.includes('/api/shades-preview')).length);expect(previewSources).toBe(0);
  const raw=JSON.parse(fixture.states.Shade1_State);raw.requested_target=100;raw.usable=false;raw.stale=true;raw.current_position=null;raw.movement_state='uncertain';
  await emit(page,'Shade1_State',JSON.stringify(raw));
  await expect(firstCard(page).locator('.position-value')).toHaveText('75%');
  await expect(firstCard(page).getByText('last known',{exact:true})).toBeVisible();
  await expect(firstCard(page).getByText('Requested 0%',{exact:true})).toBeVisible();
  await emit(page,'Shade_Service','OFF');await expect(page.getByText('26 planned · 1 mapped · 0 reporting')).toBeVisible();
  await emit(page,'Shade_Service','ON');
  await page.evaluate(()=>{const event={topic:'openhab/things/mqtt:topic:fixture:shades/status',payload:JSON.stringify({status:'OFFLINE'})};for(const source of window.shadeFixtureSources)if(source.url.includes('/fixture-openhab/rest/events')&&!source.closed)source.onmessage?.({data:JSON.stringify(event)});});
  await expect(firstCard(page)).toHaveAttribute('title',/Adapter provider unavailable/);
  await page.getByRole('button',{name:'Bathroom + Bedroom',exact:true}).click();
  await expect(page.getByRole('article',{name:'Bedroom Shade 26: Awaiting Item mapping'})).toBeVisible();
  await page.getByRole('button',{name:'Kitchen + Living Room',exact:true}).click();
  await page.evaluate(()=>{window.dispatchEvent(new Event('online'));window.dispatchEvent(new Event('focus'));document.dispatchEvent(new Event('visibilitychange'));});
  await page.reload();await expect(page.getByText('26 planned · 1 mapped · 1 reporting')).toBeVisible();
  expect(fixture.writes).toEqual([]);
  const geometry=await page.evaluate(()=>({width:document.documentElement.scrollWidth,viewport:innerWidth,height:document.documentElement.scrollHeight,screen:innerHeight}));
  expect(geometry.width).toBeLessThanOrEqual(geometry.viewport);expect(geometry.height).toBeLessThanOrEqual(geometry.screen);
 });
}

test('manual modal single command and openness conversion require explicit submissions; lifecycle and cancellation do not write',async({page})=>{
 const fixture=await setup(page,installation(1,true));await page.goto(`${baseURL}#/shades`);
 await page.getByRole('button',{name:'Manual control',exact:true}).tap();const dialog=page.getByRole('dialog',{name:'Manual shade request'});
 await expect(dialog).toBeVisible();expect(fixture.requests).toEqual([]);
 const geometry=await dialog.evaluate(element=>{const b=element.getBoundingClientRect();return {left:b.left,top:b.top,right:b.right,bottom:b.bottom,width:innerWidth,height:innerHeight,touch:[...element.querySelectorAll('button,input,select')].map(node=>node.getBoundingClientRect().height)};});
 expect(geometry.left).toBeGreaterThanOrEqual(0);expect(geometry.top).toBeGreaterThanOrEqual(0);expect(geometry.right).toBeLessThanOrEqual(geometry.width);expect(geometry.bottom).toBeLessThanOrEqual(geometry.height);expect(geometry.touch.every(height=>height>=44)).toBe(true);
 const target=dialog.getByRole('combobox',{name:'Shades to control'});await target.selectOption('shade-1');
 await dialog.getByRole('spinbutton',{name:'Percent open',exact:true}).fill('75');expect(fixture.requests).toEqual([]);
 await dialog.getByRole('button',{name:'Request percentage',exact:true}).focus();await page.keyboard.press('Enter');
 await expect(dialog.getByRole('status')).toContainText('awaiting adapter result');expect(fixture.requests).toHaveLength(1);
 expect(fixture.requests[0]).toMatchObject({slot:1,command:25});expect(Object.keys(fixture.requests[0]).sort()).toEqual(['command','request_id','requested_at_ms','slot']);
 expect(fixture.requests[0].request_id).toMatch(/^[0-9a-f-]{36}$/);expect(Number.isSafeInteger(fixture.requests[0].requested_at_ms)).toBe(true);
 await expect(firstCard(page).locator('.position-value')).toHaveText('75%');
 await dialog.getByRole('button',{name:'Cancel',exact:true}).tap();await expect(dialog).not.toBeVisible();
 await page.getByRole('button',{name:'Manual control',exact:true}).click();await page.keyboard.press('Escape');
 await page.getByRole('button',{name:'Bathroom + Bedroom',exact:true}).tap();await page.reload();
 expect(fixture.requests).toHaveLength(1);expect(fixture.writes.map(write=>write.url)).toEqual(['/api/shades/manual']);
});

test('zone/all batches contain only released commissioned members and show per-member refusal',async({page})=>{
 const manifest=installation(2,true);manifest.slots[2]={...manifest.slots[1],...SHADE_SLOTS[2],commissioned:false,manualReleased:false,operations:[],percentage:false};
 const fixture=await setup(page,manifest,{count:2,partial:true});await page.goto(`${baseURL}#/shades`);
 await page.getByRole('button',{name:'Manual control',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Manual shade request'});
 await dialog.getByRole('combobox',{name:'Shades to control'}).selectOption('kitchen');await dialog.getByRole('button',{name:'Stop',exact:true}).tap();
 await expect(dialog.getByRole('status')).toContainText('Some requests published');
 expect(fixture.requests[0]).toMatchObject({slots:[1,2],command:'STOP'});expect(fixture.requests[0]).not.toHaveProperty('slot');
 await expect(dialog.getByRole('list',{name:'Per-shade request results'})).toContainText('Shade 1: Published');
 await expect(dialog.getByRole('list',{name:'Per-shade request results'})).toContainText('Shade 2: Rejected');
 await dialog.getByRole('combobox',{name:'Shades to control'}).selectOption('all');await dialog.getByRole('button',{name:'Open',exact:true}).click();
 await expect.poll(()=>fixture.requests.length).toBe(2);expect(fixture.requests[1]).toMatchObject({slots:[1,2],command:'UP'});
 expect(fixture.requests[0].request_id).not.toBe(fixture.requests[1].request_id);
});

test('401 is explicit and never stores a frontend manual secret',async({page})=>{
 const fixture=await setup(page,installation(1,true),{status:401});await page.goto(`${baseURL}#/shades`);
 await page.getByRole('button',{name:'Manual control',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Manual shade request'});
 await dialog.getByRole('button',{name:'Close',exact:true}).click();await expect(dialog.getByRole('status')).toHaveText('Manual authentication required.');
 expect(fixture.requests).toHaveLength(1);expect(await page.evaluate(()=>JSON.stringify({...localStorage}))).not.toContain('synthetic-manual');
});

test('uncertain response never claims publication or position completion',async({page})=>{
 const fixture=await setup(page,installation(1,true),{uncertain:true});await page.goto(`${baseURL}#/shades`);
 await page.getByRole('button',{name:'Manual control',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Manual shade request'});
 await dialog.getByRole('button',{name:'Stop',exact:true}).click();await expect(dialog.getByRole('status')).toContainText('Publication uncertain');
 await expect(dialog.getByRole('status')).toContainText('No retry');expect(fixture.requests).toHaveLength(1);
});

test('installation context changes cancel an open manual modal without a write',async({page})=>{
 const manifest=installation(1,true),fixture=await setup(page,manifest);await page.goto(`${baseURL}#/shades`);
 await page.getByRole('button',{name:'Manual control',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Manual shade request'});await expect(dialog).toBeVisible();
 manifest.contextId='replacement-installation';await page.evaluate(()=>window.dispatchEvent(new Event('online')));await expect(dialog).not.toBeVisible();
 await page.getByRole('button',{name:'Manual control',exact:true}).click();await expect(dialog).toBeVisible();
 manifest.slots[0].sourceIdentity='c'.repeat(64);manifest.slots[0].commissionedEpoch='56882eb3-74e7-4726-a5f1-a89e55e4d214';
 await page.evaluate(()=>window.dispatchEvent(new Event('online')));await expect(dialog).not.toBeVisible();expect(fixture.requests).toEqual([]);
});

test('late installation mapping closes an existing preview stream and cannot reuse synthetic positions',async({page})=>{
 const manifest=emptyShadeInstallation();const fixture=await setup(page,manifest);await page.goto(`${baseURL}#/shades`);
 await expect(page.getByText(/preview only · no shade commands/)).toBeVisible();
 expect(await page.evaluate(()=>window.shadeFixtureSources.some(source=>source.url.includes('/api/shades-preview')&&!source.closed))).toBe(true);
 Object.assign(manifest,installation());await page.evaluate(()=>window.dispatchEvent(new Event('online')));
 await expect(page.getByText('26 planned · 1 mapped · 1 reporting')).toBeVisible();
 expect(await page.evaluate(()=>window.shadeFixtureSources.filter(source=>source.url.includes('/api/shades-preview')).every(source=>source.closed))).toBe(true);
 await expect(page.locator('input[type=range]:not(:disabled)')).toHaveCount(0);await expect(firstCard(page).locator('.position-value')).toHaveText('75%');expect(fixture.writes).toEqual([]);
});


test('all-refused batch receipts show no publication and per-shade rejection',async({page})=>{
 const fixture=await setup(page,installation(1,true),{none:true});await page.goto(`${baseURL}#/shades`);
 await page.getByRole('button',{name:'Manual control',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Manual shade request'});
 await dialog.getByRole('combobox',{name:'Shades to control'}).selectOption('all');
 await dialog.getByRole('button',{name:'Stop',exact:true}).click();await expect(dialog.getByRole('status')).toHaveText('No requests published.');
 expect(fixture.requests).toHaveLength(1);
});

test('manual timeout is bounded with no retry and leaving the screen aborts another pending request',async({page})=>{
 await page.addInitScript(()=>{
  const original=window.fetch;window.manualAbortCount=0;
  window.fetch=function(url,options){if(String(url)==='/api/shades/manual')options.signal.addEventListener('abort',()=>window.manualAbortCount++,{once:true});return original.call(this,url,options);};
 });
 await page.clock.install();let release;const held=new Promise(resolve=>release=resolve);
 const fixture=await setup(page,installation(1,true),{hold:held});await page.goto(`${baseURL}#/shades`);
 await page.getByRole('button',{name:'Manual control',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Manual shade request'});
 await dialog.getByRole('button',{name:'Stop',exact:true}).click();await expect.poll(()=>fixture.requests.length).toBe(1);
 await page.clock.fastForward(30001);await expect(dialog.getByRole('status')).toContainText('outcome unknown');await expect(dialog.getByRole('status')).toContainText('No retry');
 expect(await page.evaluate(()=>window.manualAbortCount)).toBe(1);expect(fixture.requests).toHaveLength(1);
 await dialog.getByRole('button',{name:'Stop',exact:true}).click();await expect.poll(()=>fixture.requests.length).toBe(2);
 await page.evaluate(()=>window.location.hash='#/');await expect(dialog).toHaveCount(0);
 await expect.poll(()=>page.evaluate(()=>window.manualAbortCount)).toBe(2);release();expect(fixture.requests).toHaveLength(2);
});

test('partial or invalid installation mapping latches preview off after subsequent endpoint loss',async({page})=>{
 const manifest=emptyShadeInstallation();manifest.slots[0].serviceAvailabilityItem='Synthetic_Service';manifest.slots[1].number=1;
 const fixture=await setup(page,manifest);await page.goto(`${baseURL}#/shades`);
 await expect(page.getByRole('button',{name:'Open all',exact:true})).toBeDisabled();
 await page.route('**/api/shades-installation',route=>route.fulfill({status:503,json:{error:'unavailable'}}));
 await page.evaluate(()=>window.dispatchEvent(new Event('online')));
 await expect(page.getByRole('button',{name:'Open all',exact:true})).toBeDisabled();
 expect(await page.evaluate(()=>window.shadeFixtureSources.filter(source=>source.url.includes('/api/shades-preview')).length)).toBe(0);expect(fixture.writes).toEqual([]);
});


test('an explicit STOP can supersede a pending manual HTTP operation without replay',async({page})=>{
 let release;const held=new Promise(resolve=>release=resolve);const fixture=await setup(page,installation(1,true),{hold:held});
 await page.goto(`${baseURL}#/shades`);await page.getByRole('button',{name:'Manual control',exact:true}).click();
 const dialog=page.getByRole('dialog',{name:'Manual shade request'});await dialog.getByRole('button',{name:'Open',exact:true}).click();
 await expect.poll(()=>fixture.requests.length).toBe(1);await expect(dialog.getByRole('button',{name:'Stop',exact:true})).toBeEnabled();
 await dialog.getByRole('button',{name:'Stop',exact:true}).click();await expect.poll(()=>fixture.requests.length).toBe(2);
 expect(fixture.requests.map(row=>row.command)).toEqual(['UP','STOP']);expect(fixture.requests[0].request_id).not.toBe(fixture.requests[1].request_id);
 await dialog.getByRole('button',{name:'Cancel',exact:true}).click();release();expect(fixture.requests).toHaveLength(2);
});


test('a valid Report from another source or commissioning epoch never becomes this slot current position',async({page})=>{
 const fixture=await setup(page);await page.goto(`${baseURL}#/shades`);
 await expect(page.getByText('26 planned · 1 mapped · 1 reporting')).toBeVisible();
 const original=JSON.parse(fixture.states.Shade1_State);
 for(const mismatch of [{source_identity_sha256:'b'.repeat(64),device_id:'SYNTHETIC_OTHER_DEVICE'},{commissioned_epoch:'56882eb3-74e7-4726-a5f1-a89e55e4d214'}]){
  const crossed=structuredClone(original);Object.assign(crossed.observation,mismatch);
  await emit(page,'Shade1_State',JSON.stringify(crossed));
  await expect(page.getByText('26 planned · 1 mapped · 0 reporting')).toBeVisible();
  await expect(firstCard(page).getByText('last known',{exact:true})).toBeVisible();
  await expect(firstCard(page).locator('.position-value')).toHaveText('75%');
  await emit(page,'Shade1_State',JSON.stringify(original));await expect(page.getByText('26 planned · 1 mapped · 1 reporting')).toBeVisible();
 }
 expect(fixture.writes).toEqual([]);
});

for(const size of [{width:1340,height:800},{width:1280,height:720}]){
 test(`${size.width}x${size.height}: manual result Item follows only its submitted request and never becomes position`,async({page})=>{
  const manifest=installation(1,true);manifest.slots[0].resultItem='Shade1_CommandResult';manifest.slots[0].adapterShadeId='skylight_1';
  const fixture=await setup(page,manifest);await page.setViewportSize(size);await page.goto(`${baseURL}#/shades`);
  await page.getByRole('button',{name:'Manual control',exact:true}).click();const dialog=page.getByRole('dialog',{name:'Manual shade request'});
  await dialog.getByRole('button',{name:'Open',exact:true}).click();
  await expect(dialog.getByRole('status')).toContainText('awaiting adapter result');
  expect(fixture.requests).toHaveLength(1);const request=fixture.requests[0];
  const envelope={schema:'dooya-owner-command/v1',request_id:request.request_id,shade_id:'skylight_1',command:'UP',origin:'manual',
   created_at_ms:request.requested_at_ms,expires_at_ms:request.requested_at_ms+10000,adapter_session:'synthetic-adapter-session',
   owner_session:'55555555-5555-4555-8555-555555555555',policy_generation:null,
   source_context:{commissioned_epoch:COMMISSIONED_EPOCH,source_generation:1,bridge_id:'AABBCCDDEEFF',device_id:'0000000000000001'}};
  const result={schema:'dooya-command-result/v1',request_id:request.request_id,status:'acknowledged',reason:'await_motor_report',
   updated_at_ms:request.requested_at_ms+1,envelope,fingerprint:'a'.repeat(64)};
  await emit(page,'Shade1_CommandResult',JSON.stringify(result));
  await expect(dialog.getByRole('status')).toContainText('Acknowledged; awaiting motor Report');
  await expect(firstCard(page).locator('.position-value')).toHaveText('75%');
  await emit(page,'Shade1_CommandResult',JSON.stringify({...result,request_id:'11111111-1111-4111-8111-111111111111',status:'target_observed'}));
  await expect(dialog.getByRole('status')).toContainText('outcome unknown');
  await emit(page,'Shade1_CommandResult',JSON.stringify({...result,status:'target_observed'}));
  await expect(dialog.getByRole('status')).toContainText('Target reported; actor unconfirmed');
  await expect(firstCard(page).locator('.position-value')).toHaveText('75%');
  await emit(page,'Shade1_CommandResult',JSON.stringify({...result,status:'uncertain'}));
  await expect(dialog.getByRole('status')).toContainText('Outcome uncertain; no automatic retry');
  const bounds=await dialog.evaluate(element=>{const b=element.getBoundingClientRect();return {right:b.right,bottom:b.bottom,width:innerWidth,height:innerHeight};});
  expect(bounds.right).toBeLessThanOrEqual(bounds.width);expect(bounds.bottom).toBeLessThanOrEqual(bounds.height);
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();expect(fixture.requests).toHaveLength(1);
 });
}
