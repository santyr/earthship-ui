import {qualificationObservation} from './household-qualification.js';
import {proposal} from './household-observation.js';
export function recommendationObservation(){
 const v=qualificationObservation();v.schema='earthship-household-observation/v4';
 const night=proposal();Object.assign(night,{intent_id:'9'.repeat(64),type:'SET_NIGHT_LOAD_OVERRIDE',confidence:'unavailable',reasons:['low_soc']});v.proposals.push(night);
 for(const p of v.proposals)Object.assign(p,{parameters:p.type==='SET_NIGHT_LOAD_OVERRIDE'?{command:'OFF'}:{},created_at:v.decision_at,expires_at:'2026-10-12T03:02:30+00:00'});
 const family=v.qualification_report.families.find(f=>f.intent_type===night.type);family.proposal_count=1;
 family.gates[2]={id:'hard_constraints',evidence_status:'observed',reason:'original_family_checks_replayed'};
 family.gates[3]={id:'unknown_fails_closed',evidence_status:'observed',reason:'unknown_checks_blocked_in_original'};
 return v;
}

export function currentDeviceObservation(){
 const v=recommendationObservation();
 for(const p of v.proposals)if(p.type==='SET_NIGHT_LOAD_OVERRIDE')Object.assign(p,{type:'SET_NIGHT_LOAD_DEVICE',parameters:{device:'dishwasher',command:'ON'}});
 for(const family of v.qualification_report.families){
  const proposals=v.proposals.filter(p=>p.type===family.intent_type),unknown=proposals.some(p=>p.hard_checks.some(c=>c.status==='unknown'));
  family.proposal_count=proposals.length;
  family.gates[2]={id:'hard_constraints',evidence_status:proposals.length?'observed':'unavailable',reason:proposals.length?'original_family_checks_replayed':'no_family_proposal'};
  family.gates[3]={id:'unknown_fails_closed',evidence_status:unknown?'observed':'unavailable',reason:unknown?'unknown_checks_blocked_in_original':'unknown_case_not_observed'};
 }
 return v;
}
