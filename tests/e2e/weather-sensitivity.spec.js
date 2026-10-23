import {test,expect} from './fixture-test.js';
import {createServer} from 'vite';
import {sensitivity,nowMs} from '../fixtures/weather-sensitivity.js';
let server,baseURL;
test.beforeAll(async()=>{server=await createServer({root:process.cwd(),logLevel:'error',server:{port:0,strictPort:false}});await server.listen();baseURL=server.resolvedUrls.local[0];});
test.afterAll(async()=>{await server?.close();});
async function open(page,width,height,value=sensitivity()){
 await page.clock.install({time:new Date(nowMs)});await page.setViewportSize({width,height});
 await page.route('**/config.json',r=>r.fulfill({json:{openhabUrl:'/fixture-openhab',apiToken:'fixture-only',staleBannerSeconds:90}}));
 await page.route('**/fixture-openhab/rest/items?*',r=>r.fulfill({json:[]}));
 await page.route('**/fixture-openhab/rest/events?*',r=>r.fulfill({contentType:'text/event-stream',body:''}));
 await page.route('**/api/weather-sensitivity',r=>value===null?r.fulfill({status:503,json:{status:'unavailable'}}):r.fulfill({json:value}));
 await page.goto(`${baseURL}#/earthship`,{waitUntil:'domcontentloaded'});await expect(page.locator('.earthship-grid')).toBeVisible();
}
for(const [width,height] of [[1340,800],[1280,720]])test(`three cases are readable by keyboard at ${width}x${height}`,async({page})=>{
 await open(page,width,height);const detail=page.locator('.weather-sensitivity details'),summary=detail.locator('summary');
 await expect(detail).not.toHaveAttribute('open');await summary.focus();await summary.press('Enter');await expect(detail).toHaveAttribute('open','');
 await expect(detail.locator('tbody tr')).toHaveCount(3);await expect(detail).toContainText('PV before electrical correction');await expect(detail).toContainText('10.00 kWh');
 await expect(detail).not.toContainText('Source initialized');await expect(detail).not.toContainText('p10');
 const hour=page.getByLabel('Sensitivity forecast hour');await hour.focus();await hour.press('ArrowLeft');await expect(detail.locator('caption')).toContainText('hour 23');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.clock.setSystemTime(new Date(nowMs+2*3600000));await page.clock.fastForward(1000);await expect(detail).toContainText('Weather sensitivity unavailable');await expect(detail.locator('table')).toHaveCount(0);
});
test('unavailable sensitivity preserves the rest of the Earthship console',async({page})=>{
 await open(page,1280,720,null);await page.locator('.weather-sensitivity summary').click();await expect(page.locator('.weather-sensitivity')).toContainText('Weather sensitivity unavailable');await expect(page.locator('.earthship-grid')).toBeVisible();
});
test('zero solar is displayed as zero without invented temperatures',async({page})=>{
 const v=sensitivity();for(const row of v.cases){row.raw_potential_pv_kwh=0;row.modeled_captured_pv_kwh=0;for(const p of row.trajectory)p.cumulative_raw_pv_kwh=0;}
 await open(page,1340,800,v);await page.locator('.weather-sensitivity summary').click();await expect(page.locator('.weather-sensitivity tbody tr')).toHaveCount(3);await expect(page.locator('.weather-sensitivity tbody tr').first()).toContainText('0.00 kWh');
});
