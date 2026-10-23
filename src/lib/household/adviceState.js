import {readable} from 'svelte/store';
import {parseAdvice} from './advice.js';
/** One shared bounded poll. Rendering never runs a model or fetches a device. */
export const adviceState=readable({raw:null,events:[],targets:[],declarations:[]},set=>{
 let stopped=false,controller=null;
 async function refresh(){
  controller?.abort();const current=new AbortController();controller=current;const timeout=setTimeout(()=>current.abort(),10000);
  const paths=['/api/household-advice','/api/household-advice-feedback','/api/household-advice-context','/api/household-advice-state'];
  try{
   const values=await Promise.allSettled(paths.map(async path=>{
    const r=await fetch(path,{signal:current.signal,cache:'no-store',redirect:'error'});if(!r.ok)throw Error('unavailable');
    const raw=await r.text();if(raw.length>262144)throw Error('oversized');return raw;
   }));
   if(stopped||current!==controller||current.signal.aborted)return;
   const raw=values[0].status==='fulfilled'&&parseAdvice(values[0].value)?values[0].value:null;
   const json=i=>{try{return values[i].status==='fulfilled'?JSON.parse(values[i].value):{};}catch{return {};}};
   set({raw,events:json(1).events??[],targets:json(2).targets??[],declarations:json(3).declarations??[]});
  }finally{clearTimeout(timeout);}
 }
 refresh();const timer=setInterval(refresh,30000);const wake=()=>{if(globalThis.document?.visibilityState!=='hidden')refresh();};globalThis.document?.addEventListener('visibilitychange',wake);globalThis.window?.addEventListener('pageshow',wake);
 return()=>{stopped=true;controller?.abort();clearInterval(timer);globalThis.document?.removeEventListener('visibilitychange',wake);globalThis.window?.removeEventListener('pageshow',wake);};
});
