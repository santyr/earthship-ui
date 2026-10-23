import { parseCalibratedEnergy, parseCalibratedPerformance } from './calibratedEnergy.js';
import { parsePvPerformance } from '../energy/pvPerformance.js';
import { parseDailyPvPotential } from '../energy/dailyPvPotential.js';
import { parseChronologicalSummary } from './chronology.js';
import { constants } from 'node:fs';
import {createHash} from 'node:crypto';
import { open, realpath, stat, lstat } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { homedir } from 'node:os';
import { OBSERVATION_MAX_BYTES, parseHouseholdObservation } from './observation.js';
import { parseCapturedPvPerformance } from './capturedPvPerformance.js';
import { parseBatteryPerformance } from './batteryPerformance.js';
import { parseEnergyObservation, parseEnergyPerformance } from './energyObservation.js';
import { parseProfiledObservation, parseProfiledPerformance } from './profiledObservation.js';
import {parseWeatherCapabilities,MAX_CAPABILITY_BYTES} from '../weather/capabilityForecast.js';
import {parseWeatherMarginals,validateMarginalEmission,MAX_MARGINAL_BYTES,MAX_MARGINAL_EMISSION_BYTES} from '../weather/marginalForecast.js';
import {parseProductionWeather,validateProductionViewReceipt,MAX_PRODUCTION_BYTES,MAX_PRODUCTION_RECEIPT_BYTES} from '../weather/productionForecast.js';
import {parseWeatherSensitivity,validateSensitivityReceipt,MAX_SENSITIVITY_BYTES,MAX_SENSITIVITY_RECEIPT_BYTES} from '../weather/sensitivity.js';
import {parseRainShadow,validateRainEmission,MAX_RAIN_BYTES,MAX_RAIN_EMISSION_BYTES} from '../weather/rainForecast.js';

// Preserve Vite's default sensitive-file exclusions and add private agent and
// receipt staging. Filesystem permissions alone do not constrain the web server.
export const HOUSEHOLD_FS_DENY = ['.env', '.env.*', '*.{crt,pem,key,p12,pfx,cer,der}', '.npmrc', '.yarnrc.yml',
  '**/.git/**', '**/.superpowers/**', '**/.codex/**', '**/.aws/**'];

function ownedFile(info,maximumBytes) {
  return info.isFile() && info.uid === process.getuid() && (info.mode & 0o777) === 0o600
    && info.nlink === 1 && info.size <= maximumBytes;
}
function same(a, b) {
  return ['dev', 'ino', 'mode', 'uid', 'nlink', 'size', 'mtimeMs', 'ctimeMs'].every(key => a[key] === b[key]);
}
async function readObservation(path, nowMs, validate = parseHouseholdObservation, maximumBytes = OBSERVATION_MAX_BYTES, onBytes = null) {
  if (resolve(path) !== path || await realpath(path) !== path) throw new Error('unavailable');
  const parent = await stat(dirname(path));
  if (!parent.isDirectory() || parent.uid !== process.getuid() || (parent.mode & 0o777) !== 0o700) throw new Error('unavailable');
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const original = await handle.stat();
    if (!ownedFile(original,maximumBytes)) throw new Error('unavailable');
    const bytes = Buffer.alloc(maximumBytes + 1);
    let length = 0;
    while (length < bytes.length) {
      const result = await handle.read(bytes, length, bytes.length - length, null);
      if (!result.bytesRead) break;
      length += result.bytesRead;
    }
    if (length > maximumBytes || length !== original.size
      || !same(original, await handle.stat()) || !same(original, await lstat(path))
      || !same(parent, await stat(dirname(path))) || await realpath(path) !== path) throw new Error('unavailable');
    if(onBytes)onBytes(bytes.subarray(0,length));
    const raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, length));
    if (!validate(raw, { nowMs })) throw new Error('unavailable');
    return raw;
  } finally { await handle.close(); }
}

/** Fixed file transport only: no receipt replay, model execution or command path. */
export function householdObservationPlugin({
  cachePath = process.env.HOUSEHOLD_OBSERVATION_CACHE || resolve(homedir(), '.local/state/household-intel/observation.json'),
  chronologicalCachePath = resolve(homedir(), '.local/state/household-intel/chronological-summary.json'),
  batteryCachePath = resolve(homedir(), '.local/state/household-intel/battery-performance.json'),
  energyCachePath = resolve(homedir(), '.local/state/household-intel/energy-observation.json'),
  energyPerformanceCachePath = resolve(homedir(), '.local/state/household-intel/energy-performance.json'),
  calibratedCachePath = resolve(homedir(), '.local/state/household-intel/calibrated-energy-observation.json'),
  calibratedPerformanceCachePath = resolve(homedir(), '.local/state/household-intel/calibrated-energy-performance.json'),
  profiledCachePath = resolve(homedir(), '.local/state/household-intel/profiled-energy-observation.json'),
  profiledPerformanceCachePath = resolve(homedir(), '.local/state/household-intel/profiled-energy-performance.json'),
  capturedPvCachePath = resolve(homedir(), '.local/state/household-intel/captured-pv-performance.json'),
  pvPerformanceCachePath = resolve(homedir(), '.local/state/household-intel/daily-pv-performance.json'),
  dailyPvCachePath = resolve(homedir(), '.local/state/household-intel/daily-pv-potential.json'),
  weatherSensitivityPath = resolve(homedir(), '.local/state/earthship-weather/shadow/google-local-v2/scenario-advisory.json'),
  weatherProductionPath = resolve(homedir(), '.local/state/earthship-weather/shadow/google-local-v2/production-forecast.json'),
  weatherRainPath = resolve(homedir(), '.local/state/earthship-weather/shadow/google-local-v2/rain-candidates.json'),
  weatherMarginalsPath = resolve(homedir(), '.local/state/earthship-weather/shadow/google-local-v2/marginal-candidates.json'),
  weatherCapabilitiesPath = resolve(homedir(), '.local/state/earthship-weather/shadow/google-local-v2/weather-capabilities.json'),
  now = Date.now,
} = {}) {
  const attach = server => { server.middlewares.use(async (req, res, next) => {
    let url;
    try { url = new URL(req.url || '/', 'http://localhost'); } catch { return next(); }
    const route = {
      '/api/weather-sensitivity': [weatherSensitivityPath, (raw,options)=>parseWeatherSensitivity(raw,options).state==='ready', MAX_SENSITIVITY_BYTES],
      '/api/weather-production': [weatherProductionPath, (raw,options)=>parseProductionWeather(raw,options).state==='ready', MAX_PRODUCTION_BYTES],
      '/api/weather-rain-shadow': [weatherRainPath, (raw,options)=>parseRainShadow(raw,options).state==='ready', MAX_RAIN_BYTES],
      '/api/weather-marginals': [weatherMarginalsPath, (raw,options)=>parseWeatherMarginals(raw,options).state==='ready', MAX_MARGINAL_BYTES],
      '/api/weather-capabilities': [weatherCapabilitiesPath, (raw,options)=>parseWeatherCapabilities(raw,options).state==='ready', MAX_CAPABILITY_BYTES],
      '/api/daily-pv-performance': [pvPerformanceCachePath, parsePvPerformance],
      '/api/daily-pv-potential': [dailyPvCachePath, parseDailyPvPotential],
      '/api/household-chronological-summary': [chronologicalCachePath, parseChronologicalSummary],
      '/api/household-observation': [cachePath, parseHouseholdObservation],
      '/api/household-captured-pv-performance': [capturedPvCachePath, parseCapturedPvPerformance],
      '/api/household-battery-performance': [batteryCachePath, parseBatteryPerformance],
      '/api/household-energy-observation': [energyCachePath, parseEnergyObservation],
      '/api/household-energy-performance': [energyPerformanceCachePath, parseEnergyPerformance],
      '/api/household-calibrated-energy-observation': [calibratedCachePath, parseCalibratedEnergy],
      '/api/household-calibrated-energy-performance': [calibratedPerformanceCachePath, parseCalibratedPerformance],
      '/api/household-profiled-energy-observation': [profiledCachePath, parseProfiledObservation],
      '/api/household-profiled-energy-performance': [profiledPerformanceCachePath, parseProfiledPerformance],
    }[url.pathname];
    if (!route) return next();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (req.method !== 'GET') { res.setHeader('Allow', 'GET'); res.writeHead(405).end('{"status":"unavailable"}'); return; }
    if (url.search) { res.writeHead(400).end('{"status":"unavailable"}'); return; }
    try {
      const at=now();let cacheBytesSha256=null;
      const raw = await readObservation(route[0], at, route[1], route[2],['/api/weather-marginals','/api/weather-rain-shadow','/api/weather-production','/api/weather-sensitivity'].includes(url.pathname)?bytes=>{cacheBytesSha256=createHash('sha256').update(bytes).digest('hex')}:null);
      if(url.pathname==='/api/weather-rain-shadow'){
        const view=parseRainShadow(raw,{nowMs:at});
        const receipt=resolve(dirname(weatherRainPath),'rain-emissions','view-'+view.reportSha256+'.json');
        await readObservation(receipt,at,(emission,options)=>validateRainEmission(emission,{view,cacheBytesSha256,...options}),MAX_RAIN_EMISSION_BYTES);
      }
      if(url.pathname==='/api/weather-marginals'){
        const view=parseWeatherMarginals(raw,{nowMs:at});
        const receipt=resolve(dirname(weatherMarginalsPath),'marginal-emissions',view.issueSha256+'.json');
        await readObservation(receipt,at,(emission,options)=>validateMarginalEmission(emission,{view,cacheBytesSha256,...options}),MAX_MARGINAL_EMISSION_BYTES);
      }
      if(url.pathname==='/api/weather-production'){
        const view=parseProductionWeather(raw,{nowMs:at});
        const receipt=resolve(dirname(weatherProductionPath),'production-views','view-'+view.reportSha256+'.json');
        await readObservation(receipt,at,(receipt,options)=>validateProductionViewReceipt(receipt,{view,cacheBytesSha256,...options}),MAX_PRODUCTION_RECEIPT_BYTES);
      }
      if(url.pathname==='/api/weather-sensitivity'){
        const view=parseWeatherSensitivity(raw,{nowMs:at});
        const receipt=resolve(dirname(weatherSensitivityPath),'scenario-reports','view-'+view.reportSha256+'.json');
        await readObservation(receipt,at,(receipt,options)=>validateSensitivityReceipt(receipt,{view,cacheBytesSha256,...options}),MAX_SENSITIVITY_RECEIPT_BYTES);
      }
      res.writeHead(200).end(raw);
    }
    catch { if (!res.headersSent) res.writeHead(503); res.end('{"status":"unavailable"}'); }
  }); };
  return { name: 'household-observation', configureServer: attach, configurePreviewServer: attach };
}
