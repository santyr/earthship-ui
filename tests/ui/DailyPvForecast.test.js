// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest';
import { render, cleanup } from '@testing-library/svelte';
import { fixture, now } from '../fixtures/daily-pv-potential.js';
vi.mock('../../src/lib/energy/dailyPvState.js',async()=>{const {writable}=await import('svelte/store');return {dailyPvRaw:writable(null),dailyPvClock:writable(0)};});
import { dailyPvRaw, dailyPvClock } from '../../src/lib/energy/dailyPvState.js';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
import DailyForecast from '../../src/lib/ui/DailyForecast.svelte';
const days=[{date:'2026-10-19',label:'Today',summary:{highF:65,lowF:46,precipPct:null,precipSumIn:0,pvKwh:null,weatherCode:null,cloudPct:40}}];
afterEach(()=>{cleanup();dailyPvRaw.set(null)});
it.each(['home','weather'])('renders separate daily PV potential on %s cards',variant=>{
 dailyPvRaw.set(JSON.stringify(fixture()));dailyPvClock.set(now);
 const {container}=render(DailyForecast,{days,variant});
 const pv=container.querySelector('[data-testid="daily-pv-potential"]');expect(pv).not.toBeNull();
 expect(pv.textContent).toContain('PV 1.3 kWh');expect(pv.title).toContain('before battery acceptance');
 expect(container.textContent).not.toContain('remaining');
});
it('withdraws expired potential rather than reusing an old daily estimate',()=>{
 dailyPvRaw.set(JSON.stringify(fixture()));dailyPvClock.set(now+90*60000);
 const {container}=render(DailyForecast,{days});expect(container.querySelector('[data-testid="daily-pv-potential"]')).toBeNull();
});

it('labels provisional empirical calibration without claiming captured PV',async()=>{
 const {calibratedFixture}=await import('../fixtures/daily-pv-potential.js');dailyPvRaw.set(JSON.stringify(calibratedFixture()));dailyPvClock.set(now);
 const {container}=render(DailyForecast,{days});const pv=container.querySelector('[data-testid="daily-pv-potential"]');
 expect(pv?.title).toContain('empirically adjusted over the next 24 hours');expect(pv?.title).toContain('before battery acceptance');
});

it('labels the supported long-horizon policy without a misleading 24-hour limit',async()=>{
 const {calibratedFixture}=await import('../fixtures/daily-pv-potential.js');const v=calibratedFixture();
 v.schema='earthship-daily-pv-potential/v3';v.confidence='provisional_empirical_supported_horizon';v.calibration.policySha256='f'.repeat(64);
 v.calibration.applyThroughAt=new Date(now+336*3600000).toISOString();v.days[0].calibrationScope='empirical_supported_horizon';
 dailyPvRaw.set(JSON.stringify(v));dailyPvClock.set(now);const {container}=render(DailyForecast,{days});const pv=container.querySelector('[data-testid="daily-pv-potential"]');
 expect(pv?.title).toContain('empirically adjusted in supported solar positions');expect(pv?.title).not.toContain('next 24 hours');
});

it('labels active native-component correction and preserves raw fallback identity',async()=>{
 const {componentFixture}=await import('../fixtures/daily-pv-potential.js');const v=componentFixture();
 dailyPvRaw.set(JSON.stringify(v));dailyPvClock.set(now);
 const {container}=render(DailyForecast,{days});let pv=container.querySelector('[data-testid="daily-pv-potential"]');
 expect(pv.title).toContain('Experimental native solar components');
 expect(pv.title).toContain('native segments only');expect(pv.title).not.toContain('next 24 hours');
});
