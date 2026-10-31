import { describe,it,expect } from 'vitest';
import { parseManualCommandResult,manualOutcomePresentation } from '../../src/lib/shades/manualResult.js';
import { emptyShadeInstallation,validateShadeInstallation,manualShadeTargets } from '../../src/lib/shades/installation.js';

const requestId='11111111-1111-4111-8111-111111111111';
const childId='22222222-2222-4222-8222-222222222222';
const epoch='33333333-3333-4333-8333-333333333333';
const session='44444444-4444-4444-8444-444444444444';
const expected={requestId,command:0,commissionedEpoch:epoch,shadeId:'skylight_1',adapterSession:session,sourceGeneration:2,requestedAtMs:1000};
function receipt(changes={}) { return {schema:'dooya-command-result/v1',request_id:requestId,status:'acknowledged',reason:'await_motor_report',updated_at_ms:1100,
 envelope:{schema:'dooya-owner-command/v1',request_id:requestId,shade_id:'skylight_1',command:0,origin:'manual',created_at_ms:1000,expires_at_ms:11000,
 adapter_session:session,owner_session:'55555555-5555-4555-8555-555555555555',policy_generation:null,
 source_context:{commissioned_epoch:epoch,source_generation:2,bridge_id:'AABBCCDDEEFF',device_id:'0000000000000001'}},fingerprint:'a'.repeat(64),...changes}; }
const raw=value=>JSON.stringify(value);

it.each([
 ['acknowledged','Acknowledged; awaiting motor Report'],['target_observed','Target reported; actor unconfirmed'],
 ['uncertain','Outcome uncertain; no automatic retry'],['rejected','Rejected by adapter'],['expired','Request expired'],['superseded','Request superseded'],
])('shows %s without mechanical completion or measured position', (status,label)=>{
 const parsed=parseManualCommandResult(raw(receipt({status})),expected);
 expect(parsed).toMatchObject({status,label});expect(parsed.position).toBeUndefined();expect(parsed.completed).toBeUndefined();
});

it.each([
 value=>value.request_id=childId,
 value=>value.envelope.request_id=childId,
 value=>value.envelope.command=100,
 value=>value.envelope.command=false,
 value=>value.envelope.origin='automatic',
 value=>value.envelope.shade_id='other_shade',
 value=>value.envelope.source_context.commissioned_epoch=childId,
 value=>value.envelope.source_context.source_generation=3,
 value=>value.envelope.adapter_session='other-session',
 value=>value.schema='dooya-command-result/v99',
 value=>value.status='completed',
 value=>value.updated_at_ms=NaN,
 value=>value.envelope.created_at_ms=999,
])('refuses stale, conflicting, modeled or malformed result provenance',mutate=>{
 const value=receipt();mutate(value);expect(parseManualCommandResult(raw(value),expected)).toBeNull();
});
it('rejects raw observations, signatures, duplicates, deep/oversize and nonfinite JSON',()=>{
 const values=[raw({schema_version:2,source:'motor_report',currentPosition:0}),raw({envelope:receipt(),signature:'x'}),
  raw(receipt()).replace('"status":"acknowledged"','"status":"rejected","status":"acknowledged"'),
  raw(receipt()).replace('"updated_at_ms":1100','"updated_at_ms":1e309'),
  raw({...receipt(),padding:'x'.repeat(33000)}),raw({...receipt(),padding:Array.from({length:30}).reduce(value=>[value],0)})];
 for(const value of values)expect(parseManualCommandResult(value,expected)).toBeNull();
});
it('keeps absent/unrelated Item values unknown and does not reinterpret publication as movement',()=>{
 const request={request_id:requestId,requested_at_ms:1000,slot:1,command:0};
 const response={request_id:requestId,status:'published_awaiting_adapter_result'};
 const slots=[{number:1,commissionedEpoch:epoch,resultItem:'Shade1_Result',adapterShadeId:'skylight_1'}];
 for(const states of [{},{Shade1_Result:'NULL'},{Shade1_Result:raw(receipt({request_id:childId}))}]){
  const view=manualOutcomePresentation(response,request,slots,states);
  expect(view.summary).toContain('unknown');expect(view.summary).not.toContain('No requests published');
 }
 expect(manualOutcomePresentation(response,request,slots,{Shade1_Result:raw(receipt())}).summary).toContain('Acknowledged; awaiting motor Report');
});
it('binds each batch member UUID independently and leaves missing members unknown',()=>{
 const request={request_id:requestId,requested_at_ms:1000,slots:[1,2],command:0};
 const response={request_id:requestId,status:'partially_published',results:[{slot:1,request_id:childId,status:'published_awaiting_adapter_result'},
  {slot:2,request_id:'66666666-6666-4666-8666-666666666666',status:'publication_uncertain_no_retry'}]};
 const slots=[{number:1,commissionedEpoch:epoch,resultItem:'Result1',adapterShadeId:'skylight_1'},
  {number:2,commissionedEpoch:epoch,resultItem:'Result2',adapterShadeId:'skylight_2'}];
 const result=receipt({request_id:childId,envelope:{...receipt().envelope,request_id:childId},status:'target_observed'});
 const view=manualOutcomePresentation(response,request,slots,{Result1:raw(result)});
 expect(view.rows).toEqual([{slot:1,label:'Target reported; actor unconfirmed'},{slot:2,label:'Publication uncertain · no retry'}]);
 expect(view.summary).not.toMatch(/complete|arrived|mechanical/i);
});
it('keeps result mappings optional and excludes them from manual capability admission',()=>{
 const empty=emptyShadeInstallation();
 expect(validateShadeInstallation(empty).slots[0]).toMatchObject({resultItem:null,adapterShadeId:null});
 empty.slots[0].resultItem='Shade1_Result';empty.slots[0].adapterShadeId='skylight_1';
 expect(validateShadeInstallation(empty).slots[0]).toMatchObject({resultItem:'Shade1_Result',adapterShadeId:'skylight_1'});
 expect(manualShadeTargets(empty)).toEqual([]);
 empty.slots[0].adapterShadeId='invalid/device';expect(validateShadeInstallation(empty)).toBeNull();
});

it('keeps malformed or absent batch-member HTTP results unknown without throwing',()=>{
 const request={request_id:requestId,requested_at_ms:1000,slots:[1,2],command:0};
 for(const response of [null,{request_id:requestId,status:'published_awaiting_adapter_result'},
  {request_id:requestId,status:'published_awaiting_adapter_result',results:{}}]){
  const result=manualOutcomePresentation(response,request,[],{});
  expect(result.rows).toEqual([{slot:1,label:'Result unavailable · outcome unknown'},{slot:2,label:'Result unavailable · outcome unknown'}]);
 }
});

it('does not let optional source-context hints replace the submitted request identity',()=>{
 const request={request_id:requestId,requested_at_ms:1000,slot:1,command:0};
 const response={request_id:requestId,status:'published_awaiting_adapter_result'};
 const wrong=receipt({request_id:childId,envelope:{...receipt().envelope,request_id:childId}});
 const view=manualOutcomePresentation(response,request,[{number:1,commissionedEpoch:epoch,resultItem:'Result'}],{Result:raw(wrong)},
  {1:{requestId:childId}});
 expect(view.summary).toContain('unknown');
});

it('preserves explicit owner refusal without claiming a publication or waiting for an adapter result',()=>{
 const request={request_id:requestId,requested_at_ms:1000,slots:[1,2],command:'STOP'};
 expect(manualOutcomePresentation({request_id:requestId,status:'not_published',results:[
  {slot:1,request_id:childId,status:'rejected'},{slot:2,request_id:'66666666-6666-4666-8666-666666666666',status:'rejected'}]},request,[],{}).summary).toBe('No requests published.');
});
