import { constants } from 'node:fs';
import { open, realpath, stat, lstat } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { homedir } from 'node:os';
import { OBSERVATION_MAX_BYTES, parseHouseholdObservation } from './observation.js';
import { parseBatteryPerformance } from './batteryPerformance.js';

// Preserve Vite's default sensitive-file exclusions and add private agent and
// receipt staging. Filesystem permissions alone do not constrain the web server.
export const HOUSEHOLD_FS_DENY = ['.env', '.env.*', '*.{crt,pem,key,p12,pfx,cer,der}', '.npmrc', '.yarnrc.yml',
  '**/.git/**', '**/.superpowers/**', '**/.codex/**', '**/.aws/**'];

function ownedFile(info) {
  return info.isFile() && info.uid === process.getuid() && (info.mode & 0o777) === 0o600
    && info.nlink === 1 && info.size <= OBSERVATION_MAX_BYTES;
}
function same(a, b) {
  return ['dev', 'ino', 'mode', 'uid', 'nlink', 'size', 'mtimeMs', 'ctimeMs'].every(key => a[key] === b[key]);
}
async function readObservation(path, nowMs, validate = parseHouseholdObservation) {
  if (resolve(path) !== path || await realpath(path) !== path) throw new Error('unavailable');
  const parent = await stat(dirname(path));
  if (!parent.isDirectory() || parent.uid !== process.getuid() || (parent.mode & 0o777) !== 0o700) throw new Error('unavailable');
  const handle = await open(path, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const original = await handle.stat();
    if (!ownedFile(original)) throw new Error('unavailable');
    const bytes = Buffer.alloc(OBSERVATION_MAX_BYTES + 1);
    let length = 0;
    while (length < bytes.length) {
      const result = await handle.read(bytes, length, bytes.length - length, null);
      if (!result.bytesRead) break;
      length += result.bytesRead;
    }
    if (length > OBSERVATION_MAX_BYTES || length !== original.size
      || !same(original, await handle.stat()) || !same(original, await lstat(path))
      || !same(parent, await stat(dirname(path))) || await realpath(path) !== path) throw new Error('unavailable');
    const raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, length));
    if (!validate(raw, { nowMs })) throw new Error('unavailable');
    return raw;
  } finally { await handle.close(); }
}

/** Fixed file transport only: no receipt replay, model execution or command path. */
export function householdObservationPlugin({
  cachePath = process.env.HOUSEHOLD_OBSERVATION_CACHE || resolve(homedir(), '.local/state/household-intel/observation.json'),
  batteryCachePath = resolve(homedir(), '.local/state/household-intel/battery-performance.json'),
  now = Date.now,
} = {}) {
  const attach = server => { server.middlewares.use(async (req, res, next) => {
    let url;
    try { url = new URL(req.url || '/', 'http://localhost'); } catch { return next(); }
    const battery = url.pathname === '/api/household-battery-performance';
    if (!battery && url.pathname !== '/api/household-observation') return next();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    if (req.method !== 'GET') { res.setHeader('Allow', 'GET'); res.writeHead(405).end('{"status":"unavailable"}'); return; }
    if (url.search) { res.writeHead(400).end('{"status":"unavailable"}'); return; }
    try { const raw = await readObservation(battery ? batteryCachePath : cachePath, now(), battery ? parseBatteryPerformance : parseHouseholdObservation); res.writeHead(200).end(raw); }
    catch { if (!res.headersSent) res.writeHead(503); res.end('{"status":"unavailable"}'); }
  }); };
  return { name: 'household-observation', configureServer: attach, configurePreviewServer: attach };
}
