import {test,expect} from './fixture-test.js';
import {createServer} from 'vite';
import {readFileSync} from 'node:fs';
let server,baseURL;const NOW=Date.parse('2026-10-22T20:30:00Z');
test.beforeAll(async()=>{server=await createServer({root:process.cwd(),logLevel:'error',server:{port:0,strictPort:false}});await server.listen();baseURL=server.resolvedUrls.local[0];});
test.afterAll(async()=>{await server?.close();});
function report(amount,complete=false){
 const at=new Date(NOW).toISOString(),total='AmbientWeatherWS2902A_RainFallTotal';
 const period=(start,until)=>({start,end:at,periodValidUntil:until,value:complete?amount:null,lower:complete?amount:null,upper:complete?amount:null,partial_lower_bound:amount,recorded_in:amount,unit:'in',method:'receipt_counter_boundary_brackets/v1'});
 return {schema:'earthship-station-ingestion/v2',generatedAt:at,fields:{[total]:{value:100,role:'outdoor',status:'fresh',receivedAt:at,validUntil:new Date(NOW+120000).toISOString()}},flat:{[total]:100},rain:{schema:'earthship-station-rain-products/v2',recordedMethod:'sum_accepted_continuous_receipt_increments/v1',status:'fresh',products:{day:period('2026-10-22T06:00:00Z','2026-10-23T06:00:00Z'),week:period('2026-10-18T06:00:00Z','2026-10-25T06:00:00Z'),month:period('2026-10-01T06:00:00Z','2026-11-01T06:00:00Z')}}};
}
async function open(page,route,width,height,amount,complete=false,original=null){
 await page.setViewportSize({width,height});await page.clock.install({time:new Date(original ? original.generatedAt : NOW)});
 await page.addInitScript(()=>{window.EventSource=class {constructor(){setTimeout(()=>this.onopen?.({type:'open'}),0)}close(){}};});
 const payload=original ?? report(amount,complete);
 await page.route('**/config.json',r=>r.fulfill({json:{openhabUrl:'/fixture-openhab',apiToken:'fixture-only',staleBannerSeconds:90}}));
 await page.route('**/fixture-openhab/rest/items?*',r=>r.fulfill({json:[{name:'WeatherStation_Quality_JSON',state:JSON.stringify(payload),type:'String'},...['RainFallDay','RainFallWeek'].map(k=>({name:'AmbientWeatherWS2902A_'+k,state:'99.99',type:'Number'}))]}));
 await page.route('**/fixture-openhab/rest/things',r=>r.fulfill({json:[]}));
 await page.route('**/fixture-openhab/rest/persistence/items/**',r=>r.fulfill({json:{data:[],datapoints:0}}));
 await page.route('**/api/**',r=>r.fulfill({status:503,json:{status:'unavailable'}}));
 await page.goto(baseURL+'#/'+route);await expect(page.locator('.rain-cell')).toBeVisible();return page.locator('.rain-cell');
}
async function readableText(tile){
 const bounds=await tile.evaluate(e=>{
  const outer=e.getBoundingClientRect();return [...e.querySelectorAll('.value,.footer')].map(el=>{
   const range=document.createRange();range.selectNodeContents(el);const b=range.getBoundingClientRect();
   return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,outer:{left:outer.left,right:outer.right,top:outer.top,bottom:outer.bottom}};
  });
 });
 for(const b of bounds){expect(b.left).toBeGreaterThanOrEqual(b.outer.left+3);expect(b.right).toBeLessThanOrEqual(b.outer.right-3);expect(b.top).toBeGreaterThanOrEqual(b.outer.top);expect(b.bottom).toBeLessThanOrEqual(b.outer.bottom);}
}
for(const [width,height] of [[1340,800],[1280,720]])for(const route of ['home','weather']){
 test(`partial day and week rainfall stay visible at ${route} ${width}x${height}`,async({page},info)=>{
  const tile=await open(page,route,width,height,.03);if(route==='home'){await expect(tile).toContainText('0.03″ / 52 gal');await expect(tile).toContainText('Week 0.03″ / 52 gal');await expect(tile).not.toContainText('partial');await expect(tile).not.toContainText('≥');}else{await expect(tile).toContainText('≥0.03″');await expect(tile).toContainText(/partial/i);await expect(tile).toContainText(/wk ≥0.03″/);await expect(tile).not.toContainText('gal');}await expect(tile).not.toContainText('99.99');
  const size=await tile.evaluate(e=>({sw:e.scrollWidth,cw:e.clientWidth}));expect(size.sw).toBeLessThanOrEqual(size.cw);await readableText(tile);
  await tile.screenshot({path:info.outputPath('rain-partial.png')});
  await page.clock.fastForward(91000);await expect(tile).not.toContainText('0.03');await expect(tile).toContainText('—');
 });
}
test('recorded zero keeps Home numeric without a partial label',async({page})=>{const tile=await open(page,'home',1280,720,0);await expect(tile).toContainText('0.00″ / 0 gal');await expect(tile).not.toContainText('partial');});
test('complete day/week totals keep their existing meaning',async({page})=>{const tile=await open(page,'home',1280,720,.1,true);await expect(tile).toContainText('0.10″');await expect(tile).toContainText('Week 0.10″');await expect(tile).not.toContainText('partial');await expect(tile).not.toContainText('≥');});

for(const amount of [10.03,100000])test(`larger recorded totals and gallons remain fully readable: ${amount}`,async({page})=>{
 const tile=await open(page,'home',1280,720,amount);await expect(tile).toContainText(`${amount.toFixed(2)}″`);await expect(tile).toContainText('gal');await readableText(tile);
});

for(const [width,height] of [[1340,800],[1280,720]])test(`saved actual OpenHAB rain receipts show inches and harvested gallons ${width}`,async({page})=>{
 const {report}=JSON.parse(readFileSync('tests/fixtures/ws2902-station-openhab-20261022.json','utf8'));
 const tile=await open(page,'home',width,height,0,false,report);
 await expect(tile).toContainText('0.08″ / 140 gal');await expect(tile).toContainText('Week 0.22″ / 384 gal');
 await expect(tile).not.toContainText('partial');await expect(tile).not.toContainText('≥');await readableText(tile);
});
