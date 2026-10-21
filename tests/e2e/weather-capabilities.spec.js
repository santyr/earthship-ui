import {test,expect} from './fixture-test.js';
import {createServer} from 'vite';
import {capabilityFixture,CAPABILITY_NOW} from '../fixtures/weather-capabilities.js';

let server,baseURL;
test.use({hasTouch:true});
test.beforeAll(async()=>{
 server=await createServer({root:process.cwd(),logLevel:'error',server:{port:0,strictPort:false}});
 await server.listen();baseURL=server.resolvedUrls.local[0];
});
test.afterAll(async()=>{await server?.close();});

async function open(page,width,height,mode='ready'){
 await page.setViewportSize({width,height});
 await page.clock.install({time:new Date(CAPABILITY_NOW)});
 await page.addInitScript(()=>{window.EventSource=class {constructor(){setTimeout(()=>this.onopen?.({type:'open'}),0)}close(){}};});
 const detail={version:1,generatedAt:new Date(CAPABILITY_NOW).toISOString(),timezone:'America/Denver',days:[{
  date:'2026-10-21',label:'Today',summary:{highF:79,lowF:70,precipPct:0,weatherCode:1,pvKwh:4},
  hours:Array.from({length:10},(_,i)=>({at:`2026-10-21T${i+13}:00:00-06:00`,tempF:70+i,precipPct:0,radiationWm2:200,windMph:0,weatherCode:1})),
 }]};
 await page.route('**/config.json',route=>route.fulfill({json:{openhabUrl:'/fixture-openhab',apiToken:'fixture-only',staleBannerSeconds:90}}));
 await page.route('**/fixture-openhab/rest/items?*',route=>route.fulfill({json:[{name:'Forecast_10Day_JSON',state:JSON.stringify(detail),type:'String'}]}));
 await page.route('**/fixture-openhab/rest/things',route=>route.fulfill({json:[]}));
 await page.route('**/fixture-openhab/rest/persistence/items/**',route=>route.fulfill({json:{data:[],datapoints:0}}));
 const value=capabilityFixture();
 if(mode==='mean-only')for(const hour of value.groups.temperature.hours){hour.p10_c=null;hour.p90_c=null;hour.range_status='missing_quantiles';}
 if(mode==='zero')for(const hour of value.groups.temperature.hours){hour.p10_c=0;hour.p90_c=0;}
 if(mode==='stale')value.valid_until=value.generated_at;
 if(mode==='crossing')value.groups.temperature.hours[0].p10_c=50;
 await page.route('**/api/weather-capabilities',route=>route.fulfill(mode==='missing'?{status:503,json:{status:'unavailable'}}:{json:value}));
 const errors=[];
 page.on('console',message=>{
  if(message.type()!=='error'&&message.type()!=='warning')return;
  const url=message.location().url||baseURL;
  if(new URL(url).pathname.startsWith('/api/')&&message.text().includes('503'))return;
  errors.push(message.text());
 });
 await page.goto(baseURL+'#/weather');
 const opener=page.locator('[data-forecast-day]').first();await expect(opener).toBeVisible();await opener.tap();
 const dialog=page.getByRole('dialog',{name:/Today forecast/i});await expect(dialog).toBeVisible();
 await expect(dialog.locator('.weather-detail-chart svg')).toBeVisible();
 return {dialog,opener,errors};
}

async function bounded(dialog,width,height){
 const size=await dialog.evaluate(element=>{const b=element.getBoundingClientRect();return {left:b.left,top:b.top,right:b.right,bottom:b.bottom,sw:element.scrollWidth,cw:element.clientWidth,sh:element.scrollHeight,ch:element.clientHeight};});
 expect(size.left).toBeGreaterThanOrEqual(0);expect(size.top).toBeGreaterThanOrEqual(0);
 expect(size.right).toBeLessThanOrEqual(width);expect(size.bottom).toBeLessThanOrEqual(height);
 expect(size.sw).toBeLessThanOrEqual(size.cw);expect(size.sh).toBeLessThanOrEqual(size.ch);
}

for(const [width,height] of [[1340,800],[1280,720]]){
 test(`raw uncertainty remains distinct, accessible and expiring at ${width}x${height}`,async({page},testInfo)=>{
  const {dialog,opener,errors}=await open(page,width,height);
  await expect(dialog.getByText('WeatherNext p10–p90; local coverage not yet verified',{exact:true})).toBeVisible();
  await expect(dialog.getByText(/initialized 6h ago/)).toBeVisible();
  await expect(dialog.getByText('Raw p10–p90: 32°–50°',{exact:true})).toHaveCount(10);
  await expect(dialog.locator('.weather-detail-chart svg [fill="#a78bfa"]').first()).toBeVisible();
  await expect(dialog.locator('.hour-temp').first()).toHaveText('70°');
  await expect(dialog.getByText(/Raw median/)).toHaveCount(0);
  await bounded(dialog,width,height);
  await dialog.screenshot({path:testInfo.outputPath('raw-temperature.png')});
  await page.setViewportSize({width:width-40,height});await bounded(dialog,width-40,height);
  await page.keyboard.press('Escape');await expect(dialog).toBeHidden();await expect(opener).toBeFocused();
  await page.keyboard.press('Enter');await expect(dialog).toBeVisible();
  await page.clock.fastForward(3600001);
  await expect(dialog.getByText('WeatherNext p10–p90; local coverage not yet verified',{exact:true})).toHaveCount(0);
  await expect(dialog.locator('.weather-detail-chart svg [fill="#a78bfa"]')).toHaveCount(0);
  await expect(dialog.locator('.hour-temp').first()).toHaveText('70°');
  expect(errors).toEqual([]);
 });
 for(const mode of ['mean-only','zero','missing','stale','crossing']){
  test(`${mode} uncertainty preserves the forecast at ${width}x${height}`,async({page})=>{
   const {dialog,errors}=await open(page,width,height,mode);
   await expect(dialog.locator('.hour-temp').first()).toHaveText('70°');
   if(mode==='zero')await expect(dialog.getByText('Raw p10–p90: 32°–32°',{exact:true})).toHaveCount(10);
   else await expect(dialog.locator('.weather-detail-chart svg [fill="#a78bfa"]')).toHaveCount(0);
   if(mode==='mean-only'){
    await expect(dialog.getByText('Raw range unavailable',{exact:true})).toHaveCount(10);
    await expect(dialog.getByText('WeatherNext raw mean; percentile range unavailable',{exact:true})).toBeVisible();
    await expect(dialog.getByText('WeatherNext p10–p90; local coverage not yet verified',{exact:true})).toHaveCount(0);
   }
   await bounded(dialog,width,height);expect(errors).toEqual([]);
  });
 }
}
