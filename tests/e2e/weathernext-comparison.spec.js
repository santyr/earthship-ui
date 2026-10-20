import { expect, test } from './fixture-test.js';
import { readFileSync } from 'node:fs';

const fixture=JSON.parse(readFileSync(new URL('../fixtures/weathernext-shadow-v2.json',import.meta.url),'utf8'));
const targets=[{name:'tablet',width:1340,height:800},{name:'laptop',width:1280,height:720}];
let server,baseURL;
test.beforeAll(async()=>{
  const {createServer}=await import('vite');
  server=await createServer({root:process.cwd(),logLevel:'error',server:{host:'127.0.0.1',port:0,strictPort:false}});
  await server.listen();baseURL=server.resolvedUrls.local[0];
});
test.afterAll(async()=>{await server?.close();});
for(const target of targets){
  test(`comparison stays inside the forecast tile and is clickable on ${target.name}`,async({page})=>{
    await page.setViewportSize({width:target.width,height:target.height});
    await page.addInitScript(()=>{
      const NativeDate=Date,frozen=Date.parse('2026-01-01T00:31:00Z');
      class FixtureDate extends NativeDate{constructor(...args){super(...(args.length?args:[frozen]));}static now(){return frozen;}}
      window.Date=FixtureDate;
      window.EventSource=class{constructor(){setTimeout(()=>this.onopen?.({type:'open'}),0);}close(){}};
    });
    await page.route('**/config.json',route=>route.fulfill({json:{openhabUrl:'/fixture-openhab',apiToken:'',staleBannerSeconds:90}}));
    await page.route('**/fixture-openhab/rest/**',route=>{
      const path=new URL(route.request().url()).pathname;
      const raw=JSON.stringify(fixture);
      const items=['Forecast_Provider_Status_JSON','Forecast_Comparison_JSON','Forecast_Local_Shadow_JSON'].map(name=>({name,state:raw,type:'String'}));
      return route.fulfill({json:path.endsWith('/items')?items:[]});
    });
    await page.goto(baseURL+'#/weather',{waitUntil:'domcontentloaded'});
    const button=page.getByRole('button',{name:'Local correction · shadow',exact:true});
    await expect(button).toBeVisible();
    const entry=await button.boundingBox(),tile=await page.locator('.daily-cell').boundingBox();
    expect(entry.y).toBeGreaterThanOrEqual(tile.y);
    expect(entry.x).toBeGreaterThanOrEqual(tile.x);
    expect(entry.x+entry.width).toBeLessThanOrEqual(tile.x+tile.width+1);
    await button.click({timeout:5000});
    const dialog=page.getByRole('dialog',{name:'WeatherNext local correction'});
    await expect(dialog.getByRole('columnheader',{name:'Raw WeatherNext',exact:true})).toBeVisible();
    const bounds=await dialog.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);expect(bounds.y).toBeGreaterThanOrEqual(0);
    expect(bounds.x+bounds.width).toBeLessThanOrEqual(target.width+1);
    expect(bounds.y+bounds.height).toBeLessThanOrEqual(target.height+1);
    await dialog.getByRole('button',{name:'Close forecast details'}).click();
    await expect(dialog).toHaveCount(0);await expect(button).toBeFocused();
  });
}
