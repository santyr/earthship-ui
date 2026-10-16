import {describe,it,expect} from 'vitest';
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
