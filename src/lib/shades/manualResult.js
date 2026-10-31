import { manualResultPresentation } from './installation.js';

const uuid=value=>typeof value==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const text=value=>typeof value==='string'&&value.length>0&&value.length<=128&&/^[\x20-\x7e]+$/.test(value);
const shadeId=value=>typeof value==='string'&&/^[a-z][a-z0-9_-]{0,47}$/.test(value);
const labels=Object.freeze({queued:'Queued; awaiting dispatch',selected:'Awaiting adapter dispatch',dispatched:'Dispatched; motor outcome unknown',
 acknowledged:'Acknowledged; awaiting motor Report',target_observed:'Target reported; actor unconfirmed',
 uncertain:'Outcome uncertain; no automatic retry',rejected:'Rejected by adapter',expired:'Request expired',superseded:'Request superseded',
 stopped:'Stop result reported; confirm motor Report',interrupted:'Request interrupted; outcome uncertain'});
const published=new Set(['published_awaiting_adapter_result','publication_uncertain_no_retry']);

function boundedJson(raw) {
 if(typeof raw!=='string'||raw.length>32768)return null;
 // JSON.parse discards duplicate keys. Inspect structural tokens first, including
 // escaped key spellings, so an overwritten identity cannot become a result.
 const stack=[];
 try {
  for(const token of raw.matchAll(/"(?:\\[\s\S]|[^"\\])*"|[{}\[\],:]/g)){
   const value=token[0],top=stack.at(-1);
   if(value==='{'||value==='['){stack.push({object:value==='{',key:value==='{',keys:new Set()});if(stack.length>16)return null;}
   else if(value==='}'||value===']')stack.pop();
   else if(value===','&&top?.object)top.key=true;
   else if(value.startsWith('"')&&top?.object&&top.key){
    const name=JSON.parse(value);if(top.keys.has(name))return null;top.keys.add(name);top.key=false;
   }
  }
  const result=JSON.parse(raw),nodes=[[result,0]];let count=0;
  while(nodes.length){
   const [value,depth]=nodes.pop();if(++count>2048||depth>16)return null;
   if(typeof value==='number'&&!Number.isFinite(value))return null;
   if(value&&typeof value==='object')for(const child of Object.values(value))nodes.push([child,depth+1]);
  }
  return result;
 } catch {return null;}
}

// This reads an outcome record. It never returns a measured position or grants
// command authority; only the separate Report/liveness path can qualify position.
export function parseManualCommandResult(raw,expected) {
 const value=boundedJson(raw),envelope=value?.envelope,source=envelope?.source_context;
 if(!object(value)||value.schema!=='dooya-command-result/v1'||!object(envelope)||!object(source)
  ||!uuid(expected?.requestId)||value.request_id!==expected.requestId||envelope.request_id!==expected.requestId
  ||envelope.schema!=='dooya-owner-command/v1'||envelope.origin!=='manual'||!shadeId(envelope.shade_id)
  ||(expected.shadeId!=null&&envelope.shade_id!==expected.shadeId)
  ||envelope.command!==expected.command||!(Number.isInteger(envelope.command)&&envelope.command>=0&&envelope.command<=100
   ||['UP','DOWN','STOP'].includes(envelope.command))
  ||!uuid(expected.commissionedEpoch)||source.commissioned_epoch!==expected.commissionedEpoch
  ||!Number.isSafeInteger(source.source_generation)||source.source_generation<0||!text(envelope.adapter_session)
  ||(expected.adapterSession!=null&&envelope.adapter_session!==expected.adapterSession)
  ||(expected.sourceGeneration!=null&&source.source_generation!==expected.sourceGeneration)
  ||!Number.isSafeInteger(envelope.created_at_ms)||envelope.created_at_ms!==expected.requestedAtMs
  ||!Number.isSafeInteger(envelope.expires_at_ms)||envelope.expires_at_ms<=envelope.created_at_ms
  ||envelope.expires_at_ms-envelope.created_at_ms>30000
  ||!Number.isSafeInteger(value.updated_at_ms)||value.updated_at_ms<envelope.created_at_ms
  ||!Object.hasOwn(labels,value.status))return null;
 return {requestId:value.request_id,status:value.status,label:labels[value.status],updatedAtMs:value.updated_at_ms};
}

export function manualOutcomePresentation(response,request,slots,itemStates={},contexts={}) {
 const fallback=manualResultPresentation(response,request);
 const numbers=request.slots??[request.slot],rows=[];let known=0;
 for(const number of numbers){
  const slot=slots.find(row=>row.number===number);
  const matches=Array.isArray(request.slots)&&Array.isArray(response?.results)?response.results.filter(row=>row?.slot===number):[];
  const member=Array.isArray(request.slots)?(matches.length===1?matches[0]:null):response;
  const memberId=member?.request_id;
  const unique=(!Array.isArray(request.slots)||(Array.isArray(response?.results)&&response.results.filter(row=>row?.request_id===memberId).length===1));
  const eligible=response?.request_id===request.request_id&&published.has(member?.status)&&uuid(memberId)&&unique;
  const parsed=eligible&&slot?.resultItem?parseManualCommandResult(itemStates[slot.resultItem],{
   requestId:memberId,command:request.command,requestedAtMs:request.requested_at_ms,
   commissionedEpoch:slot.commissionedEpoch,shadeId:slot.adapterShadeId??null,
   adapterSession:contexts[number]?.adapterSession??null,sourceGeneration:contexts[number]?.sourceGeneration??null,
  }):null;
  if(parsed)known++;
  rows.push({slot:number,label:parsed?.label??fallback.rows.find(row=>row.slot===number)?.label??'Result unavailable · outcome unknown'});
 }
 if(Array.isArray(request.slots))return {summary:known?'Adapter results received; review each shade. Position remains based on motor Reports.':response?.request_id===request.request_id&&response.status==='not_published'?fallback.summary:`${fallback.summary} Motor outcome unknown.`,rows};
 return {summary:known?`${rows[0].label}. Position remains based on motor Reports.`:
  published.has(response?.status)?`${fallback.summary} Motor outcome unknown.`:fallback.summary,rows:[]};
}
