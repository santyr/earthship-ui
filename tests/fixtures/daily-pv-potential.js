export const now=Date.parse('2026-10-19T22:46:00Z');
export function fixture(){return {schema:'earthship-daily-pv-potential/v1',provider:'weathernext3',generatedAt:new Date(now).toISOString(),validUntil:new Date(now+90*60000).toISOString(),timezone:'America/Denver',weatherSha256:'a'.repeat(64),geometrySha256:'b'.repeat(64),systemSha256:'c'.repeat(64),horizonSha256:'d'.repeat(64),confidence:'provisional_uncalibrated',automatic_actuation:false,physical_calibration_qualified:false,days:[{date:'2026-10-19',status:'available',reason:null,potentialKwh:1.25,fromAt:new Date(now).toISOString(),throughAt:'2026-10-20T06:00:00+00:00',scope:'remaining'}]};}
export function calibratedFixture(){
 const v=fixture();v.schema='earthship-daily-pv-potential/v2';v.confidence='provisional_empirical_short_horizon';
 v.calibration={modelSha256:'e'.repeat(64),trainingThrough:'2026-10-19T00:00:00Z',assessedThrough:'2026-10-19T00:00:00Z',applyThroughAt:new Date(now+24*3600000).toISOString(),independentTargetDays:5,baselineMaeW:561,candidateMaeW:439,qualification:'retrospective_development_assessment_not_prospective_or_metrology'};
 Object.assign(v.days[0],{uncalibratedPotentialKwh:1.5,calibrationScope:'empirical_short_horizon'});return v;
}

export function componentFixture(){
 const v=fixture();v.schema='earthship-daily-pv-potential/v4';v.confidence='experimental_native_component_model';
 const trained=now-86400000;
 v.calibration={modelSha256:'e'.repeat(64),calibrationSha256:'f'.repeat(64),procedureSha256:'1'.repeat(64),policySha256:'2'.repeat(64),
  trainedAt:new Date(trained).toISOString(),trainingThrough:new Date(trained-86400000).toISOString(),validUntil:new Date(trained+14*86400000).toISOString(),
  targets:737,localTargetDates:29,baselineRule:'native_fdir_ssrd_isotropic_faiman_proxy_pvwatts_dc_v2',mode:'experimental_production',physicalCalibrationQualified:false};
 Object.assign(v.days[0],{uncalibratedPotentialKwh:1.5,calibrationScope:'native_components_only',
  sourceSupport:{native_hours:9,fallback_hours:0,fallback_reasons:{}},projectionSha256:'3'.repeat(64)});
 return v;
}
