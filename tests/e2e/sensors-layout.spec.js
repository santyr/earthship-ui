import {expect,test} from '@playwright/test';
import {createServer} from 'vite';
import {assertIsolatedSensorStack, runSensorPython} from './sensor-integration.js';
import {readFileSync} from 'node:fs';


let server, baseURL;
test.beforeAll(async()=>{
 assertIsolatedSensorStack();
 process.env.OPENHAB_PROXY_TARGET='http://127.0.0.1:18084';
 delete process.env.OPENHAB_TOKEN;
 runSensorPython('services.lorawan.tests.browser_auth');
 process.env.OPENHAB_TOKEN=JSON.parse(readFileSync('.superpowers/lorawan-private/browser-auth.json','utf8')).token;
 server=await createServer({cacheDir:'.superpowers/test-cache/sensors',configLoader:'runner',plugins:[{name:'isolated-sensor-qualification',configureServer(vite){
  vite.middlewares.use('/sensor-qualification.html',(_request,response)=>{
   response.setHeader('Content-Type','text/html');
   response.end('<!doctype html><html><body style="margin:0"><main id="sensor-qualification" style="height:100dvh;padding:12px;box-sizing:border-box"></main><script type="module" src="/tests/e2e/sensor-harness.js"></script></body></html>');
  });
 }}],server:{host:'127.0.0.1',port:0,strictPort:false}});await server.listen();baseURL=server.resolvedUrls.local[0];
});
test.afterAll(async()=>{await server?.close();});
for(const [width,height] of [[1340,800],[1280,720]]) {
 test(`sensor dashboard ${width}x${height}: real OpenHAB SSE, transitions and bounded layout`,async({page},testInfo)=>{
  const violations=[];
  await page.context().route('**/*',route=>{
   const request=route.request(),url=new URL(request.url());
   if(url.origin!==new URL(baseURL).origin||!['GET','HEAD'].includes(request.method())){
    violations.push(request.method()+' '+url.origin+url.pathname);return route.abort('blockedbyclient');
   }
   return route.continue();
  });
  await page.setViewportSize({width,height});
  await page.route('**/api/**',route=>route.fulfill({status:503,json:{status:'unavailable'}}));
  await page.route('**/config.json',route=>route.fulfill({json:{openhabUrl:'',apiToken:'',staleBannerSeconds:90}}));
  const privateResponse=await page.request.get(baseURL+'.superpowers/lorawan-private/ingest.json');
  expect(privateResponse.status()).toBe(403);
  const providers=await page.request.get(baseURL+'rest/things');
  expect(providers.status()).toBe(200);
  const things=await providers.json();
  expect(Array.isArray(things)).toBe(true);
  expect(things.length).toBeGreaterThan(0);
  expect(things.every(thing=>Object.keys(thing).every(key=>['UID','label','statusInfo'].includes(key)))).toBe(true);
  const errors=[],mutations=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('request',request=>{if(!['GET','HEAD'].includes(request.method()))mutations.push(request.method()+' '+request.url());});
  await page.goto(baseURL+'sensor-qualification.html');
  await expect(page.locator('[data-sensor]')).toHaveCount(15);
  await expect(page.getByText('Synthetic demonstration')).toBeVisible();
  runSensorPython('services.lorawan.tests.integration_probe',['--state','0']);
  await expect(page.locator('[data-sensor="opening_01"] .state strong')).toHaveText('Closed');
  const start=Date.now();
  runSensorPython('services.lorawan.tests.integration_probe',['--state','1']);
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

  if(width===1340)await page.screenshot({path:testInfo.outputPath('sensors-simulation-1340x800.png')});
  await page.goto(baseURL+'#/ventilation');
  await expect(page.locator('.earthship-grid')).toBeVisible();
  await expect(page.locator('[data-ventilation-screen]')).toHaveCount(0);
  expect(errors).toEqual([]);expect(mutations).toEqual([]);expect(violations).toEqual([]);
 });
}
