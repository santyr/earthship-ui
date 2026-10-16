import {expect,it} from 'vitest';
import {policyObservation,AT} from './fixtures/household-observation.js';
import {parseHouseholdObservation} from '../src/lib/household/observation.js';
const parse=(v,nowMs=AT)=>parseHouseholdObservation(JSON.stringify(v),{nowMs});
it('keeps as-issued gate agreement separate from source expiry and all physical permission',()=>{
  const r=policyObservation(),v=parse(r);expect(v).not.toBeNull();
  expect(v.policyComparison.comparisons[0].status).toBe('matching_block');
  expect(v.policyComparison.physical_permission).toBe(false);expect(v.policyComparison.performance_status).toBe('unavailable');
  expect(parse(r,Date.parse(r.policy_comparison.valid_until)).policyComparison.expired).toBe(true);
});
it('keeps a conditional schedule unknown even if the shadow proposal is rejected for another reason',()=>{
  const r=policyObservation(),p=r.policy_comparison;
  Object.assign(p,{status:'unavailable',reason:'eligibility_not_permission',owner_reason:'cycle_completed',owner_scheduling:'conditional',gate:null});
  p.comparisons[0]={intent_id:r.proposals[0].intent_id,status:'unknown',shadow_status:null};
  expect(parse(r).policyComparison.comparisons[0].status).toBe('unknown');
});
it('does not infer agreement from an observed block without any greywater proposal',()=>{
  const r=policyObservation();r.proposals=[];r.policy_comparison.comparisons=[];
  expect(parse(r).policyComparison.status).toBe('observed_block');
});
it.each([
 ['private metadata',r=>{r.policy_comparison.raw='private original';}],
 ['private nested comparison',r=>{r.policy_comparison.comparisons[0].private_path='/private';}],
 ['permission',r=>{r.policy_comparison.physical_permission=true;}],
 ['performance',r=>{r.policy_comparison.performance_status='better';}],
 ['actuation',r=>{r.policy_comparison.automatic_actuation=true;}],
 ['wrong owner',r=>{r.policy_comparison.owner='other';}],
 ['wrong mapped gate',r=>{r.policy_comparison.gate='owner_idle';}],
 ['inconsistent block',r=>{r.policy_comparison.comparisons[0].status='different_gate_result';}],
 ['mismatched shadow status',r=>{r.policy_comparison.comparisons[0].shadow_status='pass';}],
 ['different candidate',r=>{r.policy_comparison.comparisons[0].intent_id='f'.repeat(64);}],
 ['duplicate candidate',r=>{r.policy_comparison.comparisons.push({...r.policy_comparison.comparisons[0]});}],
 ['omitted candidate',r=>{r.policy_comparison.comparisons=[];}],
 ['future evaluation',r=>{r.policy_comparison.evaluated_at='2026-10-12T03:00:31Z';}],
 ['renewed expiry',r=>{r.policy_comparison.valid_until='2026-10-12T03:03:25Z';}],
 ['invalid time object',r=>{r.policy_comparison.evaluated_at={private_path:'/private'};}],
 ['contradictory scheduling',r=>{r.policy_comparison.owner_scheduling='conditional';}],
])('rejects %s before exposing original bytes',(_,change)=>{const r=policyObservation();change(r);expect(parse(r)).toBeNull();});
it('requires null metadata when the original policy is missing, including no hidden latest time object',()=>{
 const r=policyObservation(),p=r.policy_comparison;
 Object.assign(p,{status:'unavailable',reason:'source_unavailable',gate:null,owner_reason:null,owner_scheduling:null,evaluated_at:null,valid_until:null,source_sha256:null,rule_sha256:null});
 p.comparisons[0]={intent_id:r.proposals[0].intent_id,status:'unknown',shadow_status:null};
 expect(parse(r)).not.toBeNull();p.valid_until={private_path:'/private'};expect(parse(r)).toBeNull();
});
