#!/usr/bin/env node
// Read-only, bounded comparison of the disabled source-bound estimator with
// naturally persisted OpenHAB Items. Never POSTs or writes an Item.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
import { auditNightLoad } from './bms_night_load_audit.mjs';

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

function timingSnapshot(raw, tick, fieldName = null) {
  try {
    const receipt = JSON.parse(raw);
    const field = fieldName ? receipt.fields?.[fieldName] : receipt;
    if (!field || typeof field !== 'object') return { status: 'missing_field' };
    return {
      status: ['valid', 'unavailable'].includes(field.status) ? field.status : null,
      reason: ['ok', 'source_unavailable', 'input_unavailable', 'invalid_input',
        'input_stale'].includes(field.reason) ? field.reason : null,
      receiptAgeMs: Number.isSafeInteger(receipt.recordedAt) ? tick - receipt.recordedAt : null,
      validForMs: Number.isSafeInteger(field.validUntil) ? field.validUntil - tick : null,
    };
  } catch (_) { return { status: 'missing_or_invalid_receipt' }; }
}

export function replayRuntime(histories, { startMs, endMs, nightLoadByDay = {} }) {
  if (!Number.isSafeInteger(startMs) || !Number.isSafeInteger(endMs)
      || startMs <= 0 || endMs < startMs || endMs - startMs > MAX_WINDOW_MS) {
    throw new Error('bounded replay window required');
  }
  if (!nightLoadByDay || typeof nightLoadByDay !== 'object' || Array.isArray(nightLoadByDay)
      || Object.keys(nightLoadByDay).length > 2
      || Object.entries(nightLoadByDay).some(([day, watts]) =>
        !/^\d{4}-\d{2}-\d{2}$/.test(day) || !Number.isFinite(watts)
        || watts < 0 || watts > 20000)) {
    throw new Error('invalid bounded night-load inputs');
  }
  const rows = Object.fromEntries([...EVIDENCE, ...LIVE].map(name => [name, checkedRows(name, histories[name])]));
  const indices = Object.fromEntries(Object.keys(rows).map(name => [name, 0]));
  const held = Object.fromEntries(Object.keys(rows).map(name => [name, 'NULL']));
  const output = { BMS_Runtime_Basis: 'NULL', BMS_TimeToDischarge_Smoothed: 'NULL', BMS_TimeToFull_Smoothed: 'NULL' };
  const memory = new Map();
  let tick = startMs;
  const basisCounts = {}, disagreements = [], disagreementPairs = {}, ttfReversalViolations = [];
  const firstOffSourceSnapshots = [];
  const overnightLoadInputs = {};
  let firstNonOffAt = null;
  let priorCandidateBasis = null;
  let confirmedChargingTicks = 0;
  const confirmedChargingTransitions = [], chargingBmsBasisViolations = [];
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
      persistence: { averageBetween: (start, end) => {
        if (name !== 'ConextGateway_ACPowerValue'
            || start.hour !== 20 || start.minute !== 30
            || end.hour !== 6 || end.minute !== 0
            || start.day === end.day) throw new Error('unexpected overnight-load window');
        const day = end.toLocalDate().toString();
        const watts = Object.hasOwn(nightLoadByDay, day) ? nightLoadByDay[day] : null;
        overnightLoadInputs[day] = watts === null
          ? { source: 'rule_fallback_155w', watts: 155 }
          : { source: 'as_persisted_weighted_diagnostic', watts };
        return watts;
      } },
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
    const sandbox = { require: () => openhab, Date: { now: () => tick } };
    // Observe the candidate's own validated inputs; do not duplicate its
    // receipt qualification or change the script's publications/cache logic.
    vm.runInNewContext(source + '\n;globalThis.__qualificationAudit = { bankReady, current, currentA: i };',
      sandbox, { timeout: 1000 });
    const audit = sandbox.__qualificationAudit;
    const basis = output.BMS_Runtime_Basis;
    basisCounts[basis] = (basisCounts[basis] || 0) + 1;
    if (basis === 'off' && firstOffSourceSnapshots.length < 12) {
      firstOffSourceSnapshots.push({
        at: new Date(tick).toISOString(),
        soc: timingSnapshot(held.BMS_SOC_Evidence_JSON, tick),
        remainingAh: timingSnapshot(held.BMS_Aux_Evidence_JSON, tick, 'battery.remaining_ah'),
        current: timingSnapshot(held.BMS_Runtime_Input_Evidence_JSON, tick, 'battery.dc_current_ca'),
        voltage: timingSnapshot(held.BMS_Runtime_Input_Evidence_JSON, tick, 'battery.dc_voltage_cv'),
      });
    }
    if (basis !== 'off' && firstNonOffAt === null) firstNonOffAt = new Date(tick).toISOString();
    const oldBasis = held.BMS_Runtime_Basis;
    if (oldBasis !== 'NULL' && oldBasis !== basis) {
      const at = new Date(tick).toISOString();
      const key = `${oldBasis} -> ${basis}`;
      const pair = disagreementPairs[key] || (disagreementPairs[key] = { ticks: 0, firstAt: at, lastAt: at });
      pair.ticks++;
      pair.lastAt = at;
      if (disagreements.length < 12) disagreements.push({ at, live: oldBasis, candidate: basis });
    }
    if (audit.bankReady && audit.currentA >= 1.0) {
      confirmedChargingTicks++;
      if (basis === 'bms') chargingBmsBasisViolations.push(new Date(tick).toISOString());
      if (priorCandidateBasis === 'bms' && confirmedChargingTransitions.length < 12) {
        confirmedChargingTransitions.push({ at: new Date(tick).toISOString(),
          priorBasis: priorCandidateBasis, candidateBasis: basis, currentA: audit.currentA,
          observedAt: new Date(audit.current.observedAt).toISOString() });
      }
    }
    if ((!audit.bankReady || audit.currentA < 0.5)
        && Number(output.BMS_TimeToFull_Smoothed) > 0) {
      ttfReversalViolations.push(new Date(tick).toISOString());
    }
    priorCandidateBasis = basis;
  }
  return {
    window: [new Date(startMs).toISOString(), new Date(endMs).toISOString()],
    ticks: Object.values(basisCounts).reduce((a, b) => a + b, 0),
    candidateBasisTicks: basisCounts,
    firstNonOffAt,
    disagreementPairs,
    firstBasisDisagreements: disagreements,
    firstOffSourceSnapshots,
    ttfReversalViolations,
    confirmedChargingTicks, confirmedChargingTransitions, chargingBmsBasisViolations,
    candidateScriptSha256: createHash('sha256').update(source).digest('hex'),
    overnightLoadInputs,
    lastCandidate: { basis: output.BMS_Runtime_Basis, ttdMin: output.BMS_TimeToDischarge_Smoothed,
      ttfMin: output.BMS_TimeToFull_Smoothed },
    caveat: 'Off-source snapshots are raw timing diagnostics, not the rule validity audit. Nightly loads are as-persisted Item diagnostics or the rule fallback, not source-fresh or proven equivalent to OpenHAB averageBetween; do not use numeric TTD for promotion.',
  };
}

async function fetchHistory(base, name, startMs, endMs, maxBytes = MAX_RESPONSE_BYTES) {
  const url = new URL(`/rest/persistence/items/${encodeURIComponent(name)}`, base);
  url.searchParams.set('serviceId', 'jdbc');
  url.searchParams.set('starttime', new Date(startMs).toISOString());
  url.searchParams.set('endtime', new Date(endMs).toISOString());
  const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
  const body = await response.text();
  if (body.length > maxBytes) throw new Error(`${name}: response bound`);
  const payload = JSON.parse(body);
  return checkedRows(name, payload.data);
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length !== 2 && args.length !== 4) {
    throw new Error('usage: node bms_runtime_shadow_replay.mjs START_UTC END_UTC [NIGHT_START_UTC NIGHT_END_UTC]');
  }
  const startMs = Date.parse(args[0]), endMs = Date.parse(args[1]);
  if (!Number.isSafeInteger(startMs) || !Number.isSafeInteger(endMs)
      || endMs < startMs || endMs - startMs > MAX_WINDOW_MS) throw new Error('bounded UTC window required');
  const base = 'http://127.0.0.1:5190';
  const nightLoadByDay = {};
  let nightLoadAudit = null;
  if (args.length === 4) {
    const nightStartMs = Date.parse(args[2]), nightEndMs = Date.parse(args[3]);
    if (!Number.isSafeInteger(nightStartMs) || !Number.isSafeInteger(nightEndMs)) {
      throw new Error('valid completed-night UTC bounds required');
    }
    const localStart = localTime(nightStartMs), localEnd = localTime(nightEndMs);
    const previousDay = new Date(`${localEnd.day}T12:00:00Z`);
    previousDay.setUTCDate(previousDay.getUTCDate() - 1);
    if (nightEndMs > startMs || localStart.day !== previousDay.toISOString().slice(0, 10)
        || localStart.hour !== 20 || localStart.minute !== 30 || localStart.second !== 0
        || localEnd.hour !== 6 || localEnd.minute !== 0 || localEnd.second !== 0) {
      throw new Error('completed local 20:30-06:00 night ending before replay required');
    }
    const powerRows = await fetchHistory(base, 'ConextGateway_ACPowerValue',
      nightStartMs - 30 * 60000, nightEndMs, 2 * 1024 * 1024);
    nightLoadAudit = auditNightLoad(powerRows, { startMs: nightStartMs, endMs: nightEndMs });
    nightLoadByDay[localEnd.day] = nightLoadAudit.averageW;
  }
  const histories = {};
  for (const name of EVIDENCE) histories[name] = await fetchHistory(base, name, startMs - 10 * 60000, endMs);
  for (const name of LIVE) histories[name] = await fetchHistory(base, name, startMs - 24 * 3600000, endMs);
  const result = replayRuntime(histories, { startMs, endMs, nightLoadByDay });
  if (nightLoadAudit) result.nightLoadAudit = nightLoadAudit;
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}
