/** Curated actual observations; preview values and requested targets stay separate. */
import {shape} from './advice.js';import {uniqueObjectKeys} from './observation.js';
export function parseShadeObservations(raw,{nowMs=Date.now()}={}){
 try{if(typeof raw!=='string'||raw.length>32768)return null;const v=JSON.parse(raw);uniqueObjectKeys(raw);
  if(!shape(v,['schema','generated_at','observations','automatic_actuation'])||v.schema!=='earthship-shade-observations/v1'||v.automatic_actuation!==false||!Number.isFinite(Date.parse(v.generated_at))||Date.parse(v.generated_at)>nowMs||!Array.isArray(v.observations)||v.observations.length>26)return null;
  const ids=new Set();for(const r of v.observations){
   if(!shape(r,['shade_id','zone','epoch','position_open_pct','native_position','native_convention','feedback_basis','movement','origin','observed_at','received_at','available_at','valid_until','quality','time_basis'])||ids.has(r.shade_id))return null;ids.add(r.shade_id);
   if(!['shade_id','zone','epoch'].every(k=>typeof r[k]==='string'&&/^[a-zA-Z0-9_. -]{1,80}$/.test(r[k]))||![r.position_open_pct,r.native_position].every(n=>n===null||typeof n==='number'&&Number.isFinite(n)&&n>=0)||r.position_open_pct>100)return null;
   if(!['closed_100','open_100'].includes(r.native_convention)||!['independent_position','travel_time_estimate','controller_estimate'].includes(r.feedback_basis)||!['opening','closing','stopped','unknown'].includes(r.movement)||!['manual','existing_automation','identified_other','unknown'].includes(r.origin)||!['qualified','unavailable'].includes(r.quality)||!['source_observed','adapter_report_reception'].includes(r.time_basis))return null;
   if(!['observed_at','received_at','available_at','valid_until'].every(k=>Number.isFinite(Date.parse(r[k])))||Date.parse(r.observed_at)>Date.parse(r.received_at)||Date.parse(r.received_at)>Date.parse(r.available_at))return null;
  }
  return {...v,observations:v.observations.map(r=>({...r,current:r.quality==='qualified'&&Date.parse(r.available_at)<=nowMs&&nowMs<Date.parse(r.valid_until)}))};
 }catch{return null;}
}
