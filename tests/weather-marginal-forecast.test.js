import {it,expect} from 'vitest';
import original from './fixtures/weather-marginal-shadow.json';
import {parseWeatherMarginals} from '../src/lib/weather/marginalForecast.js';
const now=Date.parse(original.generated_at);
const parse=v=>parseWeatherMarginals(JSON.stringify(v),{nowMs:now});
it('keeps raw statistics separate from unqualified generated local medians and means',()=>{
 const result=parse(original);expect(result.state).toBe('ready');expect(result.localCoverageQualified).toBe(false);
 const row=result.rows[0];expect(row.raw.p50).toBeNull();expect(row.local.empirical.mean).toBeNull();
 expect(row.local.empirical.point_estimate_kind).toBe('model_median');expect(row.local.temperature_normal.point_estimate_kind).toBe('model_mean');
 expect(row.unit).toBe('degC');expect(row.label).toContain('unqualified');
});
it.each(['private','qualified','crossing','fake-mean','joint','duplicate'])('withholds malformed %s marginal products',damage=>{
 const v=structuredClone(original);
 if(damage==='private')v.rows[0].local.temperature_normal.private_path='/private';
 if(damage==='qualified')v.local_coverage_qualified=true;
 if(damage==='crossing')v.rows[0].local.temperature_normal.quantiles.reverse();
 if(damage==='fake-mean')v.rows[0].local.empirical.mean=v.rows[0].local.empirical.point_estimate;
 if(damage==='joint')v.joint_probability=.8;
 if(damage==='duplicate')v.rows.push(v.rows[0]);
 expect(parse(v).state).toBe('unavailable');
});
it('expires the optional view without preserving stale values',()=>{
 const result=parseWeatherMarginals(JSON.stringify(original),{nowMs:Date.parse(original.valid_until)});
 expect(result.state).toBe('unavailable');expect(result.rows).toEqual([]);
});
it('preserves nonnegative wind atoms and refuses negative wind uncertainty',()=>{
 const v=structuredClone(original),r=structuredClone(v.rows[0]);r.kind='wind';r.target_start=v.generated_at;r.target_end=new Date(now+3600000).toISOString();
 r.raw={mean:0,p10:null,p50:null,p90:null};r.adaptive=null;
 r.local={empirical:null,nonnegative:{...r.local.temperature_normal,mean:.4,point_estimate:.4,quantiles:[0,0,.1,.5,1]}};v.rows=[r];
 expect(parse(v).rows[0].unit).toBe('m_s');expect(parse(v).rows[0].raw.mean).toBe(0);
 r.local.nonnegative.quantiles[0]=-.1;expect(parse(v).state).toBe('unavailable');
});
