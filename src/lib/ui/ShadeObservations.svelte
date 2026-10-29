<script>
 import {readable} from 'svelte/store';import {parseShadeObservations} from '../household/shadeObservations.js';import {recommendationClock} from '../household/recommendationState.js';
 const raw=readable(null,set=>{let stopped=false,controller;async function refresh(){controller?.abort();controller=new AbortController();const current=controller;const deadline=setTimeout(()=>current.abort(),10000);try{const r=await fetch('/api/household-shade-observations',{signal:current.signal,cache:'no-store',redirect:'error'});const text=r.ok?await r.text():null;if(!stopped&&controller===current&&!current.signal.aborted)set(text&&text.length<=32768?text:null);}catch{if(!stopped)set(null);}finally{clearTimeout(deadline);}}refresh();const timer=setInterval(refresh,30000);return()=>{stopped=true;clearInterval(timer);controller?.abort();};});
 const view=$derived(parseShadeObservations($raw,{nowMs:$recommendationClock}));
</script>
<details class="observations"><summary>Actual shade position and movement observations</summary>
 {#if !view?.observations.length}<p>No commissioned position observations. Preview positions remain rehearsal values.</p>
 {:else}{#each view.observations as row (row.shade_id)}<p><strong>{row.shade_id} · {row.zone}:</strong> {row.current?`${row.position_open_pct}% open`:'Position unavailable or stale'} · {row.movement} · {row.feedback_basis.replaceAll('_',' ')} · origin {row.origin.replaceAll('_',' ')}. Native {row.native_position??'unknown'} ({row.native_convention}); epoch {row.epoch}; acquisition clock {row.time_basis.replaceAll('_',' ')}.</p>{/each}{/if}
 <p>Observed position does not establish why a shade moved or verify its thermal benefit.</p>
</details>
<style>.observations{font-size:.62rem;color:#bbccdd;max-height:7rem;overflow:auto}summary{cursor:pointer}p{margin:.3rem 0}</style>
