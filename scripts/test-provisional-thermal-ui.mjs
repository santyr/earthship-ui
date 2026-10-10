import assert from 'node:assert/strict';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';
const issue = '2026-10-10T18:00:00+00:00';
const payload = { schema:'earthship-provisional-thermal-publication/v1',version:8,status:'provisional',generatedAt:issue,validUntil:'2026-10-10T18:15:00+00:00',
 model:{artifactSha256:'a'.repeat(64),runtimeSha256:'b'.repeat(64),createdAt:'2026-10-10T17:00:00+00:00',trainedThrough:'2026-10-10T16:40:00+00:00',fitExecuted:true,independentOriginDates:2,horizonSupport:{'1':2,'6':2,'12':1,'24':1},regularizationStrength:1},
 forecast:{schema:'earthship-provisional-thermal-forecast/v1',status:'provisional',generated_at:issue,artifact_sha256:'a'.repeat(64),runtime_sha256:'b'.repeat(64),horizon_hours:1,initial:{air_f:74,mass_f:72,outdoor_f:60},origin_actions:{indoor_shade_closed:0,outdoor_shade_present:1,vent_open:0,vent_provenance:'manual_dm',mode:'warm',action_knowledge:'as_of_snapshot_not_outcome_confirmation'},trajectory:[{at:'2026-10-10T19:00:00+00:00',air_f:75,mass_f:72.5}],confidence:'low',prediction_intervals:null,advice:[],graduated:false,automatic_actuation:false},
 confidence:{grade:'low',actionLabels:'withheld'},graduation:{forecastQualified:false,stabilityAssessed:false,calibrationAssessed:false},automaticActuation:false,reasons:['Provisional; errors are monitored.'] };
const now=Date.parse(issue)+1000;
const result=parseThermalModelResult(JSON.stringify(payload),now);
assert.equal(result.state,'ready');assert.equal(result.mode,'provisional');assert.equal(result.badge,'PROVISIONAL');assert.equal(result.confidence,'low');assert.equal(result.uncertaintyMode,'uncalibrated');
let checked=1;
for (const damage of [p=>{p.automaticActuation=true},p=>{p.graduation.forecastQualified=true},p=>{p.confidence.grade='high'},p=>{p.forecast.prediction_intervals=[]},p=>{p.forecast.advice=['open vent']},p=>{p.forecast.trajectory[0].air_f=200},p=>{p.model.createdAt='2026-10-10T20:00:00+00:00'},p=>{p.forecast.runtime_sha256='c'.repeat(64)},p=>{p.forecast.trajectory[0].at='2026-10-10T20:00:00+00:00'}]) {
 const changed=structuredClone(payload);damage(changed);assert.equal(parseThermalModelResult(JSON.stringify(changed),now).state,'unavailable');checked++;
}
assert.equal(parseThermalModelResult(JSON.stringify(payload),Date.parse(payload.validUntil)).state,'unavailable');checked++;
console.log(`${checked} provisional UI contract checks passed`);
