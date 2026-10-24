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
it('does not duplicate optimistic feedback when the next poll returns its retained event',async()=>{
 vi.spyOn(Date,'now').mockReturnValue(Date.parse(fixture.evaluated_at));vi.useFakeTimers();const journal=[];
 vi.stubGlobal('fetch',vi.fn(async(url,options)=>{
  if(options?.method==='POST'){const v=JSON.parse(options.body);journal.push({...v,episode_id:fixture.recommendations[0].episode_id,at:fixture.evaluated_at,origin:'operator'});return new Response('{"status":"retained"}');}
  return new Response(JSON.stringify(url==='/api/household-advice'?fixture:url.endsWith('feedback')?{events:journal}:url.endsWith('context')?{targets:[]}:{declarations:[]}));
 }));
 const r=render(DecisionRecommendations);await vi.advanceTimersByTimeAsync(10);await fireEvent.click(r.getByRole('button',{name:'Seen'}));await vi.advanceTimersByTimeAsync(30010);
 expect(r.getAllByRole('button',{name:'Undo feedback'})).toHaveLength(1);
});
it('renders a compact header summary with a provisional comparison and no state caveats',async()=>{
 const data=structuredClone(fixture);data.recommendations=[];data.domains.ventilation={status:'conditional',reason:'provisional_comfort_comparison',missing:[],valid_until:fixture.valid_until,comparison:[{alternative:'Leave unchanged',outcome:'Existing conditions',value:null,unit:'qualitative',metric:'directional_thermal_effect',horizon_end:fixture.valid_until},{alternative:'Ventilate briefly',outcome:'80°F indoors, 60°F outdoors. Provisional comfort band 70–76°F.',value:null,unit:'qualitative',metric:'directional_thermal_effect',horizon_end:fixture.valid_until}]};
 vi.spyOn(Date,'now').mockReturnValue(Date.parse(fixture.evaluated_at));vi.stubGlobal('fetch',vi.fn(async url=>new Response(JSON.stringify(url==='/api/household-advice'?data:url.endsWith('context')?{targets:[]}:url.endsWith('state')?{declarations:[],checks:{}}:{events:[]}))));
 const r=render(DecisionRecommendations,{header:true});
 await waitFor(()=>expect(r.getByRole('button',{name:/Suggestions.*Ventilate briefly/i})).toBeTruthy());
 expect(r.container.textContent).toContain('Provisional');expect(r.container.textContent).toContain('70–76°F');
 expect(r.queryByText(/shade state|window state|unconfirmed/i)).toBeNull();
 expect(r.queryByRole('button',{name:'Report action taken'})).toBeNull();
});
it('marks provisional suggestions expired at their domain deadline on a quiet stream',async()=>{
 const data=structuredClone(fixture);data.recommendations=[];data.domains.shades={...data.domains.shades,comparison:[]};
 data.domains.ventilation={status:'conditional',reason:'provisional_comfort_comparison',missing:[],valid_until:new Date(Date.parse(fixture.evaluated_at)+30000).toISOString(),comparison:[{alternative:'Leave unchanged',outcome:'Existing conditions',value:null,unit:'qualitative',metric:'directional_thermal_effect',horizon_end:fixture.valid_until},{alternative:'Ventilate briefly',outcome:'Provisional comfort band 70–76°F.',value:null,unit:'qualitative',metric:'directional_thermal_effect',horizon_end:fixture.valid_until}]};
 let at=Date.parse(fixture.evaluated_at);vi.spyOn(Date,'now').mockImplementation(()=>at);vi.useFakeTimers();vi.stubGlobal('fetch',vi.fn(async url=>new Response(JSON.stringify(url==='/api/household-advice'?data:url.endsWith('context')?{targets:[]}:url.endsWith('state')?{declarations:[],checks:{}}:{events:[]}))));
 const r=render(DecisionRecommendations,{header:true});await vi.advanceTimersByTimeAsync(10);
 expect(r.getByRole('button',{name:/Suggestions.*Ventilate briefly/i}).getAttribute('aria-label')).not.toContain('Expired');
 at+=31000;await vi.advanceTimersByTimeAsync(31000);
 expect(r.getByRole('button',{name:/Suggestions.*Expired.*Ventilate briefly/i})).toBeTruthy();
});
