import {afterEach,expect,it} from 'vitest';
import {mkdtemp,writeFile,chmod,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {createServer} from 'node:http';
import fixture from './fixtures/household-advice-v1.json';
import {householdAdvicePlugin} from '../src/lib/household/adviceServer.js';
const clean=[];afterEach(async()=>{for(const f of clean.splice(0).reverse())await f();});
async function endpoint(clock=()=>Date.parse(fixture.evaluated_at)){
 const dir=await mkdtemp(join(tmpdir(),'advice-'));await chmod(dir,0o700);clean.push(()=>rm(dir,{recursive:true,force:true}));
 await writeFile(join(dir,'advice.json'),JSON.stringify(fixture),{mode:0o600});let handler;
 householdAdvicePlugin({directory:dir,now:clock}).configureServer({middlewares:{use(fn){handler=fn;}}});
 const server=createServer((req,res)=>handler(req,res,()=>res.writeHead(404).end()));await new Promise(r=>server.listen(0,'127.0.0.1',r));clean.push(()=>new Promise(r=>{server.close(r);server.closeAllConnections();}));
 return {url:`http://127.0.0.1:${server.address().port}`,dir};
}
const body=()=>({event_id:'fixture-event-1',report_id:fixture.report_id,recommendation_id:fixture.recommendations[0].recommendation_id,kind:'acknowledge',snooze_until:null,corrects:null});
async function post(url,value,origin=url){return fetch(url+'/api/household-advice-feedback',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify(value)});}
it('serves the fixed report and refuses query paths and actuation methods',async()=>{
 const {url}=await endpoint();expect((await fetch(url+'/api/household-advice')).status).toBe(200);
 expect((await fetch(url+'/api/household-advice?file=/etc/passwd')).status).toBe(400);
 expect((await fetch(url+'/api/household-advice',{method:'POST'})).status).toBe(405);
});
it('retains feedback idempotently across plugin restart without any equipment transport',async()=>{
 const {url,dir}=await endpoint();expect((await post(url,body())).status).toBe(200);expect((await post(url,body())).status).toBe(200);
 const journal=JSON.parse(await readFile(join(dir,'advice-feedback.json'),'utf8'));expect(journal.events).toHaveLength(1);expect(journal.events[0].origin).toBe('operator');
 expect(journal.events[0].kind).toBe('acknowledge');expect(journal.events[0]).not.toHaveProperty('observed_position');
 const feedback=await (await fetch(url+'/api/household-advice-feedback')).json();expect(feedback.events).toHaveLength(1);
});
it.each(['cross-origin','command','unknown','oversized'])('rejects unsafe feedback: %s',async damage=>{
 const {url}=await endpoint(),v=body();if(damage==='command')v.command='ON';if(damage==='unknown')v.kind='run_rule';if(damage==='oversized')v.event_id='x'.repeat(3000);
 expect((await post(url,v,damage==='cross-origin'?'http://untrusted.example':url)).status).toBeGreaterThanOrEqual(400);
});
it('serves supported environmental checks and preserves them when recording a declaration',async()=>{
 const {url,dir}=await endpoint();const checks={rain:{clear:true,observed_at:fixture.evaluated_at,valid_until:fixture.valid_until,source_ref:'a'.repeat(64)}};
 await writeFile(join(dir,'advice-operator-state.json'),JSON.stringify({schema:'earthship-household-operator-state/v1',declarations:[],checks}),{mode:0o600});
 await writeFile(join(dir,'advice-policy.json'),JSON.stringify({schema:'earthship-household-advice-policy/v1',shades:{target:'living'},ventilation:null}),{mode:0o600});
 const response=await fetch(url+'/api/household-advice-state');expect(response.status).toBe(200);expect((await response.json()).checks).toEqual(checks);
 const written=await fetch(url+'/api/household-advice-state',{method:'POST',headers:{Origin:url,'Content-Type':'application/json'},body:JSON.stringify({event_id:'declaration-1',target:'living',kind:'shade',value:50,valid_minutes:30})});
 expect(written.status).toBe(200);expect(JSON.parse(await readFile(join(dir,'advice-operator-state.json'),'utf8')).checks).toEqual(checks);
});
it('can undo an operator event after its recommendation expires',async()=>{
 let at=Date.parse(fixture.evaluated_at);const {url}=await endpoint(()=>at);
 const action={...body(),kind:'report_action_taken'};expect((await post(url,action)).status).toBe(200);at+=121000;
 expect((await post(url,{...body(),event_id:'undo-1',kind:'undo',corrects:action.event_id})).status).toBe(200);
});
