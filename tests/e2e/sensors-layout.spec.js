import {expect,test} from '@playwright/test';
import {createServer} from 'vite';
import {execFileSync} from 'node:child_process';
import {mkdirSync} from 'node:fs';
const enabled=process.env.SENSOR_INTEGRATION==='1';
test.skip(!enabled,'requires the isolated sensor Compose stack');
let server;
test.beforeAll(async()=>{
 process.env.OPENHAB_PROXY_TARGET='http://127.0.0.1:18084';
 server=await createServer({server:{host:'127.0.0.1',port:5194,strictPort:true}});await server.listen();
});
test.afterAll(async()=>{await server?.close();});
for(const [width,height] of [[1340,800],[1280,720]]) {
 test(`sensor dashboard ${width}x${height}: real OpenHAB SSE, transitions and bounded layout`,async({page})=>{
  await page.setViewportSize({width,height});
  await page.route('**/config.json',route=>route.fulfill({json:{openhabUrl:'',apiToken:'',staleBannerSeconds:90}}));
  const privateResponse=await page.request.get('http://127.0.0.1:5194/.superpowers/lorawan-private/ingest.json');
  expect(privateResponse.status()).toBe(403);
  await page.goto('http://127.0.0.1:5194/#/ventilation');
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
 });
}
