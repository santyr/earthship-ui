/** Fixed private files and same-origin human records. No OpenHAB transport. */
import {resolve,join} from 'node:path';import {homedir} from 'node:os';
import {watch} from 'node:fs';
import {open,rename,unlink,stat,lstat,realpath} from 'node:fs/promises';import {randomUUID} from 'node:crypto';
import {readObservation} from './observationServer.js';import {uniqueObjectKeys} from './observation.js';
import {parseShadeObservations} from './shadeObservations.js';
import {parseAdvice,shape} from './advice.js';
const MAX=128;
const token=v=>typeof v==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9_. -]{0,79}$/.test(v);
const hash=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
function parse(raw){const v=JSON.parse(raw);uniqueObjectKeys(raw);return v;}
const feedbackValid=raw=>{const v=parse(raw);return shape(v,['schema','events'])&&v.schema==='earthship-household-advice-feedback/v1'&&Array.isArray(v.events)&&v.events.length<=MAX&&v.events.every(e=>shape(e,['event_id','report_id','recommendation_id','episode_id','kind','at','snooze_until','corrects','origin'])&&token(e.event_id)&&hash(e.report_id)&&hash(e.recommendation_id)&&hash(e.episode_id)&&['acknowledge','dismiss','snooze','report_action_taken','undo'].includes(e.kind)&&e.origin==='operator'&&Number.isFinite(Date.parse(e.at))&&(e.snooze_until===null||Number.isFinite(Date.parse(e.snooze_until)))&&(e.corrects===null||token(e.corrects)));};
async function directoryGuard(dir){const info=await stat(dir);if(await realpath(dir)!==dir||!info.isDirectory()||info.uid!==process.getuid()||(info.mode&0o777)!==0o700)throw Error('private directory unavailable');}
async function readOptional(path,validate,empty,at){try{return parse(await readObservation(path,at,validate,262144));}catch(e){if(e.code==='ENOENT')return empty;throw e;}}
async function writeOwned(dir,file,value){
 await directoryGuard(dir);const target=join(dir,file);try{const s=await lstat(target);if(!s.isFile()||s.uid!==process.getuid()||(s.mode&0o777)!==0o600||s.nlink!==1)throw Error('private file required');}catch(e){if(e.code!=='ENOENT')throw e;}
 const temp=join(dir,'.advice-'+randomUUID()+'.tmp');let handle;
 try{handle=await open(temp,'wx',0o600);await handle.writeFile(JSON.stringify(value));await handle.sync();await handle.close();handle=null;await directoryGuard(dir);await rename(temp,target);const parent=await open(dir,'r');try{await parent.sync();}finally{await parent.close();}}
 finally{await handle?.close();await unlink(temp).catch(()=>{});}
}
const iso=v=>typeof v==='string'&&/(?:Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v));
const checksValid=checks=>checks&&typeof checks==='object'&&!Array.isArray(checks)&&Object.keys(checks).length<=8&&Object.entries(checks).every(([key,r])=>
 ['rain','wind','security','smoke','occupancy'].includes(key)&&shape(r,['clear','observed_at','valid_until','source_ref'])&&typeof r.clear==='boolean'&&hash(r.source_ref)&&iso(r.observed_at)&&iso(r.valid_until)&&Date.parse(r.observed_at)<Date.parse(r.valid_until));
const stateValid=raw=>{const v=parse(raw);return shape(v,['schema','declarations','checks'])&&v.schema==='earthship-household-operator-state/v1'&&Array.isArray(v.declarations)&&v.declarations.length<=64&&v.declarations.every(r=>shape(r,['target','kind','value','reported_at','valid_until','source','revision'])&&token(r.target)&&['shade','opening'].includes(r.kind)&&r.source==='operator'&&token(r.revision)&&iso(r.reported_at)&&iso(r.valid_until)&&Date.parse(r.reported_at)<Date.parse(r.valid_until)&&Date.parse(r.valid_until)-Date.parse(r.reported_at)<=86400000&&(r.kind==='shade'?typeof r.value==='number'&&Number.isFinite(r.value)&&r.value>=0&&r.value<=100:['open','closed'].includes(r.value)))&&checksValid(v.checks);};

async function context(dir,at){
 const p=await readOptional(join(dir,'advice-policy.json'),raw=>{const v=parse(raw);return v.schema==='earthship-household-advice-policy/v1';},null,at);
 const targets=[];if(p?.shades&&token(p.shades.target))targets.push({target:p.shades.target,kind:'shade'});if(p?.ventilation&&token(p.ventilation.target))targets.push({target:p.ventilation.target,kind:'opening'});
 return {targets};
}
export function householdAdvicePlugin({directory=resolve(homedir(),'.local/state/household-intel'),now=Date.now}={}){
 const subscribers=new Set();let watcher=null,heartbeat=null,notification=null;
 const changedFiles=new Set(['advice.json','advice-feedback.json','advice-operator-state.json','advice-policy.json','advice-provisional-preferences.json','shade-observations.json']);
 function release(){watcher?.close();watcher=null;clearInterval(heartbeat);heartbeat=null;clearTimeout(notification);notification=null;}
 function broadcast(message){for(const response of subscribers){if(response.writableLength>4096)response.end();else response.write(message);}}
 function observe(){
  if(watcher)return;
  watcher=watch(directory,{persistent:false},(event,file)=>{
   if(file!==null&&!changedFiles.has(String(file)))return;
   clearTimeout(notification);notification=setTimeout(()=>{notification=null;broadcast('data: update\n\n');},50);
  });
  watcher.on('error',()=>{release();for(const response of subscribers)response.end();subscribers.clear();});
  heartbeat=setInterval(()=>broadcast(': keepalive\n\n'),25000);heartbeat.unref?.();
 }
 function close(){release();for(const response of subscribers)response.end();subscribers.clear();}
 let queue=Promise.resolve();const attach=server=>{server.httpServer?.once('close',close);server.middlewares.use(async(req,res,next)=>{
  let url;try{url=new URL(req.url||'/','http://localhost');}catch{return next();}
  const routes=['/api/household-advice','/api/household-advice-events','/api/household-advice-feedback','/api/household-advice-state','/api/household-advice-context','/api/household-shade-observations'];if(!routes.includes(url.pathname))return next();
  const send=(status,value)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(value));};
  if(url.search)return send(400,{status:'unavailable'});
  const writable=['/api/household-advice-feedback','/api/household-advice-state'].includes(url.pathname);
  if(req.method!=='GET'&&!(writable&&req.method==='POST')){res.setHeader('Allow',writable?'GET, POST':'GET');return send(405,{status:'unavailable'});}
  try{
   await directoryGuard(directory);
   if(req.method==='GET'){
    if(url.pathname==='/api/household-advice-events'){
     if(subscribers.size>=64)return send(503,{status:'unavailable'});
     observe();res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-store','X-Accel-Buffering':'no'});
     subscribers.add(res);res.on('close',()=>{subscribers.delete(res);if(!subscribers.size)release();});
     res.write('retry: 5000\n: connected\n\n');return;
    }
    if(url.pathname==='/api/household-shade-observations'){const raw=await readObservation(join(directory,'shade-observations.json'),now(),parseShadeObservations);return send(200,parse(raw));}
    if(url.pathname==='/api/household-advice'){const raw=await readObservation(join(directory,'advice.json'),now(),parseAdvice);return send(200,parse(raw));}
    if(url.pathname==='/api/household-advice-context')return send(200,await context(directory,now()));
    const feedback=url.pathname.endsWith('feedback');
    const journal=await readOptional(join(directory,feedback?'advice-feedback.json':'advice-operator-state.json'),feedback?feedbackValid:stateValid,feedback?{schema:'earthship-household-advice-feedback/v1',events:[]}:{schema:'earthship-household-operator-state/v1',declarations:[],checks:{}},now());
    if(feedback){const physical=await readOptional(join(directory,'advice-observed-targets.json'),raw=>{const v=parse(raw);return shape(v,['schema','generated_at','events','omitted_count','automatic_actuation'])&&Number.isInteger(v.omitted_count)&&v.omitted_count>=0&&v.schema==='earthship-household-observed-targets/v1'&&v.automatic_actuation===false&&Array.isArray(v.events)&&v.events.length<=32&&v.events.every(e=>shape(e,['event_id','episode_id','kind','at','snooze_until','corrects','evidence_refs','target','position_open_pct','shade_ids','origin','user_motivation_known','thermal_benefit_verified'])&&hash(e.event_id)&&hash(e.episode_id)&&e.kind==='target_observed'&&e.origin==='device_observation'&&token(e.target)&&e.user_motivation_known===false&&e.thermal_benefit_verified===false&&Array.isArray(e.evidence_refs)&&e.evidence_refs.every(hash)&&Array.isArray(e.shade_ids)&&e.shade_ids.every(token)&&Number.isFinite(e.position_open_pct));},{events:[]},now());journal.events=[...journal.events,...physical.events];}
    return send(200,journal);
   }
   let origin;try{origin=new URL(req.headers.origin);}catch{return send(403,{status:'unavailable'});}
   if(origin.host!==req.headers.host||!['http:','https:'].includes(origin.protocol)||req.headers['content-type']?.split(';')[0]!=='application/json')return send(403,{status:'unavailable'});
   let body='',size=0;for await(const chunk of req){size+=chunk.length;if(size>2048)return send(413,{status:'unavailable'});body+=chunk;}
   const v=parse(body);
   const write=async()=>{
    const at=now();await directoryGuard(directory);
    if(url.pathname.endsWith('feedback')){
     if(!shape(v,['event_id','report_id','recommendation_id','kind','snooze_until','corrects'])||!token(v.event_id)||!hash(v.report_id)||!hash(v.recommendation_id)||!['acknowledge','dismiss','snooze','report_action_taken','undo'].includes(v.kind))return send(400,{status:'unavailable'});
     const journal=await readOptional(join(directory,'advice-feedback.json'),feedbackValid,{schema:'earthship-household-advice-feedback/v1',events:[]},at);
     const old=journal.events.find(e=>e.event_id===v.event_id);
     if(old)return send(Object.keys(v).every(k=>old[k]===v[k])?200:409,{status:'retained'});
     if(journal.events.length>=MAX)return send(507,{status:'capacity_exhausted'});
     if(v.kind==='undo'){
      const corrected=journal.events.find(e=>e.event_id===v.corrects&&e.kind!=='undo'&&e.origin==='operator');
      if(!corrected||corrected.report_id!==v.report_id||corrected.recommendation_id!==v.recommendation_id||v.snooze_until!==null)return send(400,{status:'unavailable'});
      journal.events.push({...v,episode_id:corrected.episode_id,at:new Date(at).toISOString(),origin:'operator'});await writeOwned(directory,'advice-feedback.json',journal);return send(200,{status:'retained'});
     }
     const view=parseAdvice(await readObservation(join(directory,'advice.json'),at,parseAdvice),{nowMs:at});
     const rec=view.current.find(r=>r.recommendation_id===v.recommendation_id);
     if(!rec||view.report.report_id!==v.report_id)return send(409,{status:'advice_changed'});
     if(v.kind==='snooze'?(typeof v.snooze_until!=='string'||!(at<Date.parse(v.snooze_until)&&Date.parse(v.snooze_until)<=at+86400000)):v.snooze_until!==null)return send(400,{status:'unavailable'});
     if(v.kind==='undo'?!journal.events.some(e=>e.event_id===v.corrects&&e.episode_id===rec.episode_id&&e.kind!=='undo'):v.corrects!==null)return send(400,{status:'unavailable'});
     journal.events.push({...v,episode_id:rec.episode_id,at:new Date(at).toISOString(),origin:'operator'});await writeOwned(directory,'advice-feedback.json',journal);return send(200,{status:'retained'});
    }
    if(!shape(v,['event_id','target','kind','value','valid_minutes'])||!token(v.event_id)||!token(v.target)||!['shade','opening'].includes(v.kind)||!Number.isInteger(v.valid_minutes)||v.valid_minutes<1||v.valid_minutes>1440||(v.kind==='shade'?typeof v.value!=='number'||!Number.isFinite(v.value)||v.value<0||v.value>100:!['open','closed'].includes(v.value)))return send(400,{status:'unavailable'});
    const c=await context(directory,at);if(!c.targets.some(t=>t.target===v.target&&t.kind===v.kind))return send(400,{status:'unavailable'});
    const state=await readOptional(join(directory,'advice-operator-state.json'),stateValid,{schema:'earthship-household-operator-state/v1',declarations:[],checks:{}},at);
    const row={target:v.target,kind:v.kind,value:v.value,reported_at:new Date(at).toISOString(),valid_until:new Date(at+v.valid_minutes*60000).toISOString(),source:'operator',revision:v.event_id};
    const old=state.declarations.find(e=>e.revision===v.event_id);if(old)return send(old.target===row.target&&old.kind===row.kind&&old.value===row.value?200:409,{status:'retained'});
    if(state.declarations.length>=64)return send(507,{status:'capacity_exhausted'});
    state.declarations.push(row);await writeOwned(directory,'advice-operator-state.json',state);return send(200,{status:'retained'});
   };
   const pending=queue.then(write);queue=pending.catch(()=>{});await pending;
  }catch{if(!res.headersSent)send(503,{status:'unavailable'});}
 });};
 return {name:'household-human-advice',configureServer:attach,configurePreviewServer:attach,closeBundle:close};
}
