/** Synthetic public projection; no household sources or account identifiers. */
export const CAPABILITY_NOW=Date.parse('2026-10-21T18:00:00Z');
export function capabilityFixture(now=CAPABILITY_NOW){return {
 schema:'earthship-weathernext-capabilities/v1',provider:'weathernext3',generated_at:new Date(now).toISOString(),valid_until:new Date(now+3600000).toISOString(),timezone:'America/Denver',status:'available',
 sources:[{snapshot_sha256:'a'.repeat(64),profile_sha256:'b'.repeat(64),run_id:'ee:'+new Date(now-6*3600000).toISOString(),initialized_at:new Date(now-6*3600000).toISOString(),first_seen_at:new Date(now-3600000).toISOString(),available_at:new Date(now-3540000).toISOString(),grid_sha256:'c'.repeat(64)}],
 groups:{temperature:{method:'raw-native-statistics/v1',label:'WeatherNext p10–p90; local coverage not yet verified',nominal_interval_probability:.8,local_coverage_qualified:false,hours:Array.from({length:12},(_,i)=>({valid_at:new Date(now+(i+1)*3600000).toISOString(),source_sha256:'a'.repeat(64),mean_c:20,p10_c:0,p25_c:null,p50_c:null,p75_c:null,p90_c:10,range_status:'available'}))}},
 automatic_actuation:false,release_authorized:false,report_sha256:'d'.repeat(64)
};}
