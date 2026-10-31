import { describe, expect, it } from 'vitest';
import { SHADE_SLOTS } from '../../src/lib/shades/catalog.js';
import { emptyShadeInstallation, hasInstallationMapping, validateShadeInstallation, manualShadeTargets, manualShadeRequest, manualResultPresentation } from '../../src/lib/shades/installation.js';

function fixture() { return {schemaVersion:1,automaticReleased:false,manualOwnerAvailable:true,contextId:'fixture-1',slots:SHADE_SLOTS.map(slot=>({...slot,sourceIdentity:null,commissionedEpoch:null,commissioned:false,manualReleased:false,operations:[],percentage:false}))}; }
function mapped(number=1) { const base=SHADE_SLOTS[number-1]; return {...base,positionItem:`Shade${number}_Position`,availabilityItem:`Shade${number}_Available`,stateItem:`Shade${number}_State`,serviceAvailabilityItem:'Shade_Service',bridgeAvailabilityItem:'Shade_Bridge',serviceStateItem:'Shade_ServiceState',bridgeStateItem:'Shade_BridgeState',serviceThingUID:'mqtt:topic:fixture:shades',sourceIdentity:(number===1?'a':'b').repeat(64),commissionedEpoch:'b79b68d3-4242-446a-b9c8-127dbbe206a9',commissioned:true,manualReleased:true,operations:['UP','DOWN','STOP'],percentage:true}; }

describe('public shade installation and explicit manual request boundary',()=>{
 it('defaults all26 slots to unmapped, uncommissioned and unreleased',()=>{
  const empty=emptyShadeInstallation();expect(empty.slots).toHaveLength(26);expect(hasInstallationMapping(empty)).toBe(false);
  expect(empty.slots.every(slot=>slot.sourceIdentity===null&&slot.commissionedEpoch===null)).toBe(true);expect(empty.manualOwnerAvailable).toBe(false);expect(manualShadeTargets(empty)).toEqual([]);
 });
 it('accepts one mapped member while the remaining25 remain explicit',()=>{
  const value=fixture();value.slots[0]=mapped();const parsed=validateShadeInstallation(value);
  expect(parsed.slots[0]).toMatchObject({manualReleased:true,sourceIdentity:'a'.repeat(64),commissionedEpoch:'b79b68d3-4242-446a-b9c8-127dbbe206a9'});expect(parsed.slots.slice(1).every(slot=>slot.positionItem===null&&!slot.commissioned)).toBe(true);
  expect(hasInstallationMapping(parsed)).toBe(true);
  expect(manualShadeTargets(parsed).map(target=>target.id)).toEqual(['all','kitchen','shade-1']);
 });
 it('treats even partial mapping as disabling synthetic preview',()=>{
  const value=fixture();value.slots[0].serviceAvailabilityItem='Mapped_Service';
  expect(hasInstallationMapping(value)).toBe(true);expect(validateShadeInstallation(value)).not.toBeNull();expect(manualShadeTargets(value)).toEqual([]);
 });
 it.each([
  v=>v.slots.pop(), v=>v.slots[1].number=1,v=>v.slots[0].room='bedroom',v=>v.slots[0].label='Other',
  v=>v.automaticReleased=true,v=>v.manualOwnerAvailable='true',v=>v.slots[0].commissioned=1,
  v=>v.slots[0].operations=['RESET'],v=>v.slots[0].operations=['UP','UP'],v=>v.slots[0].positionItem='bad/name',v=>v.slots[0].sourceIdentity='A'.repeat(64),v=>v.slots[0].sourceIdentity='a'.repeat(63),v=>v.slots[0].commissionedEpoch='not-a-uuid',
 ])('rejects malformed public inventory fail-closed',mutate=>{const v=fixture();mutate(v);expect(validateShadeInstallation(v)).toBeNull();});
 it('rejects duplicate device Item mappings while allowing shared liveness Items',()=>{
  const v=fixture();v.slots[0]=mapped();v.slots[1]=mapped(2);
  expect(validateShadeInstallation(v)).not.toBeNull();v.slots[1].stateItem=v.slots[0].stateItem;expect(validateShadeInstallation(v)).toBeNull();
 });
 it('canonicalizes public fields instead of exposing supplied private identities',()=>{
  const v=fixture();v.slots[0]=mapped();v.slots[0].device_id='private';v.key='private';
  const parsed=validateShadeInstallation(v);expect(parsed.key).toBeUndefined();expect(parsed.slots[0].device_id).toBeUndefined();
 });
 it('excludes uncommissioned, unreleased and unavailable-owner members from manual targets',()=>{
  const v=fixture();v.slots[0]=mapped();v.slots[1]={...mapped(2),manualReleased:false};
  expect(manualShadeTargets(v).find(t=>t.id==='all').slots.map(s=>s.number)).toEqual([1]);
  v.manualOwnerAvailable=false;expect(manualShadeTargets(v)).toEqual([]);
 });
 it('converts UI openness exactly once and sends only the declared request fields',()=>{
  const v=fixture();v.slots[0]=mapped();const targets=manualShadeTargets(v), metadata={requestId:'b79b68d3-4242-446a-b9c8-127dbbe206a9',requestedAtMs:123456};
  expect(manualShadeRequest(targets.find(t=>t.id==='shade-1'),{openPercent:75},metadata)).toEqual({request_id:metadata.requestId,requested_at_ms:123456,slot:1,command:25});
  expect(manualShadeRequest(targets.find(t=>t.id==='kitchen'),'STOP',metadata)).toEqual({request_id:metadata.requestId,requested_at_ms:123456,slots:[1],command:'STOP'});
 });
 it('refuses unsupported percentage/operation and invalid input instead of coercing',()=>{
  const v=fixture();v.slots[0]={...mapped(),percentage:false,operations:['STOP']};const target=manualShadeTargets(v)[0];
  for(const command of ['UP',{openPercent:25},{openPercent:25.5},{openPercent:true},'RESET']) expect(()=>manualShadeRequest(target,command,{requestId:'id',requestedAtMs:1})).toThrow();
 });
});

it('does not call uncertain/refused/mismatched receipts published',()=>{
 const request={request_id:'test',slots:[1,2]};
 expect(manualResultPresentation({request_id:'test',status:'not_published'},request).summary).toBe('No requests published.');
 expect(manualResultPresentation({request_id:'test',status:'publication_uncertain_no_retry'},request).summary).toContain('uncertain');
 expect(manualResultPresentation({request_id:'other',status:'published_awaiting_adapter_result'},request).summary).toContain('unknown');
});

it('excludes a previously commissioned row missing its opaque source/epoch identity',()=>{
 const v=fixture();v.slots[0]={...mapped(),sourceIdentity:null};
 expect(manualShadeTargets(v)).toEqual([]);expect(validateShadeInstallation(v)).toBeNull();
});
it('treats partial opaque identity alone as installation evidence that inhibits preview',()=>{
 const v=fixture();v.slots[0].sourceIdentity='a'.repeat(64);expect(hasInstallationMapping(v)).toBe(true);
});
