import { energyAnalyticsV4Fixture, GENERATED_AT_MS } from './energyAnalytics.js';
export function analyticsV5Fixture() {
 const v=energyAnalyticsV4Fixture();v.schema='earthship-energy-ui/v5';
 const hash='a'.repeat(64),issued='2026-08-20T18:00:00Z';
 const profile={status:'AVAILABLE',issueSha256:hash,initializedAt:'2026-08-20T12:00:00Z',firstSeenAt:'2026-08-20T17:41:00Z',ingestionCompletedAt:'2026-08-20T17:42:00Z',snapshotSha256:hash};
 v.forecast={status:'current',reason:null,
  weather:{status:'current',issuedAt:issued,validUntil:'2026-08-20T22:00:00Z',provider:'weathernext3',productSha256:hash,providerSnapshotSha256:hash,coreIssueSha256:hash,productionIssueSha256:'b'.repeat(64),productionStatus:'MIXED_WITH_RAW_FALLBACK',sourceProfiles:{extended:{...profile},nearTerm:{...profile}},localCoverageQualified:false,probabilityClaim:false,reason:null},
  dailyPv:{status:'current',issuedAt:issued,validUntil:'2026-08-20T19:30:00Z',provider:'weathernext3',productSha256:hash,weatherSha256:hash,today:{date:'2026-08-20',fromAt:issued,throughAt:'2026-08-21T06:00:00Z',scope:'remaining',potentialKwh:4,status:'available',reason:null},tomorrow:{date:'2026-08-21',fromAt:'2026-08-21T06:00:00Z',throughAt:'2026-08-22T06:00:00Z',scope:'full_day',potentialKwh:12,status:'available',reason:null},confidence:'experimental_native_component_model',calibrationMode:'experimental_production',physicalCalibrationQualified:false,automaticActuation:false,reason:null},
  householdEnergy:{status:'current',issuedAt:issued,generatedAt:'2026-08-20T18:00:00Z',validUntil:'2026-08-20T18:15:00Z',productSha256:hash,receiptSha256:hash,cohortId:null,potentialRemainingTodayKwh:3,potentialNext24hKwh:15,capturedNext24hKwh:8,storageStatus:'conditional',confidence:'provisional_uncalibrated',physicalCalibrationQualified:false,automaticActuation:false,reason:null}};
 return v;
}
export { GENERATED_AT_MS };

/** Parent/product clocks straddle Denver midnight; day lengths may be23/25h. */
export function analyticsV5MidnightFixture(issueAt, midnightAt, nextMidnightAt) {
 const v=analyticsV5Fixture(),issue=Date.parse(issueAt),parent=issue+9*60000;
 const iso=ms=>new Date(ms).toISOString();
 const day=ms=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Denver',year:'numeric',month:'2-digit',day:'2-digit'}).format(ms);
 v.generatedAt=iso(parent);v.throughDate='2026-01-02';v.energy.latest.date='2026-01-02';
 Object.assign(v.accounting,{cutover:'2026-01-01T07:00:00Z',windowStart:'2026-01-01',windowEndExclusive:'2026-01-03',latestRevision:{id:12,sha256:'a'.repeat(64),computedAt:'2026-01-03T08:00:00Z'}});
 Object.assign(v.acLoad,{cutover:'2026-01-01T07:00:00Z',topologyFrom:'2026-01-01T07:00:00Z'});
 Object.assign(v.acLoad.latest,{date:'2026-01-02',windowStart:'2026-01-02T07:00:00Z',windowEnd:'2026-01-03T07:00:00Z',revision:{id:7,sha256:'b'.repeat(64),computedAt:'2026-01-03T08:00:00Z'}});
 Object.assign(v.forecast.weather,{issuedAt:issueAt,validUntil:iso(issue+4*3600000)});
 for(const p of Object.values(v.forecast.weather.sourceProfiles))Object.assign(p,{initializedAt:iso(issue-12*3600000),firstSeenAt:iso(issue-5*60000),ingestionCompletedAt:iso(issue-4*60000)});
 Object.assign(v.forecast.dailyPv,{issuedAt:issueAt,validUntil:iso(issue+90*60000)});
 Object.assign(v.forecast.dailyPv.today,{date:day(issue),fromAt:issueAt,throughAt:midnightAt});
 Object.assign(v.forecast.dailyPv.tomorrow,{date:day(Date.parse(midnightAt)),fromAt:midnightAt,throughAt:nextMidnightAt});
 Object.assign(v.forecast.householdEnergy,{issuedAt:iso(parent-60000),generatedAt:iso(parent),validUntil:iso(parent+14*60000)});
 return v;
}
