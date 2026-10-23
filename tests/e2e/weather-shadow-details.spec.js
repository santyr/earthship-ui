import {test,expect} from './fixture-test.js';
import {createServer} from 'vite';
import {readFileSync} from 'node:fs';
const rainOriginal=JSON.parse(readFileSync(new URL('../fixtures/weather-rain-shadow.json',import.meta.url),'utf8'));
const marginalOriginal=JSON.parse(readFileSync(new URL('../fixtures/weather-marginal-shadow.json',import.meta.url),'utf8'));
test.use({hasTouch:true});
const NOW=Date.parse(rainOriginal.generated_at)+1000;let server,baseURL;
test.beforeAll(async()=>{server=await createServer({root:process.cwd(),logLevel:'error',server:{port:0,strictPort:false}});await server.listen();baseURL=server.resolvedUrls.local[0];});test.afterAll(async()=>{await server?.close();});
function move(value,delta){if(typeof value==='string'&&/^\d{4}-\d\d-\d\dT/.test(value)&&Number.isFinite(Date.parse(value)))return new Date(Date.parse(value)+delta).toISOString();if(Array.isArray(value))return value.map(v=>move(v,delta));if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,move(v,delta)]));return value;}
async function open(page,width,height,mode='ready'){
 await page.setViewportSize({width,height});await page.clock.install({time:new Date(NOW)});await page.addInitScript(()=>{window.EventSource=class{constructor(){setTimeout(()=>this.onopen?.({type:'open'}),0)}close(){}};});
 const detail={version:1,generatedAt:new Date(NOW).toISOString(),timezone:'America/Denver',days:[{date:'2026-10-22',label:'Today',summary:{highF:72,lowF:70,precipPct:0,weatherCode:1,pvKwh:1},hours:[21,22,23].map(h=>({at:`2026-10-22T${h}:00:00Z`,tempF:70,precipPct:0,radiationWm2:100,windMph:0,weatherCode:1}))}]};
 await page.route('**/config.json',r=>r.fulfill({json:{openhabUrl:'/fixture-openhab',apiToken:'fixture-only',staleBannerSeconds:90}}));await page.route('**/fixture-openhab/rest/items?*',r=>r.fulfill({json:[{name:'Forecast_10Day_JSON',state:JSON.stringify(detail),type:'String'}]}));await page.route('**/fixture-openhab/rest/things',r=>r.fulfill({json:[]}));await page.route('**/fixture-openhab/rest/persistence/items/**',r=>r.fulfill({json:{data:[],datapoints:0}}));
 const rain=structuredClone(rainOriginal),marginal=move(marginalOriginal,Date.parse(rain.generated_at)-Date.parse(marginalOriginal.generated_at));if(mode==='stale')rain.valid_until=rain.generated_at;if(mode==='malformed')rain.schema='unknown';
 if(mode==='zero-null'){for(const head of Object.keys(rain.rows[0].raw_means_mm))rain.rows[0].raw_means_mm[head]=0;rain.rows[0].raw_means_mm.imerg_tp_1hr=null;}
 let release;const ready=mode==='loading'?new Promise(resolve=>release=resolve):Promise.resolve();
 let online=mode!=='offline';const reads=[];await page.route('**/api/**',async r=>{const path=new URL(r.request().url()).pathname;reads.push(path);if(['/api/weather-rain-shadow','/api/weather-marginals'].includes(path)&&online){await ready;return r.fulfill({json:path.endsWith('rain-shadow')?rain:marginal});}return r.fulfill({status:503,json:{status:'unavailable'}});});
 await page.goto(baseURL+'#/weather');await page.locator('[data-forecast-day]').first().click();const dialog=page.getByRole('dialog',{name:/Today forecast/i});await expect(dialog).toBeVisible();await expect(dialog.locator('.hour-temp').first()).toHaveText('70°');return {dialog,reads,setOnline:v=>online=v,release:()=>release?.()};
}
for(const [width,height] of [[1340,800],[1280,720]])test(`experimental comparisons use disclosure and preserve the forecast ${width}x${height}`,async({page},info)=>{
 const {dialog,reads}=await open(page,width,height);expect(reads).not.toContain('/api/weather-rain-shadow');expect(reads).not.toContain('/api/weather-marginals');const summary=dialog.getByText('Local forecast comparisons · experimental',{exact:true});await expect(summary).toBeVisible();await summary.focus();await page.keyboard.press('Enter');
 await expect(dialog.getByText('Raw rain interval means',{exact:true})).toBeVisible();await expect(dialog.getByText(/No supported local rain probability/)).toBeVisible();await expect(dialog.getByText(/Training-only climatology/)).toBeVisible();await expect(dialog.getByText(/local coverage not yet verified/i).first()).toBeVisible();await expect(dialog.locator('.hour-temp').first()).toHaveText('70°');
 expect(reads).toContain('/api/weather-rain-shadow');expect(reads).toContain('/api/weather-marginals');await expect(dialog.locator('.forecast-shadow-body')).toBeVisible();await dialog.screenshot({path:info.outputPath('experimental-details.png')});
 const size=await dialog.evaluate(e=>({sw:e.scrollWidth,cw:e.clientWidth,sh:e.scrollHeight,ch:e.clientHeight}));expect(size.sw).toBeLessThanOrEqual(size.cw);expect(size.sh).toBeLessThanOrEqual(size.ch);
 await page.setViewportSize({width:width-40,height});await expect(summary).toBeVisible();await page.keyboard.press('Escape');await expect(dialog).toBeHidden();
});
for(const mode of ['stale','malformed','offline'])test(`${mode} optional comparison preserves raw forecast`,async({page})=>{const {dialog}=await open(page,1280,720,mode);await dialog.getByText('Local forecast comparisons · experimental',{exact:true}).click();await expect(dialog.getByText('Rain interval comparison unavailable',{exact:true})).toBeVisible();await expect(dialog.locator('.hour-temp').first()).toHaveText('70°');});
test('offline and reconnect do not keep a withdrawn optional report',async({page})=>{const {dialog,setOnline}=await open(page,1280,720);await dialog.getByText('Local forecast comparisons · experimental',{exact:true}).click();await expect(dialog.getByText('Raw rain interval means',{exact:true})).toBeVisible();setOnline(false);await page.clock.fastForward(31000);await expect(dialog.getByText('Rain interval comparison unavailable',{exact:true})).toBeVisible();setOnline(true);await page.clock.fastForward(31000);await expect(dialog.getByText('Raw rain interval means',{exact:true})).toBeVisible();});

test('loading optional originals never replaces the primary forecast',async({page})=>{
 const {dialog,release}=await open(page,1280,720,'loading');
 await dialog.locator('.forecast-verification summary').tap();
 await expect(dialog.getByText('Rain interval comparison unavailable',{exact:true})).toBeVisible();
 await expect(dialog.locator('.hour-temp').first()).toHaveText('70°');
 release();
 await expect(dialog.getByText('Raw rain interval means',{exact:true})).toBeVisible();
 await expect(dialog.locator('.hour-temp').first()).toHaveText('70°');
});
test('zero and missing rain heads stay distinct with touch-sized controls',async({page})=>{
 const {dialog}=await open(page,1280,720,'zero-null');
 const summary=dialog.locator('.forecast-verification summary');
 await summary.tap();
 await expect(dialog.locator('dl div').filter({has:page.locator('dt',{hasText:'Total'})}).locator('dd')).toHaveText('0.00″');
 await expect(dialog.locator('dl div').filter({has:page.locator('dt',{hasText:'IMERG'})}).locator('dd')).toHaveText('unavailable');
 const select=dialog.getByRole('combobox',{name:'Rain comparison interval'});
 for(const control of [summary,select])expect((await control.boundingBox()).height).toBeGreaterThanOrEqual(44);
 await expect(dialog.getByText(/No supported local rain probability/)).toBeVisible();
});
test('closing experimental details stops polling and reopening starts fresh reads',async({page})=>{
 const {dialog,reads}=await open(page,1280,720);
 const summary=dialog.locator('.forecast-verification summary');
 await summary.tap();await expect(dialog.getByText('Raw rain interval means',{exact:true})).toBeVisible();
 await summary.tap();await expect(dialog.locator('.forecast-shadow-body')).toHaveCount(0);
 const count=()=>reads.filter(path=>['/api/weather-rain-shadow','/api/weather-marginals'].includes(path)).length;
 const before=count();await page.clock.fastForward(61000);expect(count()).toBe(before);
 await summary.tap();await expect(dialog.getByText('Raw rain interval means',{exact:true})).toBeVisible();expect(count()).toBeGreaterThan(before);
});
