import {expect,it} from 'vitest';
import {parseHouseholdObservation} from '../src/lib/household/observation.js';
import {historicalRecommendationPreview,climatePreview} from '../src/lib/household/recommendations.js';
import {recommendationObservation} from './fixtures/household-recommendations.js';
import {AT,observation,proposal} from './fixtures/household-observation.js';
const parse=(v,nowMs=AT)=>parseHouseholdObservation(JSON.stringify(v),{nowMs});
it('exposes exact OFF direction, its original clock and blocks in its own domain',()=>{
 const v=parse(recommendationObservation());expect(v).not.toBeNull();
 const r=historicalRecommendationPreview(v,'loads',AT);expect(r.rows).toHaveLength(1);
 expect(r.rows[0].action).toBe('Night-load override: OFF');expect(r.rows[0].status).toBe('Blocked');
 expect(r.rows[0].reasons).toContain('Low forecast battery SoC');expect(r.rows[0].blockers).toContain('Action effects are unqualified');
 expect(r.rows[0].createdAt).toBe(v.decision_at);expect(r.rows[0].confidence).toBe('unavailable');expect(r.automaticActuation).toBe(false);
 expect(historicalRecommendationPreview(v,'greywater',AT).rows[0].action).toBe('Run greywater circulation cycle');
 expect(historicalRecommendationPreview(v,'feeding',AT).rows).toEqual([]);
});
it('shows expired history without presenting a current recommendation or renewing clocks',()=>{
 const r=historicalRecommendationPreview(parse(recommendationObservation(),AT+60000),'loads',AT+60000);
 expect(r.rows[0].status).toBe('Expired');expect(r.current).toBe(false);expect(r.rows[0].expiresAt).toBe('2026-10-12T03:02:30+00:00');
});
it('never infers an ON/OFF command from a legacy type, reason or missing record',()=>{
 const v=recommendationObservation();v.schema='earthship-household-observation/v3';for(const p of v.proposals)for(const k of ['parameters','created_at','expires_at'])delete p[k];
 const r=historicalRecommendationPreview(parse(v),'loads',AT);expect(r.rows[0].action).toBe('Night-load override · action details unavailable');
 expect(historicalRecommendationPreview(null,'loads',AT).state).toBe('unavailable');expect(historicalRecommendationPreview(parse(observation()),'feeding',AT).state).toBe('none');
});
it.each(['command','device','extra','future','expiry','authority'])('refuses invalid detail payload: %s',damage=>{
 const v=recommendationObservation(),p=v.proposals[1];
 if(damage==='command')p.parameters.command='TOGGLE';if(damage==='device')p.parameters.device='unregistered';
 if(damage==='extra')p.parameters.private_token='do-not-display';if(damage==='future')p.created_at='2026-10-12T04:00:00Z';
 if(damage==='expiry')p.expires_at='2026-10-13T03:00:00Z';if(damage==='authority')v.automatic_actuation=true;
 expect(parse(v)).toBeNull();
});
it('never turns baseline assumptions or a forecast-only thermal payload into advice',()=>{
 const raw={status:'provisional',origin_actions:{vent_open:0}};
 expect(climatePreview(JSON.stringify(raw),'ventilation',AT).rows).toEqual([]);
 expect(climatePreview(JSON.stringify(raw),'shades',AT).rows).toEqual([]);
});
it('displays an explicit published thermal candidate, with original timing and unqualified status',async()=>{
 const {default:base}=await import('./fixtures/thermal-shadow-v1-available.json');const raw=structuredClone(base);
 raw.schedule.candidate={ventOpenAt:'2026-08-14T03:00:00+00:00',ventCloseAt:'2026-08-14T10:30:00+00:00'};
 raw.schedule.effect={morningMassDeltaF:-1.5,hallwayPeakDeltaF:-0.75};
 const r=climatePreview(JSON.stringify(raw),'ventilation',Date.parse(raw.generatedAt));expect(r.rows).toHaveLength(1);
 expect(r.rows[0].status).toBe('Blocked');expect(r.rows[0].action).toContain('Candidate ventilation window');
 expect(r.rows[0].expiresAt).toBe(raw.schedule.candidate.ventCloseAt);
 raw.forecast.trajectory[1].actions=['indoor_shade_open'];
 expect(climatePreview(JSON.stringify(raw),'shades',Date.parse(raw.generatedAt)).rows).toEqual([]);
 raw.schedule.candidate=null;raw.schedule.effect=null;
 expect(climatePreview(JSON.stringify(raw),'shades',Date.parse(raw.generatedAt)).rows).toEqual([]);
});
it('keeps policy suggestions beside their own control rather than a different load',()=>{
 const v=parse(recommendationObservation());expect(historicalRecommendationPreview(v,'night-policy',AT).rows[0].action).toBe('Night-load override: OFF');
 expect(historicalRecommendationPreview(v,'devices',AT).rows).toEqual([]);
});

it('does not fabricate a ventilation window for an explicit closed-vent candidate',async()=>{
 const {default:base}=await import('./fixtures/thermal-shadow-v1-available.json');const raw=structuredClone(base);
 raw.schedule.candidate={ventOpenAt:null,ventCloseAt:null};
 raw.schedule.effect={morningMassDeltaF:-1.5,hallwayPeakDeltaF:-0.75};
 expect(climatePreview(JSON.stringify(raw),'ventilation',Date.parse(raw.generatedAt)).rows).toEqual([]);
});

it('excludes feeder intents even when an incoming original marks one selected',()=>{
 const row=observation();const feeder=proposal();Object.assign(feeder,{selected:true,decision_status:'accepted',decision_reason:null,hard_checks:[]});row.proposals=[feeder];
 const view=parse(row);expect(view).not.toBeNull();
 expect(historicalRecommendationPreview(view,'feeding',AT).rows).toEqual([]);
});
