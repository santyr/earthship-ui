import {afterEach,expect,it} from 'vitest';
import {mkdtemp,chmod,writeFile,rename,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {createServer} from 'node:http';
import {householdAdvicePlugin} from '../src/lib/household/adviceServer.js';
const cleanup=[];
afterEach(async()=>{for(const fn of cleanup.splice(0).reverse())await fn();});
async function setup(){
 const dir=await mkdtemp(join(tmpdir(),'advice-events-'));await chmod(dir,0o700);cleanup.push(()=>rm(dir,{recursive:true,force:true}));
 let handler;const plugin=householdAdvicePlugin({directory:dir});
 const server=createServer((req,res)=>handler(req,res,()=>res.writeHead(404).end()));
 plugin.configureServer({httpServer:server,middlewares:{use(fn){handler=fn;}}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 cleanup.push(async()=>{plugin.closeBundle();await new Promise(resolve=>{server.close(resolve);server.closeAllConnections();});});
 return {dir,plugin,base:`http://127.0.0.1:${server.address().port}`};
}
async function stream(t){
 const controller=new AbortController();cleanup.push(()=>controller.abort());
 const response=await fetch(t.base+'/api/household-advice-events',{signal:controller.signal});
 expect(response.status).toBe(200);expect(response.headers.get('content-type')).toBe('text/event-stream');
 const reader=response.body.getReader();expect(new TextDecoder().decode((await reader.read()).value)).toContain(': connected');
 return reader;
}
it.each(['advice.json','advice-operator-state.json','advice-feedback.json'])('notifies atomic %s replacements and closes active readers at server shutdown',async file=>{
 const t=await setup();const reader=await stream(t);
 await writeFile(join(t.dir,'.pending'),JSON.stringify({private:'never sent'}),{mode:0o600});await rename(join(t.dir,'.pending'),join(t.dir,file));
 const next=await reader.read();expect(new TextDecoder().decode(next.value)).toBe('data: update\n\n');
 t.plugin.closeBundle();expect((await reader.read()).done).toBe(true);
});
it('supports multiple clients with the same publication notification',async()=>{
 const t=await setup();const a=await stream(t),b=await stream(t);
 await writeFile(join(t.dir,'advice.json'),'{}',{mode:0o600});
 const messages=await Promise.all([a.read(),b.read()]);expect(messages.every(r=>new TextDecoder().decode(r.value)==='data: update\n\n')).toBe(true);
});
it('keeps the notification endpoint fixed and read only',async()=>{
 const t=await setup();expect((await fetch(t.base+'/api/household-advice-events?file=other')).status).toBe(400);
 expect((await fetch(t.base+'/api/household-advice-events',{method:'POST'})).status).toBe(405);
});
