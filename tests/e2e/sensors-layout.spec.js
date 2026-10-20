import {expect,test} from '@playwright/test';
import {createServer} from 'vite';
import {execFileSync} from 'node:child_process';
import {mkdirSync,readFileSync} from 'node:fs';
const enabled=process.env.SENSOR_INTEGRATION==='1';

let server;
test.beforeAll(async()=>{
 expect(enabled,'sensor project requires SENSOR_INTEGRATION=1 and the isolated Compose stack').toBe(true);
 process.env.OPENHAB_PROXY_TARGET='http://127.0.0.1:18084';
 delete process.env.OPENHAB_TOKEN;
 execFileSync('/tmp/earthship-sensor-test-venv/bin/python',['-m','services.lorawan.tests.browser_auth'],{timeout:20000});
 process.env.OPENHAB_TOKEN=JSON.parse(readFileSync('.superpowers/lorawan-private/browser-auth.json','utf8')).token;
 server=await createServer({plugins:[{name:'isolated-sensor-qualification',configureServer(vite){
  vite.middlewares.use('/sensor-qualification.html',(_request,response)=>{
   response.setHeader('Content-Type','text/html');
   response.end('<!doctype html><html><body style="margin:0"><main id="sensor-qualification" style="height:100dvh;padding:12px;box-sizing:border-box"></main><script type="module" src="/tests/e2e/sensor-harness.js"></script></body></html>');
  });
 }}],server:{host:'127.0.0.1',port:5194,strictPort:true}});await server.listen();
});
test.afterAll(async()=>{await server?.close();});
for(const [width,height] of [[1340,800],[1280,720]]) {
 test(`sensor dashboard ${width}x${height}: real OpenHAB SSE, transitions and bounded layout`,async({page})=>{
  await page.setViewportSize({width,height});
  await page.route('**/api/**',route=>route.fulfill({status:503,json:{status:'unavailable'}}));
  await page.route('**/config.json',route=>route.fulfill({json:{openhabUrl:'',apiToken:'',staleBannerSeconds:90}}));
  const privateResponse=await page.request.get('http://127.0.0.1:5194/.superpowers/lorawan-private/ingest.json');
  expect(privateResponse.status()).toBe(403);
  const providers=await page.request.get('http://127.0.0.1:5194/rest/things');
  expect(providers.status()).toBe(200);
  const things=await providers.json();
  expect(Array.isArray(things)).toBe(true);
  expect(things.length).toBeGreaterThan(0);
  expect(things.every(thing=>Object.keys(thing).every(key=>['UID','label','statusInfo'].includes(key)))).toBe(true);
  const errors=[],mutations=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(!['GET','HEAD'].includes(request.method()))mutations.push(request.method()+' '+request.url());});
  await page.goto('http://127.0.0.1:5194/sensor-qualification.html');
  await expect(page.locator('[data-sensor]')).toHaveCount(15);
  await expect(page.getByText('Synthetic demonstration')).toBeVisible();
  execFileSync('/tmp/earthship-sensor-test-venv/bin/python',['-m','services.lorawan.tests.integration_probe','--state','0'],{timeout:20000});
  await expect(page.locator('[data-sensor="opening_01"] .state strong')).toHaveText('Closed');
  const start=Date.now();
  execFileSync('/tmp/earthship-sensor-test-venv/bin/python',['-m','services.lorawan.tests.integration_probe','--state','1'],{timeout:20000});
  await expect(page.locator('[data-sensor="opening_01"] .state strong')).toHaveText('Open');
  expect(Date.now()-start).toBeLessThan(5000);
  const geometry=await page.evaluate(()=>{
   const screen=document.querySelector('[data-ventilation-screen]');
   const cards=[...document.querySelectorAll('[data-sensor]')];
   const footer=screen.querySelector('footer');
   return {scroll:screen.scrollHeight>screen.clientHeight+1,overflow:document.documentElement.scrollWidth>innerWidth,
    cards:cards.every(c=>c.getBoundingClientRect().bottom<=footer.getBoundingClientRect().top+1)};
  });
  expect(geometry).toEqual({scroll:false,overflow:false,cards:true});
  mkdirSync('docs/screenshots',{recursive:true});
  if(width===1340)await page.screenshot({path:'docs/screenshots/sensors-simulation-1340x800.png'});
  await page.goto('http://127.0.0.1:5194/#/ventilation');
  await expect(page.locator('.earthship-grid')).toBeVisible();
  await expect(page.locator('[data-ventilation-screen]')).toHaveCount(0);
  expect(errors).toEqual([]);expect(mutations).toEqual([]);
 });
}
