#!/usr/bin/env node
import http from 'node:http';
import { createHash } from 'node:crypto';
import { mkdir, mkdtemp, open, readFile, rmdir } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { RULE_UID, planRuntimeCacheRelease, runtimeRuleEnabledState, executeRuntimeCacheRelease } from './runtime-cache-release.mjs';

const rulePath = `/rest/rules/${RULE_UID}`;
const canonical = value => JSON.stringify(value, (_key, v) => v && typeof v === 'object' && !Array.isArray(v)
  ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const sha = text => createHash('sha256').update(text).digest('hex');

export function localRuntimeTransport({ token, port = 8080, timeoutMs = 5000 }) {
  if (typeof token !== 'string' || !token || /[\r\n]/.test(token)) throw new Error('invalid credential');
  return ({ method = 'GET', path, body }) => new Promise((resolve, reject) => {
    if (!['GET /rest/', `GET ${rulePath}`, `PUT ${rulePath}`, `POST ${rulePath}/enable`].includes(`${method} ${path}`)
        || (method === 'GET' && body !== undefined)
        || (method === 'POST' && !['true', 'false'].includes(body))) {
      reject(new Error('request outside runtime release scope')); return;
    }
    const payload = body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body);
    const req = http.request({ hostname: '127.0.0.1', port, path, method,
      headers: { Authorization: `Bearer ${token}`, Accept: 'application/json',
        ...(payload === undefined ? {} : { 'Content-Type': method === 'PUT' ? 'application/json' : 'text/plain',
          'Content-Length': Buffer.byteLength(payload) }) } }, res => {
      let size = 0;
      const chunks = [];
      res.on('data', chunk => {
        size += chunk.length;
        if (size > 1024 * 1024) req.destroy(new Error('response too large'));
        else chunks.push(chunk);
      });
      res.on('error', () => { clearTimeout(timer); reject(new Error('local runtime response failed')); });
      res.on('end', () => {
        clearTimeout(timer);
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`local runtime HTTP ${res.statusCode}`)); return;
        }
        try { resolve(method === 'GET' ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : null); }
        catch { reject(new Error('invalid local runtime JSON')); }
      });
    });
    const timer = setTimeout(() => req.destroy(new Error('request deadline')), timeoutMs);
    req.on('error', () => { clearTimeout(timer); reject(new Error('local runtime request failed')); });
    req.end(payload);
  });
}

export async function verifiedRuntimeBackup(snapshot, parent) {
  const directory = await mkdtemp(`${parent}/runtime-cache-release-`);
  const file = `${directory}/original-rule.json`;
  const bytes = `${canonical(snapshot)}\n`;
  const handle = await open(file, 'wx', 0o600);
  try { await handle.writeFile(bytes); await handle.sync(); } finally { await handle.close(); }
  const dir = await open(directory, 'r');
  try { await dir.sync(); } finally { await dir.close(); }
  const parentHandle = await open(parent, 'r');
  try { await parentHandle.sync(); } finally { await parentHandle.close(); }
  const readback = await readFile(file, 'utf8');
  if (readback !== bytes) throw new Error('backup readback failed');
  return { verified: true, sha256: sha(canonical(JSON.parse(readback))), file };
}

export async function main(args = process.argv.slice(2)) {
  const apply = args.length === 2 && args[0] === '--apply' && args[1] === '--attended';
  if (!apply && !(args.length === 1 && args[0] === '--check')) throw new Error('use --check or --apply --attended');
  const env = await readFile('/home/sat/.config/hex/openhab.env', 'utf8');
  const tokens = env.split(/\r?\n/).map(line => line.trim().replace(/^export\s+/, '')).filter(line => line.startsWith('OPENHAB_TOKEN='));
  if (tokens.length !== 1) throw new Error('unique token required');
  const token = tokens[0].slice('OPENHAB_TOKEN='.length).trim().replace(/^(["'])(.*)\1$/, '$2');
  const request = localRuntimeTransport({ token });
  const root = await request({ path: '/rest/' });
  const version = root.runtimeInfo?.version;
  const source = await readFile(new URL('../openhab/rules/bms-runtime-estimator.js', import.meta.url), 'utf8');
  const readRule = () => request({ path: rulePath });
  if (!apply) {
    const rule = await readRule();
    const plan = planRuntimeCacheRelease({ source, version, rule, enabled: runtimeRuleEnabledState(rule) });
    return { mode: 'check', uid: RULE_UID, enabled: plan.enabled, originalSha256: plan.originalSha256,
      replacementSha256: plan.replacementSha256, writes: 0 };
  }
  // Cooperating invocations serialize; this does not lock out the OpenHAB UI.
  const parent = '/home/sat/.local/state';
  const lock = `${parent}/runtime-cache-release.lock`;
  await mkdir(lock, { mode: 0o700 });
  let backupFile;
  try {
    const result = await executeRuntimeCacheRelease({ source, version, readRule, write: request,
      backup: async snapshot => {
        const receipt = await verifiedRuntimeBackup(snapshot, parent);
        backupFile = receipt.file;
        process.stderr.write(`Verified backup: ${backupFile}\n`);
        return receipt;
      } });
    return { mode: 'apply', ...result, backupFile };
  } finally { await rmdir(lock); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().then(result => process.stdout.write(`${JSON.stringify(result)}\n`)).catch(error => {
    // Only the executor's fixed stage vocabulary is safe to expose.
    const message = /^runtime cache release stopped at [a-z-]+; inspect live state before any further write$/.test(error.message)
      ? error.message : 'runtime cache deployment failed; inspect local state before retrying';
    process.stderr.write(`${message}\n`);
    process.exitCode = 1;
  });
}
