// @vitest-environment jsdom
import { cleanup,render,waitFor } from '@testing-library/svelte';
import { afterEach,expect,it,vi } from 'vitest';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
import PvPotentialAccuracy from '../../src/lib/ui/PvPotentialAccuracy.svelte';
import { pvPerformance,PV_REPORT_NOW } from '../fixtures/daily-pv-performance.js';
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
it.each([true,false])('shows eligible PV errors separately from censored evidence (collecting=%s)',async collecting=>{
 vi.spyOn(Date,'now').mockReturnValue(PV_REPORT_NOW);vi.stubGlobal('fetch',async()=>new Response(JSON.stringify(pvPerformance({collecting}))));
 const {container}=render(PvPotentialAccuracy);
 await waitFor(()=>expect(container.querySelector('table[aria-label="PV potential forecast accuracy"]')).not.toBeNull());
 expect(container.textContent).toContain('charging/clipping');expect(container.textContent).toContain('166 hours without a recorded score');
 if(collecting){expect(container.textContent).toContain('Collecting eligible daylight observations');expect(container.textContent).not.toContain('0.0 W');}
 else{expect(container.textContent).toContain('200.0');expect(container.textContent).toContain('125.0');expect(container.textContent).toContain('12 / 12');}
 expect(container.querySelectorAll('button,form')).toHaveLength(0);
});
it('withholds invalid reports and labels valid stale reports',async()=>{
 vi.spyOn(Date,'now').mockReturnValue(PV_REPORT_NOW+3*3600000);vi.stubGlobal('fetch',async()=>new Response(JSON.stringify(pvPerformance())));
 const {container}=render(PvPotentialAccuracy);await waitFor(()=>expect(container.textContent).toContain('PV accuracy report is stale'));
});
