import {afterEach,it,expect} from 'vitest';
import original from './fixtures/weather-rain-shadow.json';
import emission from './fixtures/weather-rain-emission.json';
import {mkdtemp,writeFile,chmod,symlink,rm,mkdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createServer} from 'node:http';
import {readFileSync} from 'node:fs';
const originalRaw=readFileSync(new URL('./fixtures/weather-rain-shadow.json',import.meta.url),'utf8');
import {householdObservationPlugin} from '../src/lib/household/observationServer.js';
const disposals=[];afterEach(async()=>{for(const fn of disposals.splice(0).reverse())await fn()});
async function endpoint(change=async()=>{}){
 const root=await mkdtemp(join(tmpdir(),'weather-rain-'));await chmod(root,0o700);disposals.push(()=>rm(root,{recursive:true,force:true}));
 const file=join(root,'rain-candidates.json');await writeFile(file,originalRaw,{mode:0o600});const emissions=join(root,'rain-emissions');await mkdir(emissions,{mode:0o700});await writeFile(join(emissions,'view-'+original.report_sha256+'.json'),JSON.stringify(emission),{mode:0o600});await change(file,root);
 let handler;householdObservationPlugin({weatherRainPath:file,now:()=>Date.parse(original.generated_at)+2000}).configureServer({middlewares:{use(fn){handler=fn}}});
 const server=createServer((req,res)=>handler(req,res,()=>res.writeHead(404).end()));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 disposals.push(()=>new Promise(resolve=>{server.close(resolve);server.closeAllConnections()}));return 'http://127.0.0.1:'+server.address().port;
}
it('serves a fixed GET-only rain shadow without browser-selected paths',async()=>{
 const base=await endpoint(),response=await fetch(base+'/api/weather-rain-shadow');expect(response.status).toBe(200);expect(await response.json()).toEqual(original);
 expect(response.headers.get('cache-control')).toBe('no-store');
 expect((await fetch(base+'/api/weather-rain-shadow?file=/etc/passwd')).status).toBe(400);
 expect((await fetch(base+'/api/weather-rain-shadow',{method:'POST'})).status).toBe(405);
 expect((await fetch(base+'/api/weather-rain-shadow/other')).status).toBe(404);
});
it.each(['missing','symlink','permissions','private','stale','oversize','duplicate','unconfirmed','wrong-emission','changed-values','bom'])('withholds %s optional state without disclosing private contents',async damage=>{
 const base=await endpoint(async(file,root)=>{
  if(damage==='missing')await rm(file);
  if(damage==='bom')await writeFile(file,'\ufeff'+originalRaw);
  if(damage==='unconfirmed')await rm(join(root,'rain-emissions','view-'+original.report_sha256+'.json'));
  if(damage==='wrong-emission')await writeFile(join(root,'rain-emissions','view-'+original.report_sha256+'.json'),JSON.stringify({...emission,cache_bytes_sha256:'f'.repeat(64)}));
  if(damage==='permissions')await chmod(file,0o644);
  if(damage==='symlink'){const target=join(root,'private.json');await writeFile(target,'operator-private');await rm(file);await symlink(target,file)}
  if(damage==='oversize')await writeFile(file,'x'.repeat(256*1024+1));
  if(['private','stale','duplicate','changed-values'].includes(damage)){
   const p=structuredClone(original);if(damage==='changed-values')p.rows[0].raw_means_mm.total_precipitation_1hr+=1;if(damage==='private')p.source_originals={private_path:'operator-private'};if(damage==='stale')p.valid_until=p.generated_at;
   let raw=JSON.stringify(p);if(damage==='duplicate')raw=raw.replace('{','{"rows":[],');await writeFile(file,raw);
  }
 });
 const response=await fetch(base+'/api/weather-rain-shadow');expect(response.status).toBe(503);expect(await response.json()).toEqual({status:'unavailable'});
});
