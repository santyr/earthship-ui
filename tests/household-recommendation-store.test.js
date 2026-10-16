import {afterEach,expect,it,vi} from 'vitest';
import {createRecommendationState} from '../src/lib/household/recommendationState.js';
afterEach(()=>vi.useRealTimers());
it('shares one read-only poll and clock, aborts on last unsubscribe and rejects late responses',async()=>{
 vi.useFakeTimers();let resolve;const load=vi.fn(signal=>new Promise(r=>{resolve=r;}));const s=createRecommendationState({load,now:()=>Date.now()});
 const a=[],b=[];const stopA=s.raw.subscribe(v=>a.push(v)),stopB=s.raw.subscribe(v=>b.push(v)),stopClock=s.clock.subscribe(()=>{});
 expect(load).toHaveBeenCalledTimes(1);resolve('original');await vi.advanceTimersByTimeAsync(0);expect(a.at(-1)).toBe('original');expect(b.at(-1)).toBe('original');
 stopA();await vi.advanceTimersByTimeAsync(30000);expect(load).toHaveBeenCalledTimes(2);const signal=load.mock.calls[1][0];
 stopB();stopClock();expect(signal.aborted).toBe(true);resolve('late');await vi.advanceTimersByTimeAsync(60000);expect(load).toHaveBeenCalledTimes(2);expect(b.at(-1)).toBe('original');
});
