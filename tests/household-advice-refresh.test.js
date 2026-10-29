// @vitest-environment jsdom
import {afterEach,expect,it,vi} from 'vitest';
import {createAdviceState,adviceAge,ADVICE_REFRESH_MS} from '../src/lib/household/adviceState.js';
import fixture from './fixtures/household-advice-v1.json';
const subscriptions=[];
afterEach(()=>{subscriptions.splice(0).forEach(fn=>fn());vi.useRealTimers();vi.unstubAllGlobals();});
async function flush(){for(let i=0;i<20;i++)await Promise.resolve();}
function setup(){
 vi.useFakeTimers();vi.setSystemTime(new Date(fixture.evaluated_at));
 const stream={close:vi.fn()};let raw=JSON.stringify(fixture),failed=false;
 const fetcher=vi.fn(async path=>new Response(path==='/api/household-advice'?raw:JSON.stringify({events:[],targets:[],declarations:[]}),{status:failed?503:200}));
 const source=vi.fn(()=>stream);const state=createAdviceState({fetcher,eventSource:source});let latest;
 subscriptions.push(state.subscribe(v=>latest=v));
 return {state,fetcher,source,stream,get latest(){return latest;},fail:()=>failed=true,recover:()=>failed=false,invalid:()=>raw='{}'};
}
it('shares one initial read and one five-minute fallback without thirty-second polling',async()=>{
 const t=setup();subscriptions.push(t.state.subscribe(()=>{}));await flush();
 expect(t.fetcher).toHaveBeenCalledTimes(4);expect(t.source).toHaveBeenCalledTimes(1);expect(t.latest.refreshStatus).toBe('current');
 await vi.advanceTimersByTimeAsync(ADVICE_REFRESH_MS-1);expect(t.fetcher).toHaveBeenCalledTimes(4);
 await vi.advanceTimersByTimeAsync(1);await flush();expect(t.fetcher).toHaveBeenCalledTimes(8);
});
it('refreshes promptly for publication, visibility, page show, online and stream reconnection',async()=>{
 const t=setup();await flush();t.stream.onopen();await flush();expect(t.fetcher).toHaveBeenCalledTimes(4);
 for(const event of [()=>t.stream.onmessage({data:'update'}),()=>document.dispatchEvent(new Event('visibilitychange')),()=>window.dispatchEvent(new Event('pageshow')),()=>window.dispatchEvent(new Event('online')),()=>t.stream.onopen()]){
  const before=t.fetcher.mock.calls.length;event();await flush();expect(t.fetcher).toHaveBeenCalledTimes(before+4);
 }
});
it.each(['network','invalid'])('retains original issue and age after %s failure, then recovers',async damage=>{
 const t=setup();await flush();const before=t.latest;
 if(damage==='network')t.fail();else t.invalid();
 await vi.advanceTimersByTimeAsync(60000);await t.state.refresh();
 expect(t.latest.raw).toBe(before.raw);expect(t.latest.refreshStatus).toBe('failed');expect(t.latest.lastSuccessfulAt).toBe(before.lastSuccessfulAt);
 expect(adviceAge(JSON.parse(t.latest.raw).evaluated_at,Date.now())).toBe('1 min ago');
 if(damage==='network'){t.recover();await t.state.refresh();expect(t.latest.refreshStatus).toBe('current');expect(t.latest.raw).toBe(before.raw);}
});
it('coalesces overlapping notifications and fetches the state published during a pending read',async()=>{
 const t=setup();await flush();let finish;
 t.fetcher.mockImplementation(path=>new Promise(resolve=>{if(path==='/api/household-advice')finish=()=>resolve(new Response(JSON.stringify(fixture)));else resolve(new Response('{}'));}));
 const first=t.state.refresh();for(let i=0;i<5;i++)t.stream.onmessage({data:'update'});
 expect(t.fetcher).toHaveBeenCalledTimes(8);
 t.fetcher.mockImplementation(async path=>new Response(path==='/api/household-advice'?JSON.stringify(fixture):'{}'));
 finish();await first;await flush();expect(t.fetcher).toHaveBeenCalledTimes(12);
});
it('releases the stream, listeners, fallback and pending deadline at the last unsubscribe',async()=>{
 const t=setup();await flush();const calls=t.fetcher.mock.calls.length;
 subscriptions.splice(0).forEach(fn=>fn());expect(t.stream.close).toHaveBeenCalledTimes(1);expect(vi.getTimerCount()).toBe(0);
 window.dispatchEvent(new Event('online'));document.dispatchEvent(new Event('visibilitychange'));await vi.advanceTimersByTimeAsync(600000);
 expect(t.fetcher).toHaveBeenCalledTimes(calls);
});
it('reports a bounded transport timeout without discarding the previous evaluation',async()=>{
 const t=setup();await flush();const raw=t.latest.raw;
 t.fetcher.mockImplementation((path,{signal})=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>reject(Error('timeout')),{once:true})));
 const pending=t.state.refresh();await vi.advanceTimersByTimeAsync(10000);await pending;
 expect(t.latest.raw).toBe(raw);expect(t.latest.refreshStatus).toBe('failed');
});
