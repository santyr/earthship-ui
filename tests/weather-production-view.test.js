import {it,expect} from 'vitest';
import original from './fixtures/weather-production.json';
import receipt from './fixtures/weather-production-view-receipt.json';
import {parseProductionWeather,validateProductionViewReceipt,productionWeatherAt} from '../src/lib/weather/productionForecast.js';
const nowMs=Date.parse(original.published_at)+1000;
const parse=v=>parseProductionWeather(JSON.stringify(v),{nowMs});
it('reads confirmed original production ranges and keeps raw and model statistics distinct',()=>{
 const view=parse(original);expect(view.state).toBe('ready');expect(view.issueSha256).toBe(original.issue_sha256);
 const row=view.rows.find(r=>r.kind==='temperature'&&r.local);expect(row.local.point_estimate_kind).toBe('model_mean');
 expect(productionWeatherAt(view,row.target_end,'temperature')).toEqual(row);
 expect(view.rows.find(r=>r.kind==='wind')?.raw.statistic).toBe('native_boundary_mean_hour_approximation');
 expect(parseProductionWeather(JSON.stringify(original),{nowMs,issueSha256:'f'.repeat(64)}).state).toBe('unavailable');
});
it.each(['private','duplicate','crossing','nonfinite','stale','unissued','probability','model','wind-quantile','target','source'])('withholds malformed %s ranges without damaging the core forecast',damage=>{
 const v=structuredClone(original),row=v.rows.find(r=>r.local);
 if(damage==='private')v.original_sources={path:'/private'};
 if(damage==='crossing')row.local.quantiles.reverse();
 if(damage==='nonfinite')row.local.point_estimate=null;
 if(damage==='stale')v.valid_until=v.generated_at;
 if(damage==='unissued')v.issued=false;
 if(damage==='probability')v.local_coverage_qualified=true;
 if(damage==='model')row.local.model_sha256='f'.repeat(64);
 if(damage==='wind-quantile')v.rows.find(r=>r.kind==='wind').raw.p10=0;
 if(damage==='target')row.target_end=v.generated_at;
 if(damage==='source')row.source_sha256='f'.repeat(64);
 const raw=damage==='duplicate'?JSON.stringify(v).replace('{','{"rows":[],'):JSON.stringify(v);
 expect(parseProductionWeather(raw,{nowMs}).state).toBe('unavailable');
});
it('allows a valid model mean outside its marginal range and zero wind quantiles',()=>{
 const v=structuredClone(original),row=v.rows.find(r=>r.kind==='wind');row.local.quantiles=[0,0,0,0,0];row.local.point_estimate=3;
 expect(parse(v).state).toBe('ready');
});
it('requires the original byte-bound production view receipt',()=>{
 const view=parse(original),args={view,cacheBytesSha256:receipt.cache_bytes_sha256,nowMs};
 expect(validateProductionViewReceipt(JSON.stringify(receipt),args)).toBe(true);
 for(const override of [{issue_sha256:'f'.repeat(64)},{production_emission_sha256:'f'.repeat(64)},{cache_bytes_sha256:'f'.repeat(64)},{issued:false},{private:'secret'}])
  expect(validateProductionViewReceipt(JSON.stringify({...receipt,...override}),args)).toBe(false);
});
