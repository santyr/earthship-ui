// Server-only command owner. OpenHAB remains the source of zone/night policy;
// this owner authenticates explicit manual requests and transports its decisions.
import { createHash, randomUUID, timingSafeEqual } from 'node:crypto';
import { SHADE_SLOTS } from './catalog.js';
import { canonicalOwnerJson, signOwnerCommand, signOwnerPolicy } from './ownerWire.js';
const uuid=value=>typeof value==='string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const finite=value=>typeof value==='number' && Number.isFinite(value);
const fail=reason=>Object.assign(new Error(reason),{code:reason});
const zones=['kitchen','living','bathroom','bedroom'];
const command=value=>['UP','DOWN','STOP'].includes(value) || Number.isInteger(value)&&value>=0&&value<=100;

export function createShadeExecutionOwner({inventory=[],key,manualAuthorizationHash,readAdapter,readPolicy,
  publishCommand,publishPolicy,readPolicyAck,now=Date.now,monotonic=()=>performance.now(),ledgerLimit=512,loadLedger=()=>null,saveLedger=()=>{}}={}) {
  const ownerSession=randomUUID(),manualTokens=new WeakSet(),ledger=new Map(),batchLedger=new Map();
  let serial=Promise.resolve(),pending=0;
  const stopRequests=new Map(),activeRequests=new Set(),activeBatches=new Set();
  let clockHighWater=now(),retiredBefore=-1;
  function checkClock(){const at=now();if(at+1000<clockHighWater)throw fail('owner_clock_rollback');clockHighWater=Math.max(clockHighWater,at);}
  function persistLedger() {
    try {
      const value=saveLedger({schema:'earthship-shade-owner-ledger/v1',clockHighWater_ms:clockHighWater,retiredBefore_ms:retiredBefore,commands:[...ledger.entries()].map(([id,entry])=>({id,...structuredClone(entry)})),batches:[...batchLedger.entries()].map(([id,entry])=>({id,...structuredClone(entry)}))});
      if(value?.then)throw new Error();
    }catch{throw fail('owner_journal_unavailable');}
  }
  const restored=loadLedger();
  if(restored!==null&&restored!==undefined){
    if(restored.schema!=='earthship-shade-owner-ledger/v1'||!Array.isArray(restored.commands)||!Array.isArray(restored.batches)
      ||restored.commands.length>ledgerLimit+26||restored.batches.length>64)throw fail('owner_journal_invalid');
    if(restored.clockHighWater_ms!==undefined){if(!Number.isSafeInteger(restored.clockHighWater_ms)||!Number.isSafeInteger(restored.retiredBefore_ms))throw fail('owner_journal_invalid');clockHighWater=Math.max(clockHighWater,restored.clockHighWater_ms);retiredBefore=restored.retiredBefore_ms;}
    for(const [rows,target,batch] of [[restored.commands,ledger,false],[restored.batches,batchLedger,true]])for(const record of rows){
      let request;try{request=JSON.parse(record.fingerprint);}catch{throw fail('owner_journal_invalid');}
      if(!uuid(record.id)||request.request_id!==record.id||target.has(record.id)||canonicalOwnerJson(request)!==record.fingerprint
        ||!Number.isSafeInteger(request.requested_at_ms)||!command(request.command)||record.result?.request_id!==record.id
        ||typeof record.result.status!=='string'||record.result.status.length>64
        ||(batch?(!Array.isArray(request.slots)||request.slots.length>26):(!Number.isInteger(request.slot)||request.slot<1||request.slot>26)))throw fail('owner_journal_invalid');
      const {id,...entry}=structuredClone(record);
      entry.requested_at_ms=request.requested_at_ms;
      entry.retentionDeadlineMono=monotonic()+Math.max(0,Math.min(31000,request.requested_at_ms+30000-now()));
      if(['admission_pending','batch_pending'].includes(entry.result.status))entry.result={...entry.result,previous_status:entry.result.status,status:'publication_uncertain_no_retry',reason:'owner_restart_no_replay'};
      target.set(id,entry);
    }
    if([...batchLedger.keys()].some(id=>ledger.has(id)))throw fail('owner_journal_invalid');
  }

  function reclaim(map,active,pressure) {
    for(const [id,entry] of map){
      if(!pressure())break;
      const pending=['admission_pending','batch_pending'].includes(entry.result.status);
      if(!active.has(id)&&!pending&&entry.requested_at_ms+30000<=now()&&monotonic()>=entry.retentionDeadlineMono){
        retiredBefore=Math.max(retiredBefore,entry.requested_at_ms);map.delete(id);
      }
    }
  }
  function serialize(operation) {
    if(pending>=32)return Promise.reject(fail('owner_busy'));
    pending++;
    const result=serial.then(operation);serial=result.catch(()=>{}).finally(()=>pending--);return result;
  }
  function lookup(slot) {
    const expected=SHADE_SLOTS.find(row=>row.number===slot),matches=inventory.filter(row=>row.slot===slot);
    if(!expected||matches.length!==1)throw fail('unmapped_shade');
    const record=matches[0];
    if(record.zone!==expected.room||!uuid(record.commissionedEpoch)||record.manualReleased!==true
      || !['id','model','firmware','reference','deviceId'].every(k=>typeof record[k]==='string'&&record[k].length>0&&record[k].length<=128)
      || !/^[0-9A-F]{12,32}$/.test(record.deviceId)|| !Array.isArray(record.operations)
      || record.operations.some(op=>!['UP','DOWN','STOP'].includes(op)))throw fail('shade_not_commissioned');
    return record;
  }
  async function adapter({allowNotReady=false}={}) {
    const value=await readAdapter();
    if(value?.schema_version!==2||(!allowNotReady&&value.ready!==true)||typeof value.adapter_session_id!=='string'||!value.adapter_session_id
      ||!Number.isSafeInteger(value.source_generation)||value.source_generation<0
      ||!finite(value.emitted_at)||now()-value.emitted_at*1000>90_000||now()-value.emitted_at*1000< -5000
      ||typeof value.bridge_id!=='string'||!/^[0-9A-F]{12,32}$/.test(value.bridge_id))throw fail('adapter_unavailable');
    return value;
  }
  function authenticateManual(authorization) {
    if(typeof authorization!=='string'||authorization.length>2048||!/^Basic [A-Za-z0-9+/=]+$/.test(authorization)
      ||typeof manualAuthorizationHash!=='string'||!/^[0-9a-f]{64}$/.test(manualAuthorizationHash))return null;
    const actual=createHash('sha256').update(authorization).digest(),expected=Buffer.from(manualAuthorizationHash,'hex');
    if(!timingSafeEqual(actual,expected))return null;
    const token=Object.freeze({});manualTokens.add(token);return token;
  }
  async function manual(request,authority,maxTtlMs=10_000) {
    if(!authority||!manualTokens.has(authority))throw fail('manual_authentication_required');
    if(!request||Object.keys(request).sort().join(',')!=='command,request_id,requested_at_ms,slot'
      ||!uuid(request.request_id)||!Number.isInteger(request.slot)||!command(request.command)
      ||!Number.isSafeInteger(request.requested_at_ms))throw fail('invalid_manual_request');
    checkClock();
    const expires=request.requested_at_ms+maxTtlMs;
    if(request.requested_at_ms<=retiredBefore)throw fail('manual_request_expired');
    if(now()>=expires||now()-request.requested_at_ms< -1000)throw fail('manual_request_expired');
    const fingerprint=canonicalOwnerJson(request),prior=ledger.get(request.request_id);
    if(batchLedger.has(request.request_id))throw fail('request_identity_conflict');
    if(prior){if(prior.fingerprint!==fingerprint)throw fail('request_identity_conflict');return structuredClone(prior.result);}
    const record=lookup(request.slot);
    if(typeof request.command==='number'?record.percentage!==true:!record.operations.includes(request.command))throw fail('operation_not_commissioned');
    const pressure=()=>[...ledger.values()].filter(entry=>!entry.reserved).length>=ledgerLimit;
    if(pressure())reclaim(ledger,activeRequests,pressure);
    const ordinary=[...ledger.values()].filter(entry=>!entry.reserved).length,reserved=ordinary>=ledgerLimit;
    if(reserved&&(request.command!=='STOP'||[...ledger.values()].some(entry=>entry.reserved&&entry.slot===request.slot)))throw fail('request_ledger_full');
    const bound=canonicalOwnerJson(record);
    // Reserve identity/capacity synchronously before any read can yield to a
    // concurrent priority STOP. Publication is never repeated for this identity.
    const entry={fingerprint,reserved,slot:request.slot,requested_at_ms:request.requested_at_ms,retentionDeadlineMono:monotonic()+Math.max(30000,request.requested_at_ms+30000-now()),result:{request_id:request.request_id,status:'admission_pending'}};
    ledger.set(request.request_id,entry);
    try{persistLedger();}catch(error){entry.result={request_id:request.request_id,status:'rejected',reason:'owner_journal_unavailable'};throw error;}
    activeRequests.add(request.request_id);
    const deadline=monotonic()+Math.max(0,expires-now());
    try {
      const source=await adapter({allowNotReady:request.command==='STOP'});
      let policy=null;try{if(request.command!=='STOP')policy=await readPolicy();}catch{/* manual is independent of automation policy */}
      if(canonicalOwnerJson(lookup(request.slot))!==bound)throw fail('installation_changed');
      checkClock();
      if(now()>=expires||monotonic()>=deadline)throw fail('manual_request_expired');
      const envelope={schema:'dooya-owner-command/v1',request_id:request.request_id,shade_id:record.id,
        command:request.command,origin:'manual',created_at_ms:request.requested_at_ms,expires_at_ms:expires,
        adapter_session:source.adapter_session_id,owner_session:ownerSession,
        policy_generation:policy?.connected===true&&uuid(policy.sourceGeneration)?policy.sourceGeneration:null,
        source_context:{commissioned_epoch:record.commissionedEpoch,source_generation:source.source_generation,
          bridge_id:source.bridge_id,device_id:record.deviceId}};
      const signed=signOwnerCommand(envelope,key);
      entry.envelope=envelope;entry.wire_sha256=createHash('sha256').update(canonicalOwnerJson(signed)).digest('hex');
      entry.result={request_id:request.request_id,status:'publication_uncertain_no_retry'};
      persistLedger();
      checkClock();
      if(now()>=expires||monotonic()>=deadline)throw fail('manual_request_expired');
      const receipt=await publishCommand(signed);
      if(receipt?.published===true)entry.result={request_id:request.request_id,status:'published_awaiting_adapter_result'};
    }catch(error){
      if(entry.result.status==='admission_pending'){
        entry.result={request_id:request.request_id,status:'rejected',reason:error.code??'manual_admission_refused'};
        throw error;
      }
      // A publication error cannot prove that the broker did not receive it.
    }finally{activeRequests.delete(request.request_id);}
    try{persistLedger();}catch{entry.result={request_id:request.request_id,status:'publication_uncertain_no_retry',reason:'owner_journal_unavailable'};}
    return structuredClone(entry.result);
  }
  async function synchronize() {
    const source=await adapter();
    let policy;try{policy=await readPolicy();}catch{policy=null;}
    const authoritative=policy?.connected===true&&uuid(policy.sourceGeneration);
    const at=now(),value={schema:'dooya-owner-policy/v1',generation:authoritative?policy.sourceGeneration:randomUUID(),
      owner_session:ownerSession,adapter_session:source.adapter_session_id,issued_at_ms:at,expires_at_ms:at+30_000,
      zones:Object.fromEntries(zones.map(zone=>[zone,{enabled:authoritative&&policy.zones?.[zone]?.authoritative===true
        ?policy.zones[zone].saved==='ON':null,authoritative:Boolean(authoritative&&policy.zones?.[zone]?.authoritative===true)}])),
      override:{state:authoritative&&policy.override?.authoritative===true?policy.override.state:null,
        authoritative:Boolean(authoritative&&policy.override?.authoritative===true)},global_released:false};
    await publishPolicy(signOwnerPolicy(value,key));
    const ack=await readPolicyAck();
    const current=await adapter();
    let latestPolicy;try{latestPolicy=await readPolicy();}catch{latestPolicy=null;}
    const policyUnchanged=authoritative?latestPolicy?.connected===true&&latestPolicy.sourceGeneration===value.generation:latestPolicy?.connected!==true;
    const effective=policyUnchanged&&ack?.schema==='dooya-policy-ack/v1'&&ack.status==='effective'
      &&ack.adapter_session===source.adapter_session_id&&ack.source_generation===source.source_generation
      &&ack.owner_session===ownerSession&&ack.policy_generation===value.generation
      &&ack.policy_issued_at_ms===at&&finite(ack.effective_at_ms)&&ack.effective_at_ms>=at&&ack.effective_at_ms<=now()+1000
      &&now()<=value.expires_at_ms&&current.adapter_session_id===source.adapter_session_id
      &&current.source_generation===source.source_generation;
    return {status:effective?'effective':'synchronization_pending',generation:value.generation,
      adapterSession:source.adapter_session_id,automaticReleased:false};
  }
  function requestManual(request,authority) {
    if(request?.command!=='STOP')return serialize(()=>manual(request,authority));
    // An operator STOP must not wait behind a blocked ordinary publication.
    // Separate bounded per-shade serialization prevents duplicate STOP sends.
    if(!authority||!manualTokens.has(authority))return Promise.reject(fail('manual_authentication_required'));
    let fingerprint;try{lookup(request.slot);fingerprint=canonicalOwnerJson(request);}catch{return Promise.reject(fail('invalid_manual_request'));}
    const active=stopRequests.get(request.slot);
    if(active)return active.fingerprint===fingerprint?active.promise:Promise.reject(fail('operator_stop_busy'));
    const promise=manual(request,authority).finally(()=>stopRequests.delete(request.slot));
    stopRequests.set(request.slot,{fingerprint,promise});return promise;
  }
  async function batch(request,authority) {
    if(!authority||!manualTokens.has(authority))throw fail('manual_authentication_required');
    if(!request||Object.keys(request).sort().join(',')!=='command,request_id,requested_at_ms,slots'
      ||!uuid(request.request_id)||!Number.isSafeInteger(request.requested_at_ms)||!command(request.command)
      ||!Array.isArray(request.slots)||request.slots.length<1||request.slots.length>26
      ||new Set(request.slots).size!==request.slots.length||request.slots.some(slot=>!Number.isInteger(slot)||slot<1||slot>26))throw fail('invalid_manual_batch');
    const fingerprint=canonicalOwnerJson(request),prior=batchLedger.get(request.request_id);
    if(ledger.has(request.request_id))throw fail('request_identity_conflict');
    if(prior){if(prior.fingerprint!==fingerprint)throw fail('request_identity_conflict');return structuredClone(prior.result);}
    checkClock();
    if(request.requested_at_ms<=retiredBefore||now()-request.requested_at_ms>=30000||now()-request.requested_at_ms< -1000)throw fail('manual_request_expired');
    if(batchLedger.size>=64)reclaim(batchLedger,activeBatches,()=>batchLedger.size>=64);
    if(batchLedger.size>=64)throw fail('batch_identity_ledger_full');
    const results=[],entry={fingerprint,requested_at_ms:request.requested_at_ms,retentionDeadlineMono:monotonic()+Math.max(30000,request.requested_at_ms+30000-now()),result:{request_id:request.request_id,status:'batch_pending',results}};
    batchLedger.set(request.request_id,entry);
    try{persistLedger();}catch(error){entry.result={request_id:request.request_id,status:'not_published',results:[],reason:'owner_journal_unavailable'};throw error;}
    activeBatches.add(request.request_id);
    try{
    for(const slot of request.slots) {
      let hex=createHash('sha256').update(`dooya-manual-batch/v1:${request.request_id}:${slot}`).digest('hex').slice(0,32).split('');
      hex[12]='5';hex[16]=((parseInt(hex[16],16)&3)|8).toString(16);hex=hex.join('');
      const request_id=`${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
      try{results.push({slot,...await manual({request_id,requested_at_ms:request.requested_at_ms,slot,command:request.command},authority,30_000)});}
      catch(error){results.push({slot,request_id,status:error.code==='manual_request_expired'?'expired':'rejected',reason:error.code??'manual_admission_refused'});}
    }
    const published=results.filter(row=>row.status==='published_awaiting_adapter_result').length;
    entry.result={request_id:request.request_id,status:published===results.length?'published_awaiting_adapter_result':published?'partially_published':'not_published',results};
    persistLedger();
    return structuredClone(entry.result);
    }finally{activeBatches.delete(request.request_id);}
  }
  return {authenticateManual,requestManual,
    requestManualBatch:(request,authority)=>request?.command==='STOP'?batch(request,authority):serialize(()=>batch(request,authority)),
    synchronizePolicy:()=>serialize(synchronize),
    requestAutomatic:async()=>{throw fail('automatic_actuation_unreleased');},
    capabilities:async()=>({schemaVersion:1,automaticReleased:false,slots:SHADE_SLOTS.map(slot=>{
      try{const record=lookup(slot.number);return {slot:slot.number,zone:slot.room,commissioned:true,operations:[...record.operations],percentage:record.percentage===true};}
      catch{return {slot:slot.number,zone:slot.room,commissioned:false,operations:[],percentage:false};}
    })})};
}
