// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,waitFor} from '@testing-library/svelte';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
import RecommendationPreview from '../../src/lib/ui/RecommendationPreview.svelte';
import {recommendationObservation} from '../fixtures/household-recommendations.js';
import {AT} from '../fixtures/household-observation.js';
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});
function serve(){vi.spyOn(Date,'now').mockReturnValue(AT);const fetcher=vi.fn(async()=>new Response(JSON.stringify(recommendationObservation())));vi.stubGlobal('fetch',fetcher);return fetcher;}
it('shows exact action, source clocks, confidence and blockers using only the fixed GET',async()=>{
 const fetcher=serve();const {container,getAllByText,getByText}=render(RecommendationPreview,{group:'loads'});
 await waitFor(()=>expect(getAllByText('Night-load override: OFF').length).toBeGreaterThan(0));
 expect(getByText('Low forecast battery SoC')).toBeTruthy();expect(container.textContent).toContain('Blocked');
 expect(container.textContent).toContain('Confidence: unavailable');expect(container.textContent).toContain('Original decision');
 expect(container.textContent).toContain('Automatic actuation disabled');expect(container.querySelector('form,input,select')).toBeNull();
 expect([...container.querySelectorAll('button')].every(b=>b.hasAttribute('popovertarget'))).toBe(true);
 expect(fetcher.mock.calls.every(([url,options])=>url==='/api/household-observation'&&!options.method)).toBe(true);
});
it('expires from the display clock without waiting for another fetch',async()=>{
 serve();vi.useFakeTimers();const {container}=render(RecommendationPreview,{group:'greywater'});await vi.advanceTimersByTimeAsync(1);
 expect(container.textContent).toContain('Blocked');vi.spyOn(Date,'now').mockReturnValue(AT+60000);await vi.advanceTimersByTimeAsync(1000);
 expect(container.textContent).toContain('Expired');
});
it('does not fabricate feeding or shade advice when it is absent',async()=>{
 serve();const a=render(RecommendationPreview,{group:'feeding'});await waitFor(()=>expect(a.container.textContent).toContain('Not proposed'));
 const b=render(RecommendationPreview,{group:'shades'});expect(b.container.textContent).toContain('Model shade advice unavailable');
});
