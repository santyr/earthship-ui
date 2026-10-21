/** Closed diagnostic projection; source hashes resolve retained producer originals.
 * This validates quantities and references, not original acquisition or signatures.
 */
const HOUR=3600000, MPH=2.2369362920544, HASH=/^[a-f0-9]{64}$/;
const fields={temperature:['station',-100,70],dewpoint:['station',-100,70],pressure:['gridded',400,1200],speed:['gridded',0,200],u:['gridded',-200,200],v:['gridded',-200,200],total:['gridded',0,100],high:['gridded',0,100],medium:['gridded',0,100],low:['gridded',0,100]};
const missing=new Set(['qualified_indoor_temperature_and_relative_humidity','compatible_same_zone_indoor_temperature_and_humidity','forecast_dewpoint','outdoor_target_within_two_hours','indoor_temperature_outside_diagnostic_domain']);
const exact=(v,keys)=>v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).sort().join('|')===[...keys].sort().join('|');
const finite=v=>typeof v==='number'&&Number.isFinite(v);
const digest=v=>typeof v==='string'&&HASH.test(v);
const same=(a,b)=>a===null&&b===null||finite(a)&&finite(b)&&Math.abs(a-b)<=1e-9*Math.max(1,Math.abs(a),Math.abs(b));
const clock=v=>typeof v==='string'&&v.length<=64&&/^\d{4}-\d\d-\d\dT/.test(v)&&/(?:Z|[+-]\d\d:\d\d)$/.test(v)?Date.parse(v):NaN;
function requireValue(ok){if(!ok)throw new TypeError('Unavailable atmospheric diagnostic');}
const fahrenheit=v=>v===null?null:v*1.8+32;
const vapor=t=>6.11*10**(7.5*t/(237.3+t));
function runInit(run){
 if(typeof run!=='string'||run.length>128)return NaN;
 const m=/^(\d{4})(\d{2})(\d{2})_(\d{2})hr_\d{2}_preds$/.exec(run);
 return run.startsWith('ee:')?clock(run.slice(3)):m?Date.parse(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:00:00Z`):NaN;
}
function compatible(a,b,sources){
 if(!a||!b)return false;
 const x=sources.get(a.source_ref),y=sources.get(b.source_ref);
 return a.native_asset_sha256===b.native_asset_sha256&&['run_id','initialized_at','grid_sha256'].every(k=>x[k]===y[k]);
}
function moistureContext(m,first,generated,nowMs){
 requireValue(exact(m,'schema assessed_at outdoor_target_at mode outdoor_vapor_pressure_hpa indoor_vapor_pressure_hpa indoor_temperature_c indoor_relative_humidity_pct comparison valid_until indoor_evidence_sha256s indoor_context_sha256 missing_dependencies scope condensation_assessed automatic_actuation release_authorized context_sha256'.split(' '))
  &&m.schema==='earthship-forecast-moisture-context/v1'&&m.scope==='forecast_outdoor_vapor_pressure_vs_current_indoor_at_comparable_local_total_pressure'
  &&m.condensation_assessed===false&&m.automatic_actuation===false&&m.release_authorized===false&&digest(m.context_sha256)
  &&clock(m.assessed_at)===generated&&m.outdoor_target_at===first.valid_at&&Array.isArray(m.missing_dependencies)&&m.missing_dependencies.every(x=>missing.has(x)));
 const expected=first.fields.dewpoint===null?null:vapor(first.fields.dewpoint.value);
 requireValue(same(m.outdoor_vapor_pressure_hpa,expected));
 const result={mode:'outdoor_only',targetAt:m.outdoor_target_at,outdoorVaporPressureHpa:expected,indoorTemperatureF:null,indoorRelativeHumidityPct:null,indoorVaporPressureHpa:null,comparison:null,validUntil:null,missingDependencies:[...m.missing_dependencies]};
 if(m.mode==='outdoor_only'){
  requireValue(m.missing_dependencies.length>0&&['indoor_vapor_pressure_hpa','indoor_temperature_c','indoor_relative_humidity_pct','comparison','valid_until','indoor_context_sha256'].every(k=>m[k]===null)
   &&Array.isArray(m.indoor_evidence_sha256s)&&m.indoor_evidence_sha256s.length===0);
 }else{
  const target=clock(m.outdoor_target_at),until=clock(m.valid_until);
  requireValue(m.mode==='qualified_comparison'&&!m.missing_dependencies.length&&finite(m.indoor_temperature_c)&&m.indoor_temperature_c>=-100&&m.indoor_temperature_c<=70
   &&finite(m.indoor_relative_humidity_pct)&&m.indoor_relative_humidity_pct>=0&&m.indoor_relative_humidity_pct<=100&&expected!==null
   &&target>generated&&target<=generated+2*HOUR&&until>generated&&until<=generated+120000
   &&Array.isArray(m.indoor_evidence_sha256s)&&m.indoor_evidence_sha256s.length===2&&m.indoor_evidence_sha256s.every(digest)&&digest(m.indoor_context_sha256));
  const indoor=vapor(m.indoor_temperature_c)*m.indoor_relative_humidity_pct/100,difference=expected-indoor;
  const comparison=difference<-.5?'forecast_air_drier':difference>.5?'forecast_air_wetter':'similar_vapor_pressure';
  requireValue(same(m.indoor_vapor_pressure_hpa,indoor)&&m.comparison===comparison);
  if(nowMs>=until)result.missingDependencies=['indoor_evidence_expired'];
  else Object.assign(result,{mode:'qualified_comparison',indoorTemperatureF:fahrenheit(m.indoor_temperature_c),indoorRelativeHumidityPct:m.indoor_relative_humidity_pct,indoorVaporPressureHpa:indoor,comparison,validUntil:m.valid_until});
 }
 return result;
}
/** Throws for malformed structure even when this group's own data have expired.
 * The fixed GET transport serves the original JSON, so partial validation could
 * otherwise expose an unknown/private key beside a valid temperature group.
 */
export function parseAtmosphericGroup(group,{generatedMs,validUntilMs,nowMs}){
 requireValue(exact(group,'schema method valid_until sources hours moisture rh_scope pressure_basis wind_scope cloud_scope temperature_model_uses_fields selection_truncated withheld_sources'.split(' '))
  &&group.schema==='earthship-atmospheric-display/v1'&&group.method==='raw-native-atmosphere/v1'
  &&group.rh_scope==='diagnostic_from_mean_T_and_mean_Td_not_ensemble_mean_RH'&&group.pressure_basis==='mean_sea_level'
  &&group.wind_scope==='scalar_mean_speed_and_mean_vector_are_distinct; neither_is_gust'&&group.cloud_scope==='independent_layer_cover; layers_overlap_and_are_not_summed'
  &&group.temperature_model_uses_fields===false&&typeof group.selection_truncated==='boolean'&&Number.isInteger(group.withheld_sources)&&group.withheld_sources>=0&&group.withheld_sources<=32
  &&Array.isArray(group.sources)&&group.sources.length<=16&&Array.isArray(group.hours)&&group.hours.length<=24);
 const until=clock(group.valid_until);requireValue(until>generatedMs&&until<=validUntilMs);
 const sources=new Map();
 for(const s of group.sources){
  requireValue(exact(s,'ref_sha256 snapshot_sha256 source_digest grid_sha256 native_grid run_id initialized_at first_seen_at available_at'.split(' '))
   &&['ref_sha256','snapshot_sha256','source_digest','grid_sha256'].every(k=>digest(s[k]))&&!sources.has(s.ref_sha256)&&['station','gridded'].includes(s.native_grid));
  const init=clock(s.initialized_at),seen=clock(s.first_seen_at),available=clock(s.available_at);
  requireValue([init,seen,available].every(Number.isFinite)&&init<=seen&&seen<=available&&available<=generatedMs&&generatedMs<init+24*HOUR&&until<=init+24*HOUR&&runInit(s.run_id)===init);
  sources.set(s.ref_sha256,s);
 }
 const used=new Set(),hours=[];let prior=-Infinity;
 for(const row of group.hours){
  requireValue(exact(row,'valid_at fields relative_humidity_pct relative_humidity_reason wind_from_degrees vector_magnitude_m_s direction_reason'.split(' '))&&exact(row.fields,Object.keys(fields)));
  const at=clock(row.valid_at);requireValue(at>generatedMs&&at<=generatedMs+24*HOUR&&at>prior);prior=at;
  let any=false;const fieldSources={};
  for(const [name,[grid,low,high]] of Object.entries(fields)){
   const field=row.fields[name];fieldSources[name]=null;if(field===null)continue;
   requireValue(exact(field,['value','source_ref','native_asset_sha256'])&&sources.has(field.source_ref)&&digest(field.native_asset_sha256)&&finite(field.value)&&field.value>=low&&field.value<=high);
   const source=sources.get(field.source_ref);requireValue(source.native_grid===grid&&at<=clock(source.initialized_at)+360*HOUR);
   used.add(field.source_ref);any=true;fieldSources[name]={...source,native_asset_sha256:field.native_asset_sha256};
  }
  requireValue(any);
  const f=row.fields;let rh=null,rhReason='compatible_station_pair_unavailable';
  if(compatible(f.temperature,f.dewpoint,sources)){
   if(f.dewpoint.value>f.temperature.value)rhReason='dewpoint_above_temperature';
   else {rh=100*vapor(f.dewpoint.value)/vapor(f.temperature.value);rhReason=null;}
  }
  let direction=null,magnitude=null,directionReason='mean_components_unavailable';
  if(compatible(f.u,f.v,sources)){
   magnitude=Math.hypot(f.u.value,f.v.value);directionReason=magnitude<=1e-6?'calm_or_cancelling_mean_vector':null;
   if(directionReason===null)direction=(Math.atan2(-f.u.value,-f.v.value)*180/Math.PI+360)%360;
  }
  requireValue(same(row.relative_humidity_pct,rh)&&row.relative_humidity_reason===rhReason&&same(row.wind_from_degrees,direction)&&same(row.vector_magnitude_m_s,magnitude)&&row.direction_reason===directionReason);
  hours.push({at:row.valid_at,atMs:at,dewpointF:fahrenheit(f.dewpoint?.value??null),pressureHpa:f.pressure?.value??null,relativeHumidityPct:rh,relativeHumidityReason:rhReason,
   scalarSpeedMph:f.speed===null?null:f.speed.value*MPH,vectorMagnitudeMph:magnitude===null?null:magnitude*MPH,windFromDegrees:direction,directionReason,
   clouds:Object.fromEntries(['total','high','medium','low'].map(k=>[k,f[k]?.value??null])),fieldSources});
 }
 requireValue(used.size===sources.size);
 let moisture=null;
 if(group.hours.length)moisture=moistureContext(group.moisture,group.hours[0],generatedMs,nowMs);
 else requireValue(group.moisture===null);
 if(nowMs>=until||!hours.length)return {state:'unavailable',hours:[],sources:[],moisture:null};
 return {state:'ready',hours,sources:[...sources.values()],moisture,validUntil:group.valid_until,selectionTruncated:group.selection_truncated,withheldSources:group.withheld_sources,temperatureModelUsesFields:false};
}
export function atmosphericCapabilityAt(product,at){
 return product?.atmosphere?.state==='ready'?product.atmosphere.hours.find(h=>h.atMs===clock(at))??null:null;
}
