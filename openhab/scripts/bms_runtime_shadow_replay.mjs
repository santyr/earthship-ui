#!/usr/bin/env node
// Read-only, bounded comparison of the disabled source-bound estimator with
// naturally persisted OpenHAB Items. Never POSTs or writes an Item.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import vm from 'node:vm';

const source = readFileSync(new URL('../rules/bms-runtime-estimator-evidence.js', import.meta.url), 'utf8');
const EVIDENCE = [
  'BMS_SOC_Evidence_JSON', 'BMS_Aux_Evidence_JSON',
  'BMS_Runtime_Input_Evidence_JSON', 'Power_Evidence_JSON',
  'Inverter_AC_Evidence_JSON', 'Sun_Position_Elevation',
];
const LIVE = ['BMS_Runtime_Basis', 'BMS_TimeToDischarge_Smoothed', 'BMS_TimeToFull_Smoothed'];
const STEP_MS = 30000;
const MAX_WINDOW_MS = 4 * 60 * 60 * 1000;
const MAX_ROWS = 12000;
const MAX_RESPONSE_BYTES = 8 * 1024 * 1024;
const localFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'America/Denver', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

function localTime(ms) {
  const p = Object.fromEntries(localFormat.formatToParts(new Date(ms)).map(x => [x.type, x.value]));
  return { day: `${p.year}-${p.month}-${p.day}`, hour: +p.hour, minute: +p.minute, second: +p.second };
}
class LocalZDT {
  constructor(parts) { Object.assign(this, parts); }
  withHour(hour) { return new LocalZDT({ ...this, hour }); }
  withMinute(minute) { return new LocalZDT({ ...this, minute }); }
  withSecond(second) { return new LocalZDT({ ...this, second }); }
  withNano() { return this; }
  minusDays(days) {
    const d = new Date(`${this.day}T12:00:00Z`);
    d.setUTCDate(d.getUTCDate() - days);
    return new LocalZDT({ ...this, day: d.toISOString().slice(0, 10) });
  }
  isBefore(other) {
    return `${this.day}T${String(this.hour).padStart(2, '0')}:${String(this.minute).padStart(2, '0')}:${String(this.second).padStart(2, '0')}`
      < `${other.day}T${String(other.hour).padStart(2, '0')}:${String(other.minute).padStart(2, '0')}:${String(other.second).padStart(2, '0')}`;
  }
  toLocalDate() { return { toString: () => this.day }; }
}

function checkedRows(name, rows) {
  if (!Array.isArray(rows) || rows.length > MAX_ROWS) throw new Error(`${name}: row bound`);
  let previous = -Infinity;
  return rows.map(row => {
    if (!Number.isSafeInteger(row?.time) || row.time < previous || typeof row.state !== 'string') {
      throw new Error(`${name}: invalid or unordered history`);
    }
    previous = row.time;
    return { time: row.time, state: row.state };
  });
}

export function replayRuntime(histories, { startMs, endMs }) {
  if (!Number.isSafeInteger(startMs) || !Number.isSafeInteger(endMs)
      || startMs <= 0 || endMs < startMs || endMs - startMs > MAX_WINDOW_MS) {
    throw new Error('bounded replay window required');
  }
  const rows = Object.fromEntries([...EVIDENCE, ...LIVE].map(name => [name, checkedRows(name, histories[name])]));
  const indices = Object.fromEntries(Object.keys(rows).map(name => [name, 0]));
  const held = Object.fromEntries(Object.keys(rows).map(name => [name, 'NULL']));
  const output = { BMS_Runtime_Basis: 'NULL', BMS_TimeToDischarge_Smoothed: 'NULL', BMS_TimeToFull_Smoothed: 'NULL' };
  const memory = new Map();
  let tick = startMs;
  const basisCounts = {}, disagreements = [], ttfReversalViolations = [];
  const openhab = {
    cache: { private: {
      get: (key, fallback) => {
        if (!memory.has(key) && fallback) memory.set(key, fallback());
        return memory.get(key);
      }, put: (key, value) => memory.set(key, value),
    } },
    time: { toZDT: () => new LocalZDT(localTime(tick)) },
    items: { getItem: name => ({
      get state() { return name in output ? output[name] : held[name] ?? 'NULL'; },
      persistence: { averageBetween: () => 155 },
      postUpdate: value => {
        if (!(name in output)) throw new Error(`unexpected output ${name}`);
        output[name] = String(value);
      },
      sendCommand: () => { throw new Error('command forbidden in shadow replay'); },
    }) },
  };
  for (; tick <= endMs; tick += STEP_MS) {
    for (const [name, history] of Object.entries(rows)) {
      while (indices[name] < history.length && history[indices[name]].time <= tick) {
        held[name] = history[indices[name]++].state;
      }
    }
    vm.runInNewContext(source, { require: () => openhab, Date: { now: () => tick } }, { timeout: 1000 });
    const basis = output.BMS_Runtime_Basis;
    basisCounts[basis] = (basisCounts[basis] || 0) + 1;
    const oldBasis = held.BMS_Runtime_Basis;
    if (oldBasis !== 'NULL' && oldBasis !== basis && disagreements.length < 12) {
      disagreements.push({ at: new Date(tick).toISOString(), live: oldBasis, candidate: basis });
    }
    try {
      const receipt = JSON.parse(held.BMS_Runtime_Input_Evidence_JSON);
      const f = receipt.fields?.['battery.dc_current_ca'];
      if (f?.status === 'valid' && f.reason === 'ok' && tick < f.validUntil
          && f.value < 50 && Number(output.BMS_TimeToFull_Smoothed) > 0) {
        ttfReversalViolations.push(new Date(tick).toISOString());
      }
    } catch (_) { /* missing receipt is already reflected by candidate basis */ }
  }
  return {
    window: [new Date(startMs).toISOString(), new Date(endMs).toISOString()],
    ticks: Object.values(basisCounts).reduce((a, b) => a + b, 0),
    candidateBasisTicks: basisCounts,
    firstBasisDisagreements: disagreements,
    ttfReversalViolations,
    lastCandidate: { basis: output.BMS_Runtime_Basis, ttfMin: output.BMS_TimeToFull_Smoothed },
    caveat: 'Projection minutes use an unqualified 155 W nightly fallback; do not compare numeric TTD or infer operational readiness.',
  };
}

async function fetchHistory(base, name, startMs, endMs) {
  const url = new URL(`/rest/persistence/items/${encodeURIComponent(name)}`, base);
  url.searchParams.set('serviceId', 'jdbc');
  url.searchParams.set('starttime', new Date(startMs).toISOString());
  url.searchParams.set('endtime', new Date(endMs).toISOString());
  const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
  const body = await response.text();
  if (body.length > MAX_RESPONSE_BYTES) throw new Error(`${name}: response bound`);
  const payload = JSON.parse(body);
  return checkedRows(name, payload.data);
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length !== 2) throw new Error('usage: node bms_runtime_shadow_replay.mjs START_UTC END_UTC');
  const startMs = Date.parse(args[0]), endMs = Date.parse(args[1]);
  if (!Number.isSafeInteger(startMs) || !Number.isSafeInteger(endMs)
      || endMs < startMs || endMs - startMs > MAX_WINDOW_MS) throw new Error('bounded UTC window required');
  const base = 'http://127.0.0.1:5190';
  const histories = {};
  for (const name of EVIDENCE) histories[name] = await fetchHistory(base, name, startMs - 10 * 60000, endMs);
  for (const name of LIVE) histories[name] = await fetchHistory(base, name, startMs - 24 * 3600000, endMs);
  process.stdout.write(`${JSON.stringify(replayRuntime(histories, { startMs, endMs }), null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}
