import {readable} from 'svelte/store';
import {parseAdvice} from './advice.js';
export const ADVICE_REFRESH_MS=5*60*1000;
const paths=['/api/household-advice','/api/household-advice-feedback','/api/household-advice-context','/api/household-advice-state'];
/** One shared transport. Notifications read published results; never run a model. */
export function createAdviceState({fetcher=(...args)=>fetch(...args),now=()=>Date.now(),eventSource=path=>new EventSource(path)}={}){
 let value={raw:null,events:[],targets:[],declarations:[],refreshStatus:'loading',lastAttemptAt:null,lastSuccessfulAt:null};
 let activeRefresh=null;
 const state=readable(value,set=>{
  let stopped=false,controller=null,deadline=null,inFlight=null,again=false,stream=null,opened=false;
  const update=fields=>{value={...value,...fields};set(value);};
  function refresh(){
   if(stopped)return Promise.resolve();
   if(inFlight){again=true;return inFlight;}
   const current=new AbortController();controller=current;
   const timeout=setTimeout(()=>current.abort(),10000);deadline=timeout;
   update({lastAttemptAt:now()});
   inFlight=(async()=>{
    try{
     const responses=await Promise.allSettled(paths.map(async path=>{
      const response=await fetcher(path,{signal:current.signal,cache:'no-store',redirect:'error'});
      if(!response.ok)throw Error('unavailable');
      const raw=await response.text();if(new TextEncoder().encode(raw).length>262144)throw Error('oversized');return raw;
     }));
     if(stopped||current.signal.aborted)return;
     const raw=responses[0].status==='fulfilled'&&parseAdvice(responses[0].value,{nowMs:now()})?responses[0].value:null;
     const list=(index,key,previous)=>{
      try{const parsed=responses[index].status==='fulfilled'?JSON.parse(responses[index].value):null;return Array.isArray(parsed?.[key])?parsed[key]:previous;}catch{return previous;}
     };
     update({raw:raw??value.raw,refreshStatus:raw?'current':'failed',lastSuccessfulAt:raw?now():value.lastSuccessfulAt,
      events:list(1,'events',value.events),targets:list(2,'targets',value.targets),declarations:list(3,'declarations',value.declarations)});
    }catch{
     if(!stopped)update({refreshStatus:'failed'});
    }finally{
     clearTimeout(timeout);
     if(!stopped&&current.signal.aborted)update({refreshStatus:'failed'});
     inFlight=null;
     if(again&&!stopped){again=false;refresh();}
    }
   })();
   return inFlight;
  }
  activeRefresh=refresh;refresh();
  const timer=setInterval(refresh,ADVICE_REFRESH_MS);
  const wake=()=>{if(globalThis.document?.visibilityState!=='hidden')refresh();};
  const online=()=>refresh();
  globalThis.document?.addEventListener('visibilitychange',wake);
  globalThis.window?.addEventListener('pageshow',wake);
  globalThis.window?.addEventListener('online',online);
  try{
   stream=eventSource('/api/household-advice-events');
   stream.onmessage=()=>refresh();
   stream.onopen=()=>{if(opened||value.refreshStatus==='failed')refresh();opened=true;};
  }catch{/* Five-minute fallback also supports clients without EventSource. */}
  return()=>{
   stopped=true;activeRefresh=null;again=false;controller?.abort();clearTimeout(deadline);clearInterval(timer);stream?.close();
   globalThis.document?.removeEventListener('visibilitychange',wake);
   globalThis.window?.removeEventListener('pageshow',wake);
   globalThis.window?.removeEventListener('online',online);
  };
 });
 return {subscribe:state.subscribe,refresh:()=>activeRefresh?.()??Promise.resolve()};
}
export const adviceState=createAdviceState();
export const refreshAdvice=()=>adviceState.refresh();

export function adviceAge(evaluatedAt,nowMs){
 const minutes=Math.max(0,Math.floor((nowMs-Date.parse(evaluatedAt))/60000));
 if(minutes<1)return 'just now';
 if(minutes<60)return `${minutes} min ago`;
 const hours=Math.floor(minutes/60);return `${hours}h ${minutes%60}m ago`;
}
