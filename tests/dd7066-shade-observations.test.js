import { describe, expect, it } from 'vitest';
import { shadePresentation, shadeGroupPresentation, shadePreviewEnabled, SHADE_SLOTS } from '../src/lib/shades/catalog.js';
import { currentShadeObservation } from '../src/lib/shades/observation.js';

const NOW=Date.parse('2026-10-24T15:00:00Z');
const slot={sourceIdentity:'a'.repeat(64),commissionedEpoch:'11111111-1111-4111-8111-111111111111',number:1,room:'kitchen',positionItem:'Shade_Position',availabilityItem:'Shade_Available',stateItem:'Shade_State',serviceAvailabilityItem:'Shade_Service',bridgeAvailabilityItem:'Shade_Bridge',serviceStateItem:'Shade_ServiceState',bridgeStateItem:'Shade_BridgeState',serviceThingUID:'mqtt:topic:fixture:shade'};
const providers={'mqtt:topic:fixture:shade':{status:'ONLINE'}};
function fixture(position=25) {
 const identity={adapter_session_id:'adapter-session',source_generation:1};
 const observation={...identity,source_identity_sha256:slot.sourceIdentity,commissioned_epoch:slot.commissionedEpoch,id:'report-1',received_at:NOW/1000,validated_at:NOW/1000,upstream_message_id:'20261024150000000',measurement_time_known:false,hardware_boot_known:false,origin:'unknown',bridge_id:'BRIDGE',device_id:'DEVICE',device_type:'10000000'};
 return {Shade_Position:String(position),Shade_Available:'ON',Shade_Service:'ON',Shade_Bridge:'ON',Shade_State:JSON.stringify({schema_version:2,...identity,source:'motor_report',reported_position:position,current_position:position,report_received_at:NOW/1000,stale:false,usable:true,action_qualified:false,movement_state:'stationary_reported',requested_target:null,observation}),Shade_ServiceState:JSON.stringify({schema_version:2,...identity,ready:true,emitted_at:NOW/1000}),Shade_BridgeState:JSON.stringify({schema_version:2,...identity,bridge_id:'BRIDGE',reachable:true,emitted_at:NOW/1000})};
}
const read=(states,connection='live',now=NOW,things=providers)=>currentShadeObservation(slot,states,connection,now,things);

describe('DD7066 current observations require composite session liveness',()=>{
 it('routes the active catalog through v2 liveness and leaves partial installation uncommissioned',()=>{
  expect(shadePresentation(slot,fixture(),'live',NOW,providers)).toMatchObject({state:'reported',position:25});
  const historical=fixture();historical.Shade_State=JSON.stringify({...JSON.parse(historical.Shade_State),schema_version:1});historical.Shade_Service='OFF';
  expect(shadePresentation(slot,historical,'live',NOW,providers).position).toBeNull();
  expect(shadeGroupPresentation([slot,{number:2}],fixture(),'live',NOW,providers).state).toBe('unavailable');
  const partial=SHADE_SLOTS.map((row,index)=>index===0?{...row,serviceAvailabilityItem:'Mapped_Service'}:row);
  expect(shadePreviewEnabled(partial)).toBe(false);
 });

 it.each([0,25,50,75,100])('preserves native %s and derives openness once without movement authority',position=>{
  expect(read(fixture(position))).toMatchObject({state:'reported',position,openPercent:100-position,actionQualified:false,observationId:'report-1',measurementTimeKnown:false});
 });
 it.each(['Shade_Service','Shade_Bridge','Shade_Available'])('does not trust retained shade state after %s loss',item=>{
  const states=fixture();states[item]='OFF';
  expect(read(states)).toMatchObject({state:'last_known',position:null,lastKnownPosition:25});
 });
 it('gates immediately on LWT Thing offline even before retained channel states change',()=>{
  expect(read(fixture(),'live',NOW,{'mqtt:topic:fixture:shade':{status:'OFFLINE'}})).toMatchObject({state:'last_known',position:null,lastKnownPosition:25});
 });
 it('refuses old session/generation retained values and stale health snapshots',()=>{
  for(const mutate of [s=>s.Shade_ServiceState=JSON.stringify({...JSON.parse(s.Shade_ServiceState),adapter_session_id:'restarted'}),s=>s.Shade_BridgeState=JSON.stringify({...JSON.parse(s.Shade_BridgeState),source_generation:2}),s=>s.Shade_ServiceState=JSON.stringify({...JSON.parse(s.Shade_ServiceState),emitted_at:NOW/1000-91})]){
   const states=fixture();mutate(states);expect(read(states).position).toBeNull();
  }
 });
 it('keeps request/movement uncertainty separate from retained last-known position',()=>{
  const states=fixture();states.Shade_State=JSON.stringify({...JSON.parse(states.Shade_State),usable:false,stale:true,current_position:null,movement_state:'uncertain',requested_target:100,uncertainty_reason:'await_post_motion_report'});
  expect(read(states)).toMatchObject({state:'last_known',position:null,lastKnownPosition:25,requestedTarget:100,movementState:'uncertain'});
 });
 it('withholds crossed device and original commissioning-epoch reports',()=>{
  for(const mismatch of [{source_identity_sha256:'b'.repeat(64)},{commissioned_epoch:'22222222-2222-4222-8222-222222222222'}]){
   const states=fixture(),report=JSON.parse(states.Shade_State);report.observation={...report.observation,...mismatch};states.Shade_State=JSON.stringify(report);expect(read(states)).toMatchObject({state:'last_known',position:null});
  }
 });
 it('does not promote legacy v1, synthetic/cache evidence or malformed optional values',()=>{
  for(const change of [{schema_version:1},{source:'bridge_cache'},{source:'preview'},{reported_position:true},{report_received_at:null},{observation:{}}]){
   const states=fixture();states.Shade_State=JSON.stringify({...JSON.parse(states.Shade_State),...change});expect(read(states).position).toBeNull();
  }
 });
 it('leaves unmapped members explicit and requires all liveness mappings',()=>{
  expect(currentShadeObservation({number:2},fixture(),'live',NOW,providers)).toMatchObject({state:'unmapped',position:null});
  expect(currentShadeObservation({...slot,serviceStateItem:null},fixture(),'live',NOW,providers)).toMatchObject({state:'unmapped',position:null});
 });
});
