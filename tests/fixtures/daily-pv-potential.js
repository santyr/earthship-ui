export const now=Date.parse('2026-10-19T22:46:00Z');
export function fixture(){return {schema:'earthship-daily-pv-potential/v1',provider:'weathernext3',generatedAt:new Date(now).toISOString(),validUntil:new Date(now+90*60000).toISOString(),timezone:'America/Denver',weatherSha256:'a'.repeat(64),geometrySha256:'b'.repeat(64),systemSha256:'c'.repeat(64),horizonSha256:'d'.repeat(64),confidence:'provisional_uncalibrated',automatic_actuation:false,physical_calibration_qualified:false,days:[{date:'2026-10-19',status:'available',reason:null,potentialKwh:1.25,fromAt:new Date(now).toISOString(),throughAt:'2026-10-20T06:00:00+00:00',scope:'remaining'}]};}
export function calibratedFixture(){
 const v=fixture();v.schema='earthship-daily-pv-potential/v2';v.confidence='provisional_empirical_short_horizon';
 v.calibration={modelSha256:'e'.repeat(64),trainingThrough:'2026-10-19T00:00:00Z',assessedThrough:'2026-10-19T00:00:00Z',applyThroughAt:new Date(now+24*3600000).toISOString(),independentTargetDays:5,baselineMaeW:561,candidateMaeW:439,qualification:'retrospective_development_assessment_not_prospective_or_metrology'};
 Object.assign(v.days[0],{uncalibratedPotentialKwh:1.5,calibrationScope:'empirical_short_horizon'});return v;
}
