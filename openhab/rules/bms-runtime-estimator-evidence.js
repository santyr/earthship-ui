// Source-only candidate: display-only runtime estimator with source-bound input
// receipts. Keep the live rev-3 source separate until collector and fault gates
// pass. This rule never commands equipment.
// Dusk verification 2026-07-14 21:40 found: at handoff the current sits just
// past the -0.5 A gate and BMS TTD (= capacity/current) is still division-by-
// near-zero — it published 8400+ min for ~20 min while the load projection
// (1020 min) was the accurate number. Fix: two-level gating.
//   discharging: hysteresis enter <= -0.5 A / exit >= -0.25 A (unchanged)
//   deep:        enter <= -1.2 A / exit >= -0.8 A — BMS samples admitted
//                ONLY here (basis "bms", median-of-9)
//   shallow discharge: publish the overnight-load projection, basis
//                "evening" — this is also the only regime where "evening"
//                can occur, since the instant current gate always beats the
//                lagged PV-crossover EMA (verified: crossover never fired).
//   idle: projection over house-load EMA ("now") or overnight avg
//                ("evening" via PV crossover / sun < 15 deg), as before.
// Usable energy: bank derived remaining/SoC*100 (auto-scales), 10% BMS
// floor, eta 0.90. Raw TTD 0 is a sentinel, always skipped. Cache resets on
// script reload (first posts track raw / re-seed EMAs).
const { items, cache, time } = require("openhab");

const N = 9;
const ENTER_A = -0.5, EXIT_A = -0.25;
const DEEP_ENTER_A = -1.2, DEEP_EXIT_A = -0.8;
// Dwell timer (2026-07-15): during dawn/dusk crossover the current bounces
// across both gates and the basis label flapped ~8x in 40 min. A state may
// only flip after 8 min in its current state — values stay coherent with
// the label because dwell applies to the state machine, not the display.
const DWELL_MS = 8 * 60 * 1000;
const ETA = 0.90, RESERVE_PCT = 10, P_FLOOR_W = 60;
// Idle evening/now hysteresis (2026-07-16): a single margin flapped the
// basis 6x in 37 min on a partly-cloudy dawn — enter evening below 1.15x
// load, return to now only above 1.40x.
const PV_MARGIN_ENTER = 1.15, PV_MARGIN_EXIT = 1.40, LOW_SUN_DEG = 15, EMA_A = 0.05;
const NIGHT_FALLBACK_W = 155; // measured mean 2026-07-06..13

function num(name) {
  const raw = items.getItem(name).state;
  if (raw === null || raw === "NULL" || raw === "UNDEF") return NaN;
  return parseFloat(raw);
}
const nowMs = Date.now();
function receipt(name, basis) {
  try {
    const body = String(items.getItem(name).state);
    if (body.length > 8192) return null;
    const row = JSON.parse(body);
    if (!row || typeof row !== 'object' || Array.isArray(row)
        || row.version !== 1 || (basis && row.basis !== basis)
        || typeof row.streamEpoch !== 'string' || !row.streamEpoch
        || !Number.isSafeInteger(row.recordedAt) || row.recordedAt <= 0
        || row.recordedAt > nowMs || nowMs - row.recordedAt > 180000) return null;
    if (name !== 'BMS_SOC_Evidence_JSON'
        && (!Number.isSafeInteger(row.sequence) || row.sequence <= 0)) return null;
    return row;
  } catch (_) { return null; }
}
function nativeField(name, basis, key, ttl, property, min, max) {
  const row = receipt(name, basis);
  const f = row && row.fields && row.fields[key];
  if (!f || f.status !== 'valid' || f.reason !== 'ok'
      || !Number.isSafeInteger(f.observedAt) || f.observedAt <= 0
      || f.observedAt > row.recordedAt
      || f.validUntil !== f.observedAt + ttl || nowMs >= f.validUntil
      || !Number.isSafeInteger(f[property]) || f[property] < min || f[property] > max) return null;
  return { value: f[property], observedAt: f.observedAt };
}
function soc() {
  const row = receipt('BMS_SOC_Evidence_JSON');
  if (!row || row.status !== 'valid' || row.reason !== 'ok'
      || !Number.isSafeInteger(row.observedAt) || row.observedAt <= 0
      || !Number.isSafeInteger(row.scaleObservedAt) || row.scaleObservedAt <= 0
      || row.observedAt > row.recordedAt || row.scaleObservedAt > row.recordedAt
      || row.validUntil !== Math.min(row.observedAt, row.scaleObservedAt) + 120000
      || nowMs >= row.validUntil || typeof row.soc !== 'number'
      || !Number.isFinite(row.soc) || row.soc < 0 || row.soc > 100) return NaN;
  return row.soc;
}
function remainingAh() {
  return nativeField('BMS_Aux_Evidence_JSON', 'discover_bms_190_native_aux_v1',
    'battery.remaining_ah', 120000, 'value', 0, 450)?.value ?? NaN;
}
function currentA() {
  const centiamps = nativeField('BMS_Runtime_Input_Evidence_JSON',
    'native_runtime_inputs_v1', 'battery.dc_current_ca', 90000, 'value', -32767, 32767);
  return centiamps ? centiamps.value / 100 : NaN;
}
function voltageV() {
  const centivolts = nativeField('BMS_Runtime_Input_Evidence_JSON',
    'native_runtime_inputs_v1', 'battery.dc_voltage_cv', 90000, 'value', 4000, 6500);
  return centivolts ? centivolts.value / 100 : NaN;
}
function bmsMinutes(field) {
  return nativeField('BMS_Runtime_Input_Evidence_JSON', 'native_runtime_inputs_v1',
    field, 120000, 'value', 0, 100000);
}
function acWatts() {
  return nativeField('Inverter_AC_Evidence_JSON', 'inverter_output',
    'inverter.ac_output_w', 30000, 'watts', 0, 20000)?.value ?? NaN;
}
function pvWatts() {
  return nativeField('Power_Evidence_JSON', null,
    'pv.input_power_w', 120000, 'watts', 0, 4294967294)?.value ?? NaN;
}
function ema(key, v) {
  if (!Number.isFinite(v)) return cache.private.get(key);
  const prev = cache.private.get(key);
  const next = (prev == null || !Number.isFinite(prev)) ? v : prev + EMA_A * (v - prev);
  cache.private.put(key, next);
  return next;
}
function publish(minutes, basis) {
  const outItem = items.getItem("BMS_TimeToDischarge_Smoothed");
  const rounded = basis === "bms" ? Math.round(minutes) : Math.round(minutes / 10) * 10;
  if (String(rounded) !== String(parseInt(outItem.state))) outItem.postUpdate(rounded);
  const bItem = items.getItem("BMS_Runtime_Basis");
  if (bItem.state !== basis) bItem.postUpdate(basis);
}

function overnightW() {
  // Before 06:00 the current night is unfinished: use the last completed one.
  // Key by that window, so midnight retains it and 06:00 refreshes it.
  const now = time.toZDT();
  let end = now.withHour(6).withMinute(0).withSecond(0).withNano(0);
  if (now.isBefore(end)) end = end.minusDays(1);
  const day = end.toLocalDate().toString();
  let night = cache.private.get("p_night");
  if (!night || night.day !== day) {
    let w = NaN;
    try {
      const start = end.minusDays(1).withHour(20).withMinute(30);
      const a = items.getItem("ConextGateway_ACPowerValue").persistence.averageBetween(start, end);
      w = (a == null) ? NaN : (typeof a === "number" ? a : parseFloat(a.numericState ?? a.state));
    } catch (e) { /* fallback below */ }
    night = { day, w: Number.isFinite(w) ? w : NIGHT_FALLBACK_W };
    cache.private.put("p_night", night);
  }
  return night.w;
}

// projection(forceEvening): usable energy over a load basis. forceEvening is
// used during shallow discharge, where overnight-average is the honest basis.
function projection(forceEvening) {
  const stateOfCharge = soc(), rem = remainingAh(), volts = voltageV();
  const ac = acWatts(), pv = pvWatts();
  if (!Number.isFinite(ac)) cache.private.put("p_load", null);
  if (!Number.isFinite(pv)) cache.private.put("p_pv", null);
  const pLoad = Number.isFinite(ac) ? ema("p_load", ac) : NaN;
  const pPv = Number.isFinite(pv) ? ema("p_pv", pv) : NaN;
  if (![stateOfCharge, rem, volts, pLoad].every(Number.isFinite)
      || stateOfCharge <= RESERVE_PCT) {
    publish(0, "off");
    return;
  }
  const bankAh = rem / stateOfCharge * 100;
  const usableWh = bankAh * Math.max(stateOfCharge - RESERVE_PCT, 0) / 100 * volts * ETA;
  const elev = num("Sun_Position_Elevation");
  let evening;
  if (forceEvening) {
    evening = true;
  } else {
    const wasEvening = cache.private.get("idleEvening") === true;
    const margin = wasEvening ? PV_MARGIN_EXIT : PV_MARGIN_ENTER;
    evening = (Number.isFinite(pPv) && pPv < pLoad * margin) ||
      (Number.isFinite(elev) && elev < LOW_SUN_DEG);
    cache.private.put("idleEvening", evening);
  }
  if (evening) publish(usableWh / Math.max(overnightW(), P_FLOOR_W) * 60, "evening");
  else publish(usableWh / Math.max(pLoad, P_FLOOR_W) * 60, "now");
}

const i = currentA();
const bankSoc = soc(), bankRemaining = remainingAh();
const bankReady = [i, bankSoc, bankRemaining].every(Number.isFinite);
const st = cache.private.get("ttd_state", () => ({ discharging: false, deep: false, buf: [], tsDisch: 0, tsDeep: 0 }));
if (!bankReady) {
  // A held numeric Item or cached EMA must never authorize an active basis.
  st.discharging = false; st.deep = false; st.deepStreak = 0;
  st.buf.length = 0; st.lastTtdAt = null;
  cache.private.put("p_load", null);
  cache.private.put("p_pv", null);
  cache.private.put("i_chg", null);
  cache.private.put("idleEvening", null);
  publish(0, "off");
}
if (bankReady) {
  const dischDwellOk = (nowMs - (st.tsDisch || 0)) >= DWELL_MS;
  if (!st.discharging && i <= ENTER_A && dischDwellOk) {
    st.discharging = true; st.tsDisch = nowMs;
  } else if (st.discharging && i >= EXIT_A && dischDwellOk) {
    st.discharging = false; st.deep = false; st.buf.length = 0; st.tsDisch = nowMs;
  }
  if (st.discharging) {
    // Burst filter (2026-07-16): a ~45 s appliance surge (-20.7 A well-pump
    // burst) captured 'deep' from a single sample and the dwell then held a
    // misleading bms value for 8 min. Deep now needs 2 consecutive deep
    // samples (~60 s at the 30 s poll) before engaging.
    st.deepStreak = (i <= DEEP_ENTER_A) ? (st.deepStreak || 0) + 1 : 0;
    const deepDwellOk = (nowMs - (st.tsDeep || 0)) >= DWELL_MS;
    if (!st.deep && st.deepStreak >= 2 && deepDwellOk) { st.deep = true; st.tsDeep = nowMs; }
    else if (st.deep && i >= DEEP_EXIT_A && deepDwellOk) {
      st.deep = false; st.buf.length = 0; st.lastTtdAt = null; st.tsDeep = nowMs;
    }
  } else {
    st.deepStreak = 0;
  }
}

// --- Time to Full (2026-07-16): the BMS TimeToFull register has reported
// exactly one value ever (0) — effectively unimplemented on this setup.
// Estimate: missing Ah / smoothed charge current, published to
// BMS_TimeToFull_Smoothed (0 = sentinel: full or not charging). Prefer the
// BMS register if it ever starts reporting.
(function timeToFull() {
  const out = items.getItem("BMS_TimeToFull_Smoothed");
  const bmsTtf = bmsMinutes('battery.ttf_min')?.value ?? NaN;
  let ttf = 0;
  if (bankReady && Number.isFinite(bmsTtf) && bmsTtf > 0) {
    ttf = Math.round(bmsTtf);
  } else if (bankReady) {
    const stateOfCharge = soc(), rem = remainingAh();
    const iChg = ema("i_chg", i);
    if ([stateOfCharge, rem, iChg].every(Number.isFinite)
        && stateOfCharge > 0 && stateOfCharge < 99 && iChg >= 0.5) {
      const bankAh = rem / stateOfCharge * 100;
      const missingAh = bankAh * (100 - stateOfCharge) / 100;
      ttf = Math.round(missingAh / iChg * 60 / 10) * 10;
    }
  }
  if (String(ttf) !== String(parseInt(out.state))) out.postUpdate(ttf);
})();

if (!bankReady) {
  // The OFF barrier above is the only runtime publication on this path.
} else if (st.discharging && st.deep) {
  const ttd = bmsMinutes('battery.ttd_min');
  if (ttd && ttd.value > 0) {
    if (ttd.observedAt !== st.lastTtdAt) st.buf.push(ttd.value);
    st.lastTtdAt = ttd.observedAt;
    while (st.buf.length > N) st.buf.shift();
    const sorted = [...st.buf].sort((a, b) => a - b);
    publish(sorted[Math.floor(sorted.length / 2)], "bms");
  } else { st.buf.length = 0; st.lastTtdAt = null; projection(true); }
} else if (st.discharging) {
  projection(true);
} else {
  projection(false);
}
