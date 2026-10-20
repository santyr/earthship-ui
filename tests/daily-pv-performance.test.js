import { expect, it } from 'vitest';
import { pvPerformance, PV_REPORT_NOW } from './fixtures/daily-pv-performance.js';
import { parsePvPerformance } from '../src/lib/energy/pvPerformance.js';
it('preserves separate PV model/policy cohorts, measured coverage and zero-evidence nulls',()=>{
  for(const collecting of [true,false]){
    const v=pvPerformance({collecting});const parsed=parsePvPerformance(JSON.stringify(v),{nowMs:PV_REPORT_NOW});
    expect(parsed.cohorts).toEqual(v.cohorts);expect(parsed.expired).toBe(false);
  }
  expect(parsePvPerformance(pvPerformance(),{nowMs:PV_REPORT_NOW+3*3600000}).expired).toBe(true);
});
it.each(['private','authority','zeroEvidence','counts','duration','postOrigin','future','window','cohortDuplicate'])('refuses invalid or expanded PV report: %s',damage=>{
  const v=pvPerformance();
  if(damage==='private')v.original_path='/operator-private';
  if(damage==='authority')v.automatic_actuation=true;
  if(damage==='zeroEvidence'){v.cohorts[0].eligible_bins=0;v.cohorts[0].censored_bins=24;v.cohorts[0].adjusted_bins=0;v.cohorts[0].covered_seconds=0;}
  if(damage==='counts')v.cohorts[0].censored_bins=25;
  if(damage==='duration')v.cohorts[0].covered_seconds=4000;
  if(damage==='postOrigin')v.cohorts[0].last_issue='2026-10-20T14:00:00Z';
  if(damage==='future')v.generated_at='2026-10-20T14:00:00Z';
  if(damage==='window')v.scored_hours=500;
  if(damage==='cohortDuplicate')v.cohorts.push({...v.cohorts[0]});
  expect(parsePvPerformance(v,{nowMs:PV_REPORT_NOW})).toBeNull();
});
