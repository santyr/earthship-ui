import {afterEach,it,expect} from 'vitest';
import {mkdtemp,writeFile,chmod,symlink,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createServer} from 'node:http';
import {householdObservationPlugin} from '../src/lib/household/observationServer.js';
import {capabilityFixture,CAPABILITY_NOW} from './fixtures/weather-capabilities.js';
const disposals=[];
afterEach(async()=>{for(const fn of disposals.splice(0).reverse())await fn()});
async function endpoint(change=async()=>{}){
 const root=await mkdtemp(join(tmpdir(),'weather-capability-'));await chmod(root,0o700);disposals.push(()=>rm(root,{recursive:true,force:true}));
 const file=join(root,'weather-capabilities.json');await writeFile(file,JSON.stringify(capabilityFixture()),{mode:0o600});await change(file,root);
 let handler;householdObservationPlugin({weatherCapabilitiesPath:file,now:()=>CAPABILITY_NOW}).configureServer({middlewares:{use(fn){handler=fn}}});
 const server=createServer((req,res)=>handler(req,res,()=>res.writeHead(404).end()));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));disposals.push(()=>new Promise(resolve=>{server.close(resolve);server.closeAllConnections()}));
 return 'http://127.0.0.1:'+server.address().port;
}
it('serves only a validated fixed capability file and disallows browser-selected paths',async()=>{
 const base=await endpoint();const response=await fetch(base+'/api/weather-capabilities');expect(response.status).toBe(200);expect(await response.json()).toEqual(capabilityFixture());expect(response.headers.get('cache-control')).toBe('no-store');
 expect((await fetch(base+'/api/weather-capabilities?file=/etc/passwd')).status).toBe(400);
 expect((await fetch(base+'/api/weather-capabilities',{method:'POST'})).status).toBe(405);
 expect((await fetch(base+'/api/weather-capabilities/other')).status).toBe(404);
});
it.each(['missing','symlink','permissions','private','duplicate','stale','oversize','private-run'])('withholds %s supplemental state without private payloads',async damage=>{
 const base=await endpoint(async(file,root)=>{
  if(damage==='missing')await rm(file);
  if(damage==='permissions')await chmod(file,0o644);
  if(damage==='symlink'){const target=join(root,'private.json');await writeFile(target,'operator-private');await rm(file);await symlink(target,file)}
  if(damage==='oversize')await writeFile(file,'x'.repeat(256*1024+1));
  if(['private','duplicate','stale','private-run'].includes(damage)){
   const v=capabilityFixture();if(damage==='private')v.private_path='/operator-private';if(damage==='stale')v.valid_until=v.generated_at;
   if(damage==='private-run')v.sources[0].run_id='private:/operator-private';
   let raw=JSON.stringify(v);if(damage==='duplicate')raw=raw.replace('{','{"groups":{"private_path":"operator-private"},');await writeFile(file,raw);
  }
 });
 const response=await fetch(base+'/api/weather-capabilities');expect(response.status).toBe(503);expect(await response.json()).toEqual({status:'unavailable'});
});
