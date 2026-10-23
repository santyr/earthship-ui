// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';import {cleanup,render,waitFor,fireEvent} from '@testing-library/svelte';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
import DecisionRecommendations from '../../src/lib/ui/DecisionRecommendations.svelte';
import fixture from '../fixtures/household-advice-v1.json';
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});
function serve(){vi.spyOn(Date,'now').mockReturnValue(Date.parse(fixture.evaluated_at));const fetcher=vi.fn(async url=>new Response(JSON.stringify(url==='/api/household-advice'?fixture:url.endsWith('context')?{targets:[]}:url.endsWith('state')?{declarations:[],checks:{}}:{events:[]})));vi.stubGlobal('fetch',fetcher);return fetcher;}
it('shows a usable action, time, reason, evidence, and baseline details',async()=>{
 serve();const r=render(DecisionRecommendations);
 await waitFor(()=>expect(r.container.textContent).toContain('Open living shades to 100% open'));
 expect(r.container.textContent).toContain('Manual advice');expect(r.container.textContent).toContain('Admit available solar heat');
 expect(r.container.textContent).toContain('Baseline');expect(r.container.textContent).toContain('rule based');
});
it('feedback writes only to the human journal and never a device endpoint',async()=>{
 const fetcher=serve();const r=render(DecisionRecommendations);await waitFor(()=>expect(r.getByRole('button',{name:'Seen'})).toBeTruthy());
 await fireEvent.click(r.getByRole('button',{name:'Seen'}));
 const posts=fetcher.mock.calls.filter(([,o])=>o?.method==='POST');expect(posts).toHaveLength(1);expect(posts[0][0]).toBe('/api/household-advice-feedback');
 expect(JSON.parse(posts[0][1].body).kind).toBe('acknowledge');expect(fetcher.mock.calls.some(([url])=>url.startsWith('/rest'))).toBe(false);
});
it('removes actionable cards when clock expires on a quiet stream',async()=>{
 serve();vi.useFakeTimers();const r=render(DecisionRecommendations);await vi.advanceTimersByTimeAsync(10);
 expect(r.container.textContent).toContain('Open living shades');vi.spyOn(Date,'now').mockReturnValue(Date.parse(fixture.evaluated_at)+121000);await vi.advanceTimersByTimeAsync(1000);
 expect(r.queryByRole('button',{name:'Seen'})).toBeNull();expect(r.container.textContent).toContain('expired');
});
