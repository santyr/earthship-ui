import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {homedir} from 'node:os';
import {resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {parseTerrainDaylight} from './terrainDaylight.js';
import {localDateAt} from './forecastDetail.js';
import {HOUSEHOLD_TIMEZONE} from '../site.js';
const execute=promisify(execFile);
/** Fixed, bounded, original-cache projection. No native acquisition or mutations. */
async function project(){
 const root=resolve(process.env.EARTHSHIP_UI_SOLAR_ROOT||fileURLToPath(new URL('../../../',import.meta.url)));
 const {stdout}=await execute('/usr/bin/python3',[resolve(root,'scripts/run-household-job.py'),'--production','--minimum-mib','256','--preferred-mib','512','--tasks','24','--seconds','15','--','/usr/bin/python3',resolve(root,'openhab/scripts/site_daylight.py'),'--geometry-root',resolve(homedir(),'.local/state/earthship-weather/daily-pv/geometry'),'--horizon',resolve(root,'openhab/household-solar-horizon.json')],{cwd:root,timeout:18000,maxBuffer:16384,encoding:'utf8',env:{...process.env,PYTHONPATH:resolve(root,'openhab/scripts'),PYTHONDONTWRITEBYTECODE:'1',OPENBLAS_NUM_THREADS:'1',OMP_NUM_THREADS:'1',MKL_NUM_THREADS:'1'}});
 return stdout;
}
export function terrainDaylightPlugin({load=project,now=Date.now}={}){
 let value=null,until=0,day=null,pending=null;
 async function current(){
  const today=localDateAt(now(),HOUSEHOLD_TIMEZONE);
  if(day===today&&now()<until)return value&&parseTerrainDaylight(value,{nowMs:now()})?value:null;
  if(!pending){
   pending=(async()=>{
    try{const raw=await load();const report=parseTerrainDaylight(raw,{nowMs:now()});if(!report)throw Error('unavailable');value=JSON.stringify(report);until=Math.min(now()+300000,Date.parse(report.validUntil));day=report.day;}
    catch{value=null;until=now()+30000;day=localDateAt(now(),HOUSEHOLD_TIMEZONE);}
   })().finally(()=>{pending=null;});
  }
  await pending;return value&&parseTerrainDaylight(value,{nowMs:now()})?value:null;
 }
 const attach=server=>{server.middlewares.use(async(req,res,next)=>{
  let url;try{url=new URL(req.url||'/','http://localhost');}catch{return next();}
  if(url.pathname!=='/api/terrain-daylight')return next();
  res.setHeader('Content-Type','application/json');res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='GET'){res.setHeader('Allow','GET');res.writeHead(405).end('{"status":"unavailable"}');return;}
  if(url.search){res.writeHead(400).end('{"status":"unavailable"}');return;}
  const raw=await current();if(res.destroyed)return;
  res.writeHead(raw?200:503).end(raw??'{"status":"unavailable"}');
 });};
 return {name:'terrain-daylight',configureServer:attach,configurePreviewServer:attach};
}
