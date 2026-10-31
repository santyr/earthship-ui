import { describe, expect, it } from 'vitest';
import { createShadeExecutionOwner } from '../src/lib/shades/executionOwner.js';
import { createHash } from 'node:crypto';
const NOW=1792854000000;
const auth='Basic '+Buffer.from('operator:synthetic-password-with-32-bytes').toString('base64');
const epoch='00000000-0000-4000-8000-000000000003';
const rid='00000000-0000-4000-8000-000000000001';
const gen='00000000-0000-4000-8000-000000000004';
function fixture(options={}){
 let clock=NOW;
 const commands=[],policies=[];
 const adapter={schema_version:2,adapter_session_id:'fixture-adapter',source_generation:1,ready:true,bridge_id:'001122334455',emitted_at:NOW/1000};
 const record={slot:18,zone:'bathroom',id:'bathroom_18',deviceId:'001122334456',commissionedEpoch:epoch,model:'synthetic roller',firmware:'synthetic-1',reference:'synthetic-commissioning-fixture',operations:['UP','DOWN','STOP'],percentage:true,manualReleased:true};
 const policy={connected:true,sourceGeneration:gen,override:{state:'ON',authoritative:true},zones:Object.fromEntries(['kitchen','living','bathroom','bedroom'].map(zone=>[zone,{saved:'OFF',authoritative:true}]))};
 let wrongAck=false;
 const owner=createShadeExecutionOwner({...options,inventory:[record],key:Buffer.from('K'.repeat(32)),manualAuthorizationHash:createHash('sha256').update(auth).digest('hex'),now:()=>clock,monotonic:()=>clock-NOW,readAdapter:async()=>adapter,readPolicy:async()=>policy,publishCommand:async value=>{commands.push(value);return {published:true};},publishPolicy:async value=>{policies.push(value);},readPolicyAck:async()=>{const p=policies.at(-1).envelope;return {schema:'dooya-policy-ack/v1',adapter_session:adapter.adapter_session_id,source_generation:adapter.source_generation,owner_session:p.owner_session,policy_generation:wrongAck?'old':p.generation,policy_issued_at_ms:p.issued_at_ms,effective_at_ms:NOW,status:'effective'};}});
 return {owner,commands,policies,adapter,record,policy,setTime:value=>clock=value,wrongAck:()=>wrongAck=true};
}
describe('trusted OpenHAB-backed shade execution owner',()=>{
 it('never admits a caller-controlled manual label or origin without the authenticated manual path',async()=>{
  const f=fixture();await expect(f.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:'UP',source:'manual'},{})).rejects.toThrow();expect(f.commands).toEqual([]);
  expect(f.owner.authenticateManual('Basic invalid')).toBeNull();
 });
 it('signs a trusted explicit manual operation independently of OFF/nightly protection',async()=>{
  const f=fixture();const token=f.owner.authenticateManual(auth);expect(token).not.toBeNull();
  const result=await f.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:25},token);
  expect(result.status).toBe('published_awaiting_adapter_result');expect(f.commands).toHaveLength(1);
  expect(f.commands[0].envelope).toMatchObject({origin:'manual',shade_id:'bathroom_18',command:25,adapter_session:'fixture-adapter',source_context:{commissioned_epoch:epoch,source_generation:1,bridge_id:'001122334455',device_id:'001122334456'}});
 });
 it('requires individually commissioned operations, current adapter identity and bounded request IDs',async()=>{
  for(const mutate of [f=>f.record.manualReleased=false,f=>f.record.commissionedEpoch=null,f=>f.adapter.ready=false,f=>f.adapter.emitted_at=NOW/1000-91]){
   const f=fixture();mutate(f);await expect(f.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:'UP'},f.owner.authenticateManual(auth))).rejects.toThrow();expect(f.commands).toEqual([]);
  }
 });
 it('never broadcasts groups and rejects unknown slots or programming commands',async()=>{
  const f=fixture();for(const request of [{request_id:rid,requested_at_ms:NOW,slot:'all',command:'DOWN'},{request_id:rid,requested_at_ms:NOW,slot:1,command:'UP'},{request_id:rid,requested_at_ms:NOW,slot:18,command:'PAIR'},{request_id:rid,requested_at_ms:NOW,slot:18,command:true}])await expect(f.owner.requestManual(request,f.owner.authenticateManual(auth))).rejects.toThrow();expect(f.commands).toEqual([]);
 });
 it('reports inhibition effective only after the exact final-dispatch acknowledgement',async()=>{
  const f=fixture();expect(await f.owner.synchronizePolicy()).toMatchObject({status:'effective'});expect(f.commands).toEqual([]);
  expect(f.policies[0].envelope).toMatchObject({generation:gen,global_released:false,override:{state:'ON',authoritative:true},zones:{bathroom:{enabled:false,authoritative:true}}});
  f.wrongAck();expect(await f.owner.synchronizePolicy()).toMatchObject({status:'synchronization_pending'});expect(f.commands).toEqual([]);
 });
 it('does not turn preference changes, page reads or automatic requests into motion',async()=>{
  const f=fixture();await f.owner.capabilities();f.policy.zones.bathroom.saved='ON';await f.owner.synchronizePolicy();await expect(f.owner.requestAutomatic({})).rejects.toThrow(/unreleased/);expect(f.commands).toEqual([]);
 });
 it('does not redate an old HTTP intent into a new movement after owner recreation',async()=>{
  const f=fixture();f.setTime(NOW+11000);f.adapter.emitted_at=(NOW+11000)/1000;
  await expect(f.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:'UP'},f.owner.authenticateManual(auth))).rejects.toThrow(/expired/);expect(f.commands).toEqual([]);
 });
 it('retains an authenticated operator STOP path after new movement becomes unready or normal identities saturate',async()=>{
  const f=fixture({ledgerLimit:1});const token=f.owner.authenticateManual(auth);
  await f.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:'UP'},token);
  f.adapter.ready=false;
  const result=await f.owner.requestManual({request_id:'00000000-0000-4000-8000-000000000005',requested_at_ms:NOW,slot:18,command:'STOP'},token);
  expect(result.status).toBe('published_awaiting_adapter_result');expect(f.commands).toHaveLength(2);expect(f.commands[1].envelope.command).toBe('STOP');
 });
 it('expands a manual group into individually qualified requests and reports unmapped members without a broadcast',async()=>{
  const f=fixture();const result=await f.owner.requestManualBatch({request_id:rid,requested_at_ms:NOW,slots:[18,26],command:'UP'},f.owner.authenticateManual(auth));
  expect(result.status).toBe('partially_published');expect(result.results.map(row=>[row.slot,row.status])).toEqual([[18,'published_awaiting_adapter_result'],[26,'rejected']]);expect(f.commands).toHaveLength(1);expect(f.commands[0].envelope.shade_id).toBe('bathroom_18');
  expect(f.commands[0].envelope.expires_at_ms).toBe(NOW+30000);
 });
 it('binds a batch identity to its original complete membership and intent',async()=>{
  const f=fixture(),token=f.owner.authenticateManual(auth),request={request_id:rid,requested_at_ms:NOW,slots:[18],command:'UP'};
  await f.owner.requestManualBatch(request,token);
  await expect(f.owner.requestManualBatch({...request,slots:[18,26]},token)).rejects.toThrow(/identity_conflict/);
  expect(f.commands).toHaveLength(1);
 });
 it('restores command and batch identities as history without re-publishing after owner restart',async()=>{
  let saved=null;const store={loadLedger:()=>saved,saveLedger:value=>{saved=structuredClone(value);}};
  const first=fixture(store),request={request_id:rid,requested_at_ms:NOW,slots:[18],command:'UP'};
  await first.owner.requestManualBatch(request,first.owner.authenticateManual(auth));expect(saved).not.toBeNull();
  const restarted=fixture(store),token=restarted.owner.authenticateManual(auth);
  await restarted.owner.requestManualBatch(request,token);expect(restarted.commands).toEqual([]);
  await expect(restarted.owner.requestManualBatch({...request,slots:[18,26]},token)).rejects.toThrow(/identity_conflict/);
 });
 it('commits request identity before publication and refuses movement on owner journal failure',async()=>{
  const f=fixture({saveLedger:()=>{throw new Error('synthetic disk failure');}});
  await expect(f.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:'UP'},f.owner.authenticateManual(auth))).rejects.toThrow(/journal/);expect(f.commands).toEqual([]);
 });
 it('reclaims only expired terminal capacity and preserves STOP after durable owner restart',async()=>{
  let saved=null;const store={ledgerLimit:1,loadLedger:()=>saved,saveLedger:value=>{saved=structuredClone(value);}};
  const f=fixture(store),token=f.owner.authenticateManual(auth);
  await f.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:'UP'},token);
  f.setTime(NOW+60000);f.adapter.emitted_at=(NOW+60000)/1000;
  await expect(f.owner.requestManual({request_id:'00000000-0000-4000-8000-000000000005',requested_at_ms:NOW+60000,slot:18,command:'DOWN'},token)).resolves.toMatchObject({status:'published_awaiting_adapter_result'});
  await f.owner.requestManual({request_id:'00000000-0000-4000-8000-000000000006',requested_at_ms:NOW+60000,slot:18,command:'STOP'},token);
  const restarted=fixture(store);restarted.setTime(NOW+120000);restarted.adapter.emitted_at=(NOW+120000)/1000;
  await expect(restarted.owner.requestManual({request_id:'00000000-0000-4000-8000-000000000007',requested_at_ms:NOW+120000,slot:18,command:'STOP'},restarted.owner.authenticateManual(auth))).resolves.toMatchObject({status:'published_awaiting_adapter_result'});
  await expect(restarted.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:'UP'},restarted.owner.authenticateManual(auth))).rejects.toThrow(/expired/);
 });
 it('retains an unpublished terminal batch after initial journal failure without retrying it',async()=>{
  let unavailable=true;
  const f=fixture({saveLedger:()=>{if(unavailable)throw new Error('synthetic failure');}}),token=f.owner.authenticateManual(auth);
  const request={request_id:rid,requested_at_ms:NOW,slots:[18],command:'UP'};
  await expect(f.owner.requestManualBatch(request,token)).rejects.toThrow(/journal/);
  unavailable=false;
  expect(await f.owner.requestManualBatch(request,token)).toMatchObject({status:'not_published',reason:'owner_journal_unavailable'});
  expect(f.commands).toEqual([]);
 });
 it('refuses fresh movement after a material wall-clock rollback',async()=>{
  const f=fixture(),token=f.owner.authenticateManual(auth);
  await f.owner.requestManual({request_id:rid,requested_at_ms:NOW,slot:18,command:'UP'},token);
  f.setTime(NOW-2000);
  await expect(f.owner.requestManual({request_id:'00000000-0000-4000-8000-000000000009',requested_at_ms:NOW-2000,slot:18,command:'DOWN'},token)).rejects.toThrow(/clock_rollback/);
  expect(f.commands).toHaveLength(1);
 });
 it('is idempotent for a submitted manual identity and never retries uncertain publication',async()=>{
  const f=fixture();const token=f.owner.authenticateManual(auth),request={request_id:rid,requested_at_ms:NOW,slot:18,command:'STOP'};
  await f.owner.requestManual(request,token);await f.owner.requestManual(request,token);expect(f.commands).toHaveLength(1);
  await expect(f.owner.requestManual({...request,command:'DOWN'},token)).rejects.toThrow();
 });
});
