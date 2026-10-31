// @vitest-environment jsdom
import {render,cleanup,waitFor} from '@testing-library/svelte';
import {afterEach,expect,it,vi} from 'vitest';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
vi.mock('../../src/lib/household/adviceState.js',async()=>{
 const actual=await vi.importActual('../../src/lib/household/adviceState.js');const {writable}=await import('svelte/store');
 return {...actual,adviceState:writable({raw:null,events:[],targets:[],declarations:[],refreshStatus:'current'}),refreshAdvice:vi.fn()};
});
vi.mock('../../src/lib/household/recommendationState.js',async()=>{const {writable}=await import('svelte/store');return {recommendationClock:writable(0)};});
import DecisionRecommendations from '../../src/lib/ui/DecisionRecommendations.svelte';
import {adviceState} from '../../src/lib/household/adviceState.js';
import {recommendationClock} from '../../src/lib/household/recommendationState.js';
import fixture from '../fixtures/household-advice-v1.json';
import provisional from '../fixtures/household-provisional-advice-v1.json';
afterEach(cleanup);
function setup(report=fixture,delta=0,status='current'){
 recommendationClock.set(Date.parse(report.evaluated_at)+delta);
 adviceState.set({raw:JSON.stringify(report),events:[],targets:[],declarations:[],refreshStatus:status});
}
it('shows only current action text and suppresses expired actions without a transport update',async()=>{
 setup();const r=render(DecisionRecommendations,{header:true});
 expect(r.container.querySelector('.header-summary').textContent).toBe('Open living shades to 100% open');
 expect(r.container.querySelector('.header-summary').getAttribute('aria-label')).toBe('Open living shades to 100% open');
 recommendationClock.set(Date.parse(fixture.evaluated_at)+180000);
 await waitFor(()=>expect(r.container.querySelector('.header-summary').textContent).toBe('Awaiting fresh evidence'));
 expect(r.container.querySelector('.header-summary').textContent).not.toContain('Open living shades');
 expect(r.container.textContent).toContain('Last advice expired');expect(r.container.querySelector('.cards .action')).toBeNull();
});
it('retains failed-read history while suppressing actionable controls and original clocks',()=>{
 setup(fixture,60000,'failed');const r=render(DecisionRecommendations,{header:true});
 expect(r.container.querySelector('.header-summary').textContent).toBe('Awaiting fresh evidence');
 expect(r.container.textContent).toContain('Update failed');expect(r.container.textContent).toContain('updates every 5 minutes');
 expect(r.container.querySelector('.cards .action')).toBeNull();
});
it('marks a provisional comparison stale at its own earlier source horizon',()=>{
 const report=structuredClone(provisional);const at=Date.parse(report.evaluated_at);report.valid_until=new Date(at+300000).toISOString();
 for(const d of Object.values(report.domains))if(d.reason.startsWith('provisional_')){d.valid_until=new Date(at+15000).toISOString();d.comparison.forEach(c=>c.horizon_end=d.valid_until);}
 setup(report,60000);const r=render(DecisionRecommendations,{header:true});
 expect(r.container.querySelector('.header-summary').textContent).toBe('Awaiting fresh evidence');
 expect(r.container.querySelector('.header-summary').textContent).not.toContain('Ventilate');
 expect(r.container.textContent).toContain('expired');
});
