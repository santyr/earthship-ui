// @vitest-environment node
import {test,expect} from 'vitest';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createBuiltFixtureServer} from './e2e/built-fixture-server.js';

test('built fixture serves complete assets while isolating backends and owning only preview state',async()=>{
 const directory=await mkdtemp(join(tmpdir(),'built-fixture-contract-'));
 await writeFile(join(directory,'index.html'),'<html>complete fixture application</html>');
 await writeFile(join(directory,'app.js'),'globalThis.fixtureLoaded=true;');
 const origins=new Set();const server=await createBuiltFixtureServer(directory,origins);
 try {
  await server.listen();const origin=server.resolvedUrls.local[0];expect(origins.has(origin)).toBe(true);
  expect(await fetch(origin).then(r=>r.text())).toContain('complete fixture application');
  const asset=await fetch(origin+'/app.js');expect(asset.headers.get('content-type')).toBe('text/javascript');expect(await asset.text()).toContain('fixtureLoaded');
  for(const path of ['/rest/items','/fixture-openhab/rest/items','/api/household-advice']){
   expect((await fetch(origin+path)).status).toBe(503);
   expect((await fetch(origin+path,{method:'POST',body:'ON'})).status).toBe(503);
  }
  expect(await fetch(origin+'/config.json').then(r=>r.json())).toMatchObject({apiToken:'',openhabUrl:''});
  expect((await fetch(origin+'/app.js',{method:'POST',body:'change'})).status).toBe(405);
  const update=await fetch(origin+'/api/shades-preview',{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify({slots:[1],openPercent:25})});
  expect(update.status).toBe(200);expect((await update.json()).positions[0]).toBe(25);
 }finally{await server.close();await server.close();await rm(directory,{recursive:true,force:true});}
 expect(origins.size).toBe(0);
});
