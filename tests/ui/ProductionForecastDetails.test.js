// @vitest-environment jsdom
import {cleanup,render,screen,fireEvent} from '@testing-library/svelte';
import {afterEach,beforeEach,it,expect,vi} from 'vitest';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
vi.mock('../../src/lib/weather/productionState.js',async()=>{
 const {writable}=await import('svelte/store');return {productionWeatherRaw:writable(null),productionWeatherClock:writable(0)};
});
import original from '../fixtures/weather-production.json';
import ProductionForecastDetails from '../../src/lib/ui/ProductionForecastDetails.svelte';
import {productionWeatherRaw,productionWeatherClock} from '../../src/lib/weather/productionState.js';
beforeEach(()=>{productionWeatherRaw.set(JSON.stringify(original));productionWeatherClock.set(Date.parse(original.published_at)+1000)});
afterEach(()=>cleanup());
it('shows active original means, local ranges, native quantities and finite training support',()=>{
 render(ProductionForecastDetails,{issueSha256:original.issue_sha256});
 expect(screen.getByText('Active production forecast · experimental')).toBeTruthy();
 expect(screen.getByText(/Local temperature mean/)).toBeTruthy();
 expect(screen.getByText(/Local p10–p90/)).toBeTruthy();
 expect(screen.getByText(/Hourly wind estimate unavailable/)).toBeTruthy();
 expect(screen.getByText(/local target dates/)).toBeTruthy();
 expect(screen.getByText(/Local interval coverage is unverified/)).toBeTruthy();
});
it('withholds a valid optional report from a different core issue',()=>{
 render(ProductionForecastDetails,{issueSha256:'f'.repeat(64)});
 expect(screen.getByRole('status').textContent).toContain('Production ranges unavailable');
 expect(screen.queryByText(/Local temperature mean/)).toBeNull();
});
it('changes to a real published hour and names the hourly wind approximation',async()=>{
 render(ProductionForecastDetails,{issueSha256:original.issue_sha256});
 const row=original.rows.find(r=>r.kind==='wind');
 await fireEvent.change(screen.getByRole('combobox',{name:'Production forecast hour'}),{target:{value:row.target_end}});
 expect(screen.getByText(/Local station hourly wind mean/)).toBeTruthy();
 expect(screen.getByText(/Native boundary-mean hourly approximation/)).toBeTruthy();
});
