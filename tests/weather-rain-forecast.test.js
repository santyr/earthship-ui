import {it,expect} from 'vitest';
import original from './fixtures/weather-rain-shadow.json';
import emission from './fixtures/weather-rain-emission.json';
import {parseRainShadow,validateRainEmission,MAX_RAIN_BYTES} from '../src/lib/weather/rainForecast.js';
const now=Date.parse(original.generated_at)+1000,parse=value=>parseRainShadow(JSON.stringify(value),{nowMs:now});
it('reads original interval means as an unselected unqualified shadow',()=>{
 const p=parse(original);expect(p.state).toBe('ready');expect(p.rows).toHaveLength(1);expect(p.localCoverageQualified).toBe(false);expect(p.rows[0].local.probability_wet).toBeNull();
});
it('preserves measured zeros and incomplete heads without inventing probabilities',()=>{
 const v=structuredClone(original);for(const head of Object.keys(v.rows[0].raw_means_mm))v.rows[0].raw_means_mm[head]=0;
 expect(parse(v).rows[0].raw_means_mm.total_precipitation_1hr).toBe(0);v.rows[0].raw_means_mm.imerg_tp_1hr=null;expect(parse(v).state).toBe('ready');
});
it('allows a supported experimental zero probability with an explicit local label',()=>{
 const v=structuredClone(original),l=v.rows[0].local;Object.assign(l,{status:'experimental_prediction',reason:null,model_sha256:'e'.repeat(64),probability_wet:0,conditional_wet_mean_mm:2,subthreshold_mean_mm:.1,mean_depth_mm:.1,climatology_probability:.5});
 const p=parse(v);expect(p.state).toBe('ready');expect(p.rows[0].local.probability_wet).toBe(0);expect(p.label).toMatch(/local.*experimental/i);
});
it.each(['schema','private','stale','future','life','duplicate','source','hours','kind','nan','negative','unknown-probability','qualified','target','unseen-value','model','total'])('withholds %s malformed rain report',damage=>{
 const v=structuredClone(original),r=v.rows[0],l=r.local;
 if(damage==='schema')v.schema='earthship-rain-shadow-view/v9';if(damage==='private')v.source_originals={secret:'private'};
 if(damage==='stale')v.valid_until=v.generated_at;if(damage==='future')v.generated_at=new Date(now+6000).toISOString();if(damage==='life')v.valid_until=new Date(now+7*3600000).toISOString();
 if(damage==='duplicate')v.rows.push(r);if(damage==='source')r.source_available_at=new Date(now+60000).toISOString();if(damage==='hours')r.hours+=1;if(damage==='kind')r.interval_kind='unknown';
 if(damage==='nan')r.raw_means_mm.total_precipitation_1hr='0';if(damage==='negative')r.raw_means_mm.total_precipitation_1hr=-1;
 if(damage==='unknown-probability')l.probability_wet=.4;if(damage==='qualified')l.probability_calibration_qualified=true;if(damage==='target')l.target.end=r.start;
 if(damage==='unseen-value')l.mean_depth_mm=2;if(damage==='model')l.model_sha256='bad';
 if(damage==='total')Object.assign(l,{status:'experimental_prediction',reason:null,model_sha256:'e'.repeat(64),probability_wet:.5,conditional_wet_mean_mm:2,subthreshold_mean_mm:.1,mean_depth_mm:9,climatology_probability:.5});
 expect(parse(v).state).toBe('unavailable');
});
it('bounds bytes, duplicate object keys and legacy view lifetimes',()=>{
 expect(parseRainShadow('x'.repeat(MAX_RAIN_BYTES+1),{nowMs:now}).state).toBe('unavailable');
 expect(parseRainShadow(JSON.stringify(original).replace('{','{"rows":[], '),{nowMs:now}).state).toBe('unavailable');
 const legacy=structuredClone(original);legacy.schema='earthship-rain-shadow-view/v1';expect(parse(legacy).state).toBe('unavailable');legacy.valid_until=new Date(Date.parse(legacy.generated_at)+2*3600000).toISOString();expect(parse(legacy).state).toBe('ready');
});
it('requires the original receipt and exact actual cache byte hash',()=>{
 const view=parse(original),options={view,cacheBytesSha256:emission.cache_bytes_sha256,nowMs:now};
 expect(validateRainEmission(JSON.stringify(emission),options)).toBe(true);
 for(const change of [{cache_bytes_sha256:'f'.repeat(64)},{schema:'other'},{automatic_actuation:true},{private:'secret'},{contract_sha256:'f'.repeat(64)},{cache_write_completed_at:new Date(now+1).toISOString()}])expect(validateRainEmission(JSON.stringify({...emission,...change}),options)).toBe(false);
});
