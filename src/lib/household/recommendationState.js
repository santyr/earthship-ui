import {readable} from 'svelte/store';
import {loadHouseholdObservation} from './observationClient.js';
/** Subscribers share one fixed GET poll; the last subscriber owns cleanup. */
export function createRecommendationState({load=loadHouseholdObservation,now=()=>Date.now()}={}){
 const raw=readable(null,set=>{
  let stopped=false,controller=null,deadline=null;set(null);
  async function refresh(){
   controller?.abort();clearTimeout(deadline);const current=new AbortController();controller=current;
   deadline=setTimeout(()=>current.abort(),10000);
   try{const value=await load(current.signal);if(!stopped&&controller===current&&!current.signal.aborted)set(value);}
   catch{if(!stopped&&controller===current)set(null);}
   finally{if(controller===current)clearTimeout(deadline);}
  }
  refresh();const timer=setInterval(refresh,30000);
  return()=>{stopped=true;clearInterval(timer);clearTimeout(deadline);controller?.abort();};
 });
 const clock=readable(now(),set=>{set(now());const timer=setInterval(()=>set(now()),1000);return()=>clearInterval(timer);});
 return {raw,clock};
}
const shared=createRecommendationState();
export const householdObservationRaw=shared.raw;
export const recommendationClock=shared.clock;
