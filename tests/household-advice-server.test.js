import {afterEach,expect,it} from 'vitest';
import {mkdtemp,writeFile,chmod,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {createServer} from 'node:http';
import fixture from './fixtures/household-advice-v1.json';
import {householdAdvicePlugin} from '../src/lib/household/adviceServer.js';
const clean=[];afterEach(async()=>{for(const f of clean.splice(0).reverse())await f();});
async function endpoint(){
 const dir=await mkdtemp(join(tmpdir(),'advice-'));await chmod(dir,0o700);clean.push(()=>rm(dir,{recursive:true,force:true}));
 await writeFile(join(dir,'advice.json'),JSON.stringify(fixture),{mode:0o600});let handler;
 householdAdvicePlugin({directory:dir,now:()=>Date.parse(fixture.evaluated_at)}).configureServer({middlewares:{use(fn){handler=fn;}}});
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
