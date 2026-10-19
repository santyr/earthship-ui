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
 expect(pv.textContent).toContain('PV 1 kWh');expect(pv.title).toContain('before battery acceptance');
 expect(container.textContent).not.toContain('remaining');
});
it('withdraws expired potential rather than reusing an old daily estimate',()=>{
 dailyPvRaw.set(JSON.stringify(fixture()));dailyPvClock.set(now+90*60000);
 const {container}=render(DailyForecast,{days});expect(container.querySelector('[data-testid="daily-pv-potential"]')).toBeNull();
});
