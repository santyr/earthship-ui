// Closed current-product contract. Accounting and AC qualification stay in analyticsResult.
const fields={
 weather:'status issuedAt validUntil provider productSha256 providerSnapshotSha256 coreIssueSha256 productionIssueSha256 productionStatus sourceProfiles localCoverageQualified probabilityClaim reason',
 dailyPv:'status issuedAt validUntil provider productSha256 weatherSha256 today tomorrow confidence calibrationMode physicalCalibrationQualified automaticActuation reason',
 householdEnergy:'status issuedAt generatedAt validUntil productSha256 receiptSha256 cohortId potentialRemainingTodayKwh potentialNext24hKwh capturedNext24hKwh storageStatus confidence physicalCalibrationQualified automaticActuation reason',
};
const families=Object.keys(fields),states=['current','stale','degraded','unavailable'];
const profileFields='status issueSha256 initializedAt firstSeenAt ingestionCompletedAt snapshotSha256';
const check=v=>{if(!v)throw new Error('current_forecast_invalid');};
const exact=(v,list)=>{const keys=list.split(' ');check(v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k)));};
const stamp=v=>{check(typeof v==='string'&&/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(v));const n=Date.parse(v);check(Number.isFinite(n));return n;};
const hash=v=>check(typeof v==='string'&&/^[a-f0-9]{64}$/.test(v));
const reason=v=>check(v===null||typeof v==='string'&&/^[A-Za-z][A-Za-z0-9_]{0,95}$/.test(v));
const number=(v,high=100000)=>check(typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=high);
const dateAt=ms=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Denver',year:'numeric',month:'2-digit',day:'2-digit'}).format(ms);
const midnight=ms=>new Intl.DateTimeFormat('en-GB',{timeZone:'America/Denver',hourCycle:'h23',hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(ms)==='00:00:00'&&ms%1000===0;
export function emptyAnalyticsForecastSection(family){
 const s=Object.fromEntries(fields[family].split(' ').map(k=>[k,null]));Object.assign(s,{status:'unavailable',reason:'no_current_product_snapshot'});
 if(family==='weather')Object.assign(s,{sourceProfiles:Object.fromEntries(['extended','nearTerm'].map(p=>[p,Object.fromEntries(profileFields.split(' ').map(k=>[k,null]))])),localCoverageQualified:false,probabilityClaim:false});
 else Object.assign(s,{physicalCalibrationQualified:false,automaticActuation:false});
 return s;
}
function validateSection(family,s,generated){
 exact(s,fields[family]);check(states.includes(s.status));reason(s.reason);
 if(s.issuedAt===null){
  check(s.status==='unavailable'&&s.reason==='no_current_product_snapshot');
  if(family==='weather'){
   check(s.localCoverageQualified===false&&s.probabilityClaim===false);exact(s.sourceProfiles,'extended nearTerm');
   for(const p of Object.values(s.sourceProfiles)){exact(p,profileFields);check(Object.values(p).every(v=>v===null));}
  }else check(s.physicalCalibrationQualified===false&&s.automaticActuation===false);
  const special=['status','reason','sourceProfiles','localCoverageQualified','probabilityClaim','physicalCalibrationQualified','automaticActuation'];
  check(Object.entries(s).every(([k,v])=>special.includes(k)||v===null));return;
 }
 const issue=stamp(s.issuedAt),until=stamp(s.validUntil),current=s.status==='current';hash(s.productSha256);check(issue<=generated&&until>issue&&(!current||generated<until));
 if(family==='weather'){
  check(s.provider==='weathernext3'&&s.localCoverageQualified===false&&s.probabilityClaim===false);hash(s.providerSnapshotSha256);hash(s.productionIssueSha256);if(s.coreIssueSha256!==null)hash(s.coreIssueSha256);check(!current||s.coreIssueSha256!==null);
  check(['ACTIVE','MIXED_WITH_RAW_FALLBACK','RAW_FALLBACK'].includes(s.productionStatus)&&until<=issue+4*3600000&&(!current||s.reason===null));exact(s.sourceProfiles,'extended nearTerm');check(!current||s.sourceProfiles.extended.status==='AVAILABLE'&&s.coreIssueSha256===s.sourceProfiles.extended.issueSha256);
  for(const p of Object.values(s.sourceProfiles)){exact(p,profileFields);check(['AVAILABLE','UNAVAILABLE'].includes(p.status));
   if(p.status==='AVAILABLE'){hash(p.issueSha256);hash(p.snapshotSha256);const initialized=stamp(p.initializedAt),seen=stamp(p.firstSeenAt),ingested=stamp(p.ingestionCompletedAt);check(initialized<=seen&&seen<=ingested&&ingested<=issue&&until<=initialized+24*3600000);}
   else check(Object.entries(p).every(([k,v])=>k==='status'||v===null));
  }
 }else{
  check(s.physicalCalibrationQualified===false&&s.automaticActuation===false);
  if(family==='dailyPv'){
   check(s.provider==='weathernext3'&&s.confidence==='experimental_native_component_model'&&['experimental_production','raw_component_fallback'].includes(s.calibrationMode)&&until<=issue+90*60000);hash(s.weatherSha256);
   const today=dateAt(generated),tomorrow=new Date(Date.parse(`${today}T12:00:00Z`)+86400000).toISOString().slice(0,10);
   for(const [key,day,scope] of [['today',today,'remaining'],['tomorrow',tomorrow,'full_day']]){
    const d=s[key];if(d===null)continue;exact(d,'date fromAt throughAt scope potentialKwh status reason');check(d.date===day&&d.scope===scope&&['available','unavailable'].includes(d.status));reason(d.reason);
    const start=stamp(d.fromAt),end=stamp(d.throughAt);check(issue<=start&&start<end&&end-start<=25*3600000&&dateAt(start)===day&&dateAt(end-1)===day&&midnight(end)&&(scope!=='full_day'||midnight(start)));
    if(current&&d.status==='available')number(d.potentialKwh,1000);else check(d.potentialKwh===null);
   }
  }else{
   hash(s.receiptSha256);if(s.cohortId!==null)hash(s.cohortId);const completed=stamp(s.generatedAt);
   check(issue<=completed&&completed<=generated&&until===issue+15*60000&&s.confidence==='provisional_uncalibrated'&&['conditional','unavailable'].includes(s.storageStatus));
   if(current){check(s.reason===null);number(s.potentialNext24hKwh);number(s.potentialRemainingTodayKwh,s.potentialNext24hKwh+1e-7);if(s.storageStatus==='conditional')number(s.capturedNext24hKwh,s.potentialNext24hKwh+1e-7);else check(s.capturedNext24hKwh===null);}
   else check(['potentialRemainingTodayKwh','potentialNext24hKwh','capturedNext24hKwh'].every(k=>s[k]===null));
  }
 }
}
function aggregate(v){const s=families.map(k=>v[k].status);return s.every(v=>v==='current')?'current':s.every(v=>v==='unavailable')?'unavailable':s.every(v=>['stale','unavailable'].includes(v))&&s.includes('stale')?'stale':'degraded';}
export function validateAnalyticsForecast(v,generated){exact(v,'status weather dailyPv householdEnergy reason');check(states.includes(v.status));reason(v.reason);families.forEach(k=>validateSection(k,v[k],generated));check(v.status===aggregate(v));}
export function currentAnalyticsForecast(forecast,{nowMs,parentStale=false}={}){
 const v=structuredClone(forecast);
 for(const family of families){
  const s=v[family];if(s.issuedAt!==null&&(parentStale||nowMs<stamp(s.issuedAt)||nowMs>=stamp(s.validUntil))){s.status='stale';s.reason=parentStale?'analytics_payload_stale':'product_validity_expired';}
  if(family==='dailyPv'){
   const today=dateAt(nowMs),tomorrow=new Date(Date.parse(`${today}T12:00:00Z`)+86400000).toISOString().slice(0,10);
   // Retained rows keep their original scope; a full day never becomes remaining today.
   for(const [name,day,scope] of [['today',today,'remaining'],['tomorrow',tomorrow,'full_day']]){
    if(s[name]!==null&&(s[name].date!==day||s[name].scope!==scope))s[name]=null;
   }
  }
  if(s.status!=='current'){
   if(family==='dailyPv')for(const name of ['today','tomorrow']){if(s[name]!==null)s[name].potentialKwh=null;}
   if(family==='householdEnergy')for(const name of ['potentialRemainingTodayKwh','potentialNext24hKwh','capturedNext24hKwh'])s[name]=null;
  }
 }
 v.status=aggregate(v);v.reason=v.status==='current'?null:'current_forecast_set_incomplete';return v;
}
export function currentLegacyForecast(forecast,{nowMs,parentStale=false}={}){
 const v=structuredClone(forecast),issued=typeof v.issuedAt==='string'?Date.parse(v.issuedAt):NaN,until=typeof v.validFor==='string'?Date.parse(v.validFor):NaN;
 if(v.status!=='current'||parentStale||!Number.isFinite(issued)||!Number.isFinite(until)||issued>nowMs||nowMs>=until||nowMs-issued>6*3600000){
  for(const key of ['pv24hKwh','nextMorningSocPct','fullToday','fullTomorrow'])v[key]=null;
  if(v.status==='current'){v.status='stale';v.reason=parentStale?'analytics_payload_stale':'forecast_clock_not_current';}
 }
 return v;
}
