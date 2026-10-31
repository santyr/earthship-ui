// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render} from '@testing-library/svelte';
vi.mock('svelte',async()=>import('../../node_modules/svelte/src/index-client.js'));
import RecommendationPreview from '../../src/lib/ui/RecommendationPreview.svelte';
import {recommendationObservation} from '../fixtures/household-recommendations.js';
import {AT} from '../fixtures/household-observation.js';
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();vi.unstubAllGlobals();});
it.each(['loads','night-policy','greywater','devices','feeding'])('retires %s previews without polling the old proposal source',group=>{
 vi.spyOn(Date,'now').mockReturnValue(AT);
 const fetcher=vi.fn(async()=>new Response(JSON.stringify(recommendationObservation())));vi.stubGlobal('fetch',fetcher);
 const {container}=render(RecommendationPreview,{group});
 expect(container.querySelector('[data-recommendation-group]')).toBeNull();
 expect(container.textContent).not.toContain('Night-load override');
 expect(fetcher).not.toHaveBeenCalled();
});
it('keeps current thermal advice explicitly unavailable when no qualified model candidate exists',()=>{
 const {container}=render(RecommendationPreview,{group:'shades'});
 expect(container.textContent).toContain('Model shade advice unavailable');
 expect(container.textContent).toContain('Automatic actuation disabled');
});
