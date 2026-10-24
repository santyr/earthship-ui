import {describe,it,expect} from 'vitest';
import {AUTOMATED_QUALIFICATION_FAMILIES} from '../src/lib/household/qualification.js';
import {parseHouseholdObservation} from '../src/lib/household/observation.js';
import {AT,policyObservation} from './fixtures/household-observation.js';
import {qualificationObservation} from './fixtures/household-qualification.js';
const parse=v=>parseHouseholdObservation(JSON.stringify(v),{nowMs:AT});
it('admits all twelve evidence gates per family without creating release authority',()=>{
 const v=qualificationObservation(),r=parse(v);expect(r).not.toBeNull();expect(r.qualification_report).toEqual(v.qualification_report);
 expect(r.qualification_report.families).toHaveLength(4);expect(r.qualification_report.families[0].gates).toHaveLength(12);
});
it('retains original assessment clocks and expires display without graduating',()=>{
 const v=qualificationObservation();const r=parseHouseholdObservation(JSON.stringify(v),{nowMs:AT+3600000});expect(r).not.toBeNull();
 expect(r.expired).toBe(true);expect(r.qualification_report).toEqual(v.qualification_report);
});
describe('closed qualification evidence contract',()=>{
 it.each(['root_authority','family_authority','graduated','private','family_private','gate_private','scope','receipt','snapshot','clock','family_missing','family_duplicate','type','capability','owner','count','gate_missing','gate_duplicate','gate_reordered','evidence','reason','unsupported_pass'])('refuses %s',damage=>{
  const v=qualificationObservation(),q=v.qualification_report,f=q.families[0],g=f.gates[0];
  if(damage==='root_authority')q.release_authorized=true;
  if(damage==='family_authority')f.release_authorized=true;
  if(damage==='graduated')q.status='qualified';
  if(damage==='private')q.private_path='/private/input';
  if(damage==='family_private')f.raw='private';
  if(damage==='gate_private')g.raw='private';
  if(damage==='scope')q.scope='release';
  if(damage==='receipt')q.receipt_sha256='f'.repeat(64);
  if(damage==='snapshot')q.snapshot_id='f'.repeat(64);
  if(damage==='clock')q.decision_at='2026-10-12T03:01:00Z';
  if(damage==='family_missing')q.families.pop();
  if(damage==='family_duplicate')q.families[1]=structuredClone(f);
  if(damage==='type')f.intent_type='REQUEST_SHADE_POSITION';
  if(damage==='capability')f.capability_id='feeder-request-v1';
  if(damage==='owner')f.owner='/private/owner';
  if(damage==='count')f.proposal_count=0;
  if(damage==='gate_missing')f.gates.pop();
  if(damage==='gate_duplicate')f.gates[1]=structuredClone(g);
  if(damage==='gate_reordered')f.gates.reverse();
  if(damage==='evidence')g.evidence_status='qualified';
  if(damage==='reason')g.reason='release_granted';
  if(damage==='unsupported_pass')f.gates[4].evidence_status='observed';
  expect(parse(v)).toBeNull();
 });
});
it('does not admit assessment bytes under old observation schema',()=>{
 const v=qualificationObservation();v.schema='earthship-household-observation/v2';expect(parse(v)).toBeNull();expect(parse(policyObservation())).not.toBeNull();
});


it('accepts current qualification v2 containing only automated household families',()=>{
 const v=qualificationObservation();
 v.qualification_report.schema='earthship-household-intent-qualification/v2';
 v.qualification_report.families=v.qualification_report.families.filter(f=>f.intent_type!=='RUN_FEEDER_CYCLE');
 const result=parse(v);expect(result).not.toBeNull();
 expect(result.qualification_report.families.map(f=>f.intent_type)).toEqual(['RUN_GREYWATER_CYCLE','SET_NIGHT_LOAD_OVERRIDE','SET_NIGHT_LOAD_DEVICE']);
});
it('rejects feeder release qualification in a current v2 report',()=>{
 const v=qualificationObservation();v.qualification_report.schema='earthship-household-intent-qualification/v2';
 expect(parse(v)).toBeNull();
});


function currentQualification() {
 const v=qualificationObservation();v.planner_version='bounded_exhaustive_v2';
 v.proposals=[];v.policy_comparison.comparisons=[];
 v.qualification_report.schema='earthship-household-intent-qualification/v3';
 v.qualification_report.families=v.qualification_report.families.filter(f=>f.intent_type==='SET_NIGHT_LOAD_DEVICE');
 return v;
}
it('accepts the current scope-bound planner v2 and device-only qualification v3 together',()=>{
 const v=currentQualification(),r=parse(v);expect(r).not.toBeNull();
 expect(r.planner_version).toBe('bounded_exhaustive_v2');
 expect(r.qualification_report.families.map(f=>f.intent_type)).toEqual(['SET_NIGHT_LOAD_DEVICE']);
 expect(r.automatic_actuation).toBe(false);
});
it('excludes manual greywater and coupled overrides from the current qualification catalog',()=>{
 expect(AUTOMATED_QUALIFICATION_FAMILIES.map(([kind])=>kind)).toEqual(['SET_NIGHT_LOAD_DEVICE']);
});
it.each(['RUN_GREYWATER_CYCLE','SET_NIGHT_LOAD_OVERRIDE','RUN_FEEDER_CYCLE'])(
 'rejects a current v3 qualification report carrying an excluded family: %s',kind=>{
 const v=currentQualification();const old=qualificationObservation().qualification_report.families.find(f=>f.intent_type===kind);
 v.qualification_report.families.unshift(old);expect(parse(v)).toBeNull();
 });
it('refuses to relabel a historical plan as current without its new scope contract',()=>{
 const v=currentQualification();v.planner_version='bounded_exhaustive_v1';expect(parse(v)).toBeNull();
 const old=qualificationObservation();old.planner_version='bounded_exhaustive_v2';expect(parse(old)).toBeNull();
});
it('does not allow a retained greywater proposal to enter a current device-only observation',()=>{
 const v=currentQualification(),old=qualificationObservation();v.proposals=old.proposals;
 v.policy_comparison=old.policy_comparison;expect(parse(v)).toBeNull();
});
