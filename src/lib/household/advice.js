import {uniqueObjectKeys} from './observation.js';
/** Closed human-advice reader. No command construction or actuation imports. */
const fields='schema evaluation_version snapshot_id policy_sha256 evaluated_at valid_until timezone domains recommendations human_action_only automatic_actuation report_id'.split(' ');
const recFields='recommendation_id episode_id snapshot_id policy_sha256 kind target action action_spec baseline comparison effects evidence_basis limitations conditions invalidation_triggers decision_at start_at end_at review_at valid_until source_valid_until source_refs model_refs reason human_action_only automatic_actuation'.split(' ');
const kinds=['SHADE_POSITION','VENTILATION_WINDOW','FLEXIBLE_LOAD_TIMING'];
const statuses=['recommendation_available','no_change_recommended','conditional','insufficient_evidence','unavailable'];
export const shape=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const word=v=>typeof v==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9_. -]{0,79}$/.test(v);
const text=v=>typeof v==='string'&&v.length>0&&v.length<=512;
const num=(v,lo,hi)=>typeof v==='number'&&Number.isFinite(v)&&v>=lo&&v<=hi;
const time=v=>typeof v==='string'&&/(?:Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v));
const list=(v,check,max=16)=>Array.isArray(v)&&v.length<=max&&v.every(check);
const excluded=v=>['greywater','feeder','feeding','southoutlet','eastoutlet','set_night_load_override'].includes(v.toLowerCase());
function comparison(v){return list(v,r=>shape(r,['alternative','outcome','metric','value','unit','horizon_end'])&&text(r.alternative)&&text(r.outcome)&&word(r.metric)&&word(r.unit)&&(r.value===null||num(r.value,-100000,100000))&&time(r.horizon_end),8);}
export function parseAdvice(raw,{nowMs=Date.now()}={}){
 try{
  if(typeof raw!=='string'||new TextEncoder().encode(raw).length>32768||!Number.isFinite(nowMs))return null;
  const r=JSON.parse(raw);uniqueObjectKeys(raw);
  if(!shape(r,fields)||r.schema!=='earthship-household-advice/v1'||r.evaluation_version!=='directional-advice-1'||!hash(r.snapshot_id)||!hash(r.report_id)||(r.policy_sha256!==null&&!hash(r.policy_sha256))||r.human_action_only!==true||r.automatic_actuation!==false)return null;
  new Intl.DateTimeFormat('en-US',{timeZone:r.timezone});
  if(!time(r.evaluated_at)||!time(r.valid_until))return null;
  const at=Date.parse(r.evaluated_at),until=Date.parse(r.valid_until);
  if(at>nowMs||until<=at||until-at>1800000)return null;
  if(!shape(r.domains,['shades','ventilation','energy']))return null;
  for(const d of Object.values(r.domains))if(!shape(d,['status','reason','missing','comparison','valid_until'])||!statuses.includes(d.status)||!word(d.reason)||!list(d.missing,word)||!comparison(d.comparison)||!time(d.valid_until)||Date.parse(d.valid_until)<=at||Date.parse(d.valid_until)>until)return null;
  if(!Array.isArray(r.recommendations)||r.recommendations.length>3)return null;
  const ids=new Set();
  for(const rec of r.recommendations){
   if(!shape(rec,recFields)||!['recommendation_id','episode_id','snapshot_id','policy_sha256'].every(k=>hash(rec[k]))||rec.snapshot_id!==r.snapshot_id||rec.policy_sha256!==r.policy_sha256||ids.has(rec.recommendation_id))return null;
   ids.add(rec.recommendation_id);
   if(!kinds.includes(rec.kind)||!word(rec.target)||excluded(rec.target)||!text(rec.action)||!text(rec.reason)||!comparison(rec.comparison)||rec.human_action_only!==true||rec.automatic_actuation!==false)return null;
   if(!shape(rec.baseline,['state','basis','revision'])||!['operator_declaration','independent_position','declared_scheduled_task'].includes(rec.baseline.basis)||!word(rec.baseline.revision))return null;
   if(!shape(rec.effects,['thermal_f','soc_pct','energy_kwh'])||Object.values(rec.effects).some(v=>v!==null&&!num(v,-10000,10000))||!['rule_based','model_compared','experimental'].includes(rec.evidence_basis))return null;
   if(!['limitations','conditions','invalidation_triggers'].every(k=>list(rec[k],text))||!['source_refs','model_refs'].every(k=>list(rec[k],hash))||!rec.source_refs.length)return null;
   if(rec.comparison.length<2||(rec.evidence_basis==='rule_based'&&Object.values(rec.effects).some(v=>v!==null)))return null;
   if(rec.kind==='SHADE_POSITION'){
    const positions=Array.isArray(rec.baseline.state)?rec.baseline.state:[rec.baseline.state];
    if(!positions.length||positions.length>26||!positions.every(p=>num(p,0,100))||(rec.evidence_basis==='rule_based'&&![0,100].includes(rec.action_spec.position_open_pct)))return null;
   }else if(rec.kind==='VENTILATION_WINDOW'){if(!['open','closed'].includes(rec.baseline.state))return null;}
   else if(!time(rec.baseline.state))return null;
   const s=rec.action_spec;
   if(rec.kind==='SHADE_POSITION'&&(!shape(s,['position_open_pct','shade_ids'])||!num(s.position_open_pct,0,100)||!list(s.shade_ids,word,26)||!s.shade_ids.length))return null;
   if(rec.kind==='VENTILATION_WINDOW'&&(!shape(s,['opening_state','window_minutes'])||!['open','closed'].includes(s.opening_state)||!num(s.window_minutes,1,60)))return null;
   if(rec.kind==='FLEXIBLE_LOAD_TIMING'&&(!shape(s,['scheduled_start'])||!time(s.scheduled_start)))return null;
   const clockKeys=['decision_at','start_at','end_at','review_at','valid_until','source_valid_until'];
   if(!clockKeys.every(k=>time(rec[k])))return null;
   const t=Object.fromEntries(clockKeys.map(k=>[k,Date.parse(rec[k])]));
   if(t.decision_at!==at||t.start_at<at||t.start_at>=t.end_at||t.review_at<=at||t.review_at>t.valid_until||t.valid_until>Math.min(until,t.source_valid_until,t.end_at))return null;
  }
  return {report:r,domains:Object.fromEntries(Object.entries(r.domains).map(([key,d])=>[key,nowMs>=Date.parse(d.valid_until)?{...d,status:'unavailable',reason:'evaluation_expired'}:d])),expired:nowMs>=until,current:r.recommendations.filter(rec=>nowMs<Math.min(until,Date.parse(rec.valid_until),Date.parse(rec.source_valid_until),Date.parse(rec.end_at)))};
 }catch{return null;}
}
export function feedbackStatus(rec,events,nowMs=Date.now()){
 const rows=events.filter(e=>e.episode_id===rec.episode_id&&Date.parse(e.at)<=nowMs),undone=new Set(rows.filter(e=>e.kind==='undo').map(e=>e.corrects));
 const latest=rows.filter(e=>e.kind!=='undo'&&!undone.has(e.event_id)).at(-1);
 if(!latest)return 'unseen';if(latest.kind==='snooze')return nowMs<Date.parse(latest.snooze_until)?'snoozed':'unseen';
 return {dismiss:'dismissed',acknowledge:'seen',report_action_taken:'action_self_reported',target_observed:'target_observed'}[latest.kind]??'unseen';
}
