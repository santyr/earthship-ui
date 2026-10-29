import {test,expect} from './fixture-test.js';
import {createServer} from './fixture-server.js';
import {readFileSync} from 'node:fs';
const original=JSON.parse(readFileSync(new URL('../fixtures/weather-production.json',import.meta.url),'utf8'));
let server,baseURL;
test.beforeAll(async()=>{server=await createServer({root:process.cwd(),logLevel:'error',server:{port:0,strictPort:false}});await server.listen();baseURL=server.resolvedUrls.local[0]});
test.afterAll(async()=>await server?.close());
async function open(page,width,height,mode='ready'){
 await page.setViewportSize({width,height});await page.clock.install({time:new Date(Date.parse(original.published_at)+1000)});
 await page.addInitScript(()=>{window.EventSource=class{constructor(){setTimeout(()=>this.onopen?.({type:'open'}),0)}close(){}}});
 const point=(at,kind)=>original.rows.find(r=>r.kind===kind&&r.target_end===at);
 const hours=original.rows.filter(r=>r.kind==='temperature').slice(0,12).map(r=>{
  const wind=point(r.target_end,'wind');return {at:new Date(Date.parse(r.target_end)-7*3600000).toISOString().slice(0,-1)+'-07:00',tempF:r.local.point_estimate*1.8+32,windMph:2.2369362921,...(wind?{windMeanMph:wind.local.point_estimate*2.2369362921}:{}),radiationWm2:100,precipIn:.01};
 });
 const detail={version:3,provider:'weathernext3',providerStatus:'AVAILABLE',generatedAt:original.generated_at,timezone:'America/Denver',
  productionModel:{issueSha256:original.issue_sha256,status:'MIXED_WITH_RAW_FALLBACK',localCoverageQualified:false,probabilityClaim:false,temperatureStatistic:'model_point_with_declared_raw_fallback',windStatistic:'native_instantaneous_with_separate_local_hour_mean'},
  days:[{date:'2026-01-16',label:'Today',summary:{highF:54,lowF:53,precipPct:null,weatherCode:null,pvKwh:null,temperatureScope:'remaining',temperatureStatistic:'extrema_of_hourly_point_forecasts'},hours}]};
 await page.route('**/config.json',r=>r.fulfill({json:{openhabUrl:'/fixture-openhab',apiToken:'fixture-only',staleBannerSeconds:90}}));
 await page.route('**/fixture-openhab/rest/items?*',r=>r.fulfill({json:[{name:'Forecast_10Day_JSON',state:JSON.stringify(detail),type:'String'}]}));
 await page.route('**/fixture-openhab/rest/things',r=>r.fulfill({json:[]}));
 await page.route('**/fixture-openhab/rest/persistence/items/**',r=>r.fulfill({json:{data:[],datapoints:0}}));
 const view=structuredClone(original);if(mode==='different-issue')view.issue_sha256='f'.repeat(64);
 await page.route('**/api/weather-production',r=>r.fulfill(mode==='missing'?{status:503,json:{status:'unavailable'}}:{json:view}));
 const requests=[];page.on('request',r=>{const p=new URL(r.url()).pathname;if(p.startsWith('/api/weather-'))requests.push(p)});
 const chartErrors=[];page.on('console',m=>{if(m.type()==='error'&&!m.text().includes('503'))chartErrors.push(m.text())});
 await page.goto(baseURL+'#/weather');const opener=page.locator('[data-forecast-day]').first();await expect(opener).toBeVisible();await opener.click();
 const dialog=page.getByRole('dialog',{name:/Today forecast/i});await expect(dialog).toBeVisible();await expect(dialog.locator('.weather-detail-chart svg')).toBeVisible();
 expect(requests).not.toContain('/api/weather-production');
 await dialog.getByText('Production forecast ranges · experimental',{exact:true}).click();
 return {dialog,requests,chartErrors};
}
for(const [width,height] of [[1340,800],[1280,720]])test(`confirmed production ranges, lazy transport and cleanup at ${width}x${height}`,async({page},testInfo)=>{
 const {dialog,requests,chartErrors}=await open(page,width,height);
 await expect(dialog.getByText('Active production forecast · experimental',{exact:true})).toBeVisible();
 await expect(dialog.getByText(/Local temperature mean/)).toBeVisible();
 expect(requests.filter(p=>p==='/api/weather-production')).toHaveLength(1);
 expect(requests).not.toContain('/api/weather-marginals');expect(requests).not.toContain('/api/weather-rain-shadow');
 const row=original.rows.find(r=>r.kind==='wind');await dialog.getByRole('combobox',{name:'Production forecast hour'}).selectOption(row.target_end);
 await expect(dialog.getByText(/Local station hourly wind mean/)).toBeVisible();
 await expect.poll(async()=>dialog.locator('.weather-detail-chart').evaluate(el=>Math.abs(el.clientHeight-el.querySelector('svg').getBoundingClientRect().height))).toBeLessThanOrEqual(1);
 await dialog.screenshot({path:testInfo.outputPath('production-ranges.png')});
 await dialog.locator('.production-forecast-details').evaluate(el=>{el.scrollTop=el.scrollHeight});
 await expect(dialog.locator('.production-forecast-details').getByText(/Local interval coverage is unverified/)).toBeVisible();
 await dialog.screenshot({path:testInfo.outputPath('production-ranges-support.png')});
 const bounds=await dialog.evaluate(el=>({w:el.scrollWidth,cw:el.clientWidth,h:el.scrollHeight,ch:el.clientHeight}));expect(bounds.w).toBeLessThanOrEqual(bounds.cw);expect(bounds.h).toBeLessThanOrEqual(bounds.ch);
 await dialog.getByText('Production forecast ranges · experimental',{exact:true}).click();const count=requests.filter(p=>p==='/api/weather-production').length;
 await page.clock.fastForward(31000);expect(requests.filter(p=>p==='/api/weather-production')).toHaveLength(count);expect(chartErrors).toEqual([]);
});
for(const mode of ['different-issue','missing'])test(`optional ${mode} ranges preserve actual core points`,async({page})=>{
 const {dialog,chartErrors}=await open(page,1280,720,mode);await expect(dialog.getByRole('status').filter({hasText:'Production ranges unavailable'})).toBeVisible();
 await expect(dialog.locator('.hour-temp').first()).toHaveText('54°');await expect(dialog.locator('.weather-detail-chart svg')).toBeVisible();expect(chartErrors).toEqual([]);
});
