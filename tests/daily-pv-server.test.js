import { afterEach, expect, it } from 'vitest';
import { mkdtemp, writeFile, chmod, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createServer } from 'node:http';
import { fixture, calibratedFixture, now } from './fixtures/daily-pv-potential.js';
import { householdObservationPlugin } from '../src/lib/household/observationServer.js';
const cleanup = [];
afterEach(async () => { for (const task of cleanup.splice(0).reverse()) await task(); });
it.each([['/api/daily-pv-potential', fixture], ['/api/daily-pv-potential', calibratedFixture]])(
  'serves fixed curated GET %s without allowing file selection or authority', async (endpoint, fixture) => {
    const dir = await mkdtemp(join(tmpdir(), 'energy-monitoring-')); await chmod(dir, 0o700); cleanup.push(() => rm(dir, { recursive: true, force: true }));
    const path = join(dir, 'value.json'); await writeFile(path, JSON.stringify(fixture()), { mode: 0o600 });
    let handler;
    householdObservationPlugin({ dailyPvCachePath: path, now: () => now })
      .configureServer({ middlewares: { use(fn) { handler = fn; } } });
    const server = createServer((req, res) => handler(req, res, () => res.writeHead(404).end()));
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); cleanup.push(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
    const url = `http://127.0.0.1:${server.address().port}${endpoint}`;
    const response = await fetch(url); expect(response.status).toBe(200); expect(await response.json()).toEqual(fixture());
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect((await fetch(url, { method: 'POST' })).status).toBe(405); expect((await fetch(`${url}?path=/etc/passwd`)).status).toBe(400);
    await writeFile(path, JSON.stringify({ ...fixture(), original_path: '/operator-private' }));
    const refused = await fetch(url); expect(refused.status).toBe(503); expect(await refused.json()).toEqual({ status: 'unavailable' });
  },
);

import {terrainDaylightPlugin} from '../src/lib/weather/terrainDaylightServer.js';
const terrainReport=()=>({schema:'earthship-terrain-daylight/v1',method:'native-five-minute-terrain-endpoint-mask/v1',day:'2026-10-20',timezone:'America/Denver',calculatedAt:'2026-10-20T18:00:00Z',dayStartAt:'2026-10-20T06:00:00Z',validUntil:'2026-10-21T06:00:00Z',geometryAvailableAt:'2026-10-19T18:00:00Z',geometrySha256:'a'.repeat(64),horizonSha256:'b'.repeat(64),sourceRuntimeSha256:'c'.repeat(64),daySeconds:86400,terrainSunlightSeconds:32400,unobstructedSunlightSeconds:39600,firstSunAt:'2026-10-20T14:00:00Z',lastSunAt:'2026-10-20T23:00:00Z',resolutionSeconds:300,confidence:'unvalidated_map_estimate',physical_calibration_qualified:false,automatic_actuation:false});
async function terrainServer(options){
 let handler;expect(terrainDaylightPlugin(options).configureServer({middlewares:{use(fn){handler=fn;return()=>{};}}})).toBeUndefined();
 const server=createServer((req,res)=>handler(req,res,()=>res.writeHead(404).end()));await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));cleanup.push(()=>new Promise(resolve=>{server.close(resolve);server.closeAllConnections();}));return `http://127.0.0.1:${server.address().port}/api/terrain-daylight`;
}
it('bounds the fixed terrain route and shares one private projection across concurrent GETs',async()=>{
 let calls=0,release;const barrier=new Promise(resolve=>release=resolve);let clock=Date.parse('2026-10-20T20:00:00Z');
 const url=await terrainServer({load:async()=>{calls++;await barrier;return JSON.stringify(terrainReport());},now:()=>clock});
 expect((await fetch(url,{method:'POST'})).status).toBe(405);expect((await fetch(url+'?path=/etc/passwd')).status).toBe(400);expect(calls).toBe(0);
 const first=fetch(url),second=fetch(url);await new Promise(resolve=>setTimeout(resolve,10));release();
 const responses=await Promise.all([first,second]);expect(calls).toBe(1);
 for(const response of responses){expect(response.status).toBe(200);expect(response.headers.get('cache-control')).toBe('no-store');expect(await response.json()).toEqual(terrainReport());}
 expect((await fetch(url)).status).toBe(200);expect(calls).toBe(1);
 clock=Date.parse('2026-10-21T06:00:00Z');expect((await fetch(url)).status).toBe(503);expect(calls).toBe(2);
});
it('keeps private failures bounded and retries an optional terrain projection after refusal',async()=>{
 let calls=0,clock=Date.parse('2026-10-20T20:00:00Z');
 const url=await terrainServer({load:async()=>{calls++;if(calls===1)throw Error('private path or credential');return JSON.stringify(terrainReport());},now:()=>clock});
 const bad=await fetch(url);expect(bad.status).toBe(503);expect(await bad.text()).toBe('{"status":"unavailable"}');
 expect((await fetch(url)).status).toBe(503);expect(calls).toBe(1);
 clock+=30001;expect((await fetch(url)).status).toBe(200);expect(calls).toBe(2);
});
it.each(['authority','extra','corrupt'])('refuses malformed terrain worker output: %s',async kind=>{
 const report=terrainReport();if(kind==='authority')report.automatic_actuation=true;if(kind==='extra')report.privatePath='/private';
 const url=await terrainServer({load:async()=>kind==='corrupt'?'private stderr, no JSON':JSON.stringify(report),now:()=>Date.parse('2026-10-20T20:00:00Z')});
 expect((await fetch(url)).status).toBe(503);
});
