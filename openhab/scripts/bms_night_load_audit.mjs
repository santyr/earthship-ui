#!/usr/bin/env node
// Read-only audit of one completed overnight inverter-output window. The
// explicit UTC bounds must be selected from the local 20:30–06:00 window.
import { pathToFileURL } from 'node:url';

const ITEM = 'ConextGateway_ACPowerValue';
const MAX_ROWS = 12000;
const MAX_BYTES = 2 * 1024 * 1024;
const MAX_GAP_MS = 120000;
const CARRY_LOOKBACK_MS = 30 * 60000;

export function auditNightLoad(rows, { startMs, endMs }) {
  if (!Number.isSafeInteger(startMs) || !Number.isSafeInteger(endMs)
      || startMs <= 0 || endMs - startMs < 7 * 3600000
      || endMs - startMs > 12 * 3600000) throw new Error('bounded completed night required');
  if (!Array.isArray(rows) || rows.length > MAX_ROWS) throw new Error('row bound exceeded');
  let previous = -Infinity;
  let carry = null;
  let value = null;
  let lastAt = startMs;
  let lastSourceAt = null;
  let weighted = 0;
  let maxGapMs = 0;
  let inWindowRows = 0;
  for (const row of rows) {
    if (!Number.isSafeInteger(row?.time) || row.time <= previous
        || row.time < startMs - CARRY_LOOKBACK_MS || row.time > endMs
        || typeof row.state !== 'string' || !/^(?:0|[1-9]\d*)(?:\.\d+)?$/.test(row.state)) {
      throw new Error('invalid, unordered or out-of-window power history');
    }
    const watts = Number(row.state);
    if (!Number.isFinite(watts) || watts > 20000) throw new Error('invalid power value');
    previous = row.time;
    if (row.time <= startMs) {
      carry = row;
      value = watts;
      lastSourceAt = row.time;
      continue;
    }
    if (carry === null) throw new Error('missing start carry');
    const gap = row.time - lastSourceAt;
    if (gap > MAX_GAP_MS) throw new Error('power source gap exceeded');
    maxGapMs = Math.max(maxGapMs, gap);
    weighted += value * (row.time - lastAt);
    lastAt = row.time;
    lastSourceAt = row.time;
    value = watts;
    inWindowRows++;
  }
  if (carry === null || startMs - carry.time > MAX_GAP_MS) throw new Error('stale or absent start carry');
  if (lastSourceAt === null || endMs - lastSourceAt > MAX_GAP_MS) {
    throw new Error('power source end gap exceeded');
  }
  maxGapMs = Math.max(maxGapMs, endMs - lastSourceAt);
  weighted += value * (endMs - lastAt);
  return {
    window: [new Date(startMs).toISOString(), new Date(endMs).toISOString()],
    item: ITEM,
    method: 'bounded_left_held_state_average',
    averageW: weighted / (endMs - startMs),
    carryAgeSeconds: (startMs - carry.time) / 1000,
    maxSourceGapSeconds: maxGapMs / 1000,
    inWindowRows,
    sourceFreshnessQualified: false,
    caveat: 'As-persisted Item timestamps are not original acquisition receipts; this does not prove source freshness or exact OpenHAB extension parity.',
  };
}

async function main() {
  if (process.argv.length !== 4) throw new Error('usage: node bms_night_load_audit.mjs START_UTC END_UTC');
  const startMs = Date.parse(process.argv[2]), endMs = Date.parse(process.argv[3]);
  if (!Number.isSafeInteger(startMs) || !Number.isSafeInteger(endMs)
      || startMs <= 0 || endMs - startMs < 7 * 3600000
      || endMs - startMs > 12 * 3600000 || endMs > Date.now()) {
    throw new Error('bounded completed night required');
  }
  const url = new URL(`/rest/persistence/items/${ITEM}`, 'http://127.0.0.1:5190');
  url.searchParams.set('serviceId', 'jdbc');
  url.searchParams.set('starttime', new Date(startMs - CARRY_LOOKBACK_MS).toISOString());
  url.searchParams.set('endtime', new Date(endMs).toISOString());
  const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`power history HTTP ${response.status}`);
  const body = await response.text();
  if (body.length > MAX_BYTES) throw new Error('response bound exceeded');
  const payload = JSON.parse(body);
  process.stdout.write(`${JSON.stringify(auditNightLoad(payload.data, { startMs, endMs }), null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}
