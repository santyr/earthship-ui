import {afterEach,it,expect} from 'vitest';
import {mkdtemp,chmod,mkdir,writeFile,rm,symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createServer} from 'node:http';
import {createHash} from 'node:crypto';
import {householdObservationPlugin} from '../src/lib/household/observationServer.js';
import {sensitivity,confirmation,nowMs} from './fixtures/weather-sensitivity.js';
const clean=[];afterEach(async()=>{for(const fn of clean.splice(0).reverse())await fn();});
async function setup(damage){
 const dir=await mkdtemp(join(tmpdir(),'sensitivity-'));await chmod(dir,0o700);clean.push(()=>rm(dir,{recursive:true,force:true}));
 const file=join(dir,'scenario-advisory.json'),receipts=join(dir,'scenario-reports');await mkdir(receipts,{mode:0o700});
 const v=sensitivity(),raw=JSON.stringify(v);await writeFile(file,raw,{mode:0o600});const pin=createHash('sha256').update(raw).digest('hex'),receipt=join(receipts,'view-'+v.report_sha256+'.json');
 const r=confirmation(v,pin);if(damage==='binding')r.cache_bytes_sha256='0'.repeat(64);if(damage==='future')r.published_at=v.through;
 if(damage!=='missing')await writeFile(receipt,JSON.stringify(r),{mode:0o600});
 if(damage==='private')await writeFile(file,raw.replace('{','{"private":"/operator",'));
 if(damage==='permissions')await chmod(file,0o644);
 if(damage==='symlink'){await rm(file);await symlink(receipt,file);}
 let handler;householdObservationPlugin({weatherSensitivityPath:file,now:()=>nowMs}).configureServer({middlewares:{use(fn){handler=fn;}}});
 const server=createServer((req,res)=>handler(req,res,()=>res.writeHead(404).end()));await new Promise(r=>server.listen(0,'127.0.0.1',r));clean.push(()=>new Promise(r=>{server.close(r);server.closeAllConnections();}));
 return {url:`http://127.0.0.1:${server.address().port}/api/weather-sensitivity`,raw};
}
it('serves only the confirmed literal view through the fixed read-only route',async()=>{
 const {url,raw}=await setup();const response=await fetch(url);expect(response.status).toBe(200);expect(await response.text()).toBe(raw);expect(response.headers.get('cache-control')).toBe('no-store');
 expect((await fetch(url+'?file=/private')).status).toBe(400);expect((await fetch(url,{method:'POST'})).status).toBe(405);expect((await fetch(url+'/other')).status).toBe(404);
});
it.each(['missing','binding','future','private','permissions','symlink'])('withholds %s source and confirmation failures',async damage=>{
 const {url}=await setup(damage);const r=await fetch(url);expect(r.status).toBe(503);expect(await r.text()).toBe('{"status":"unavailable"}');
});
