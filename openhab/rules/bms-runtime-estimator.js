// Hybrid runtime-to-empty estimator (rev 3, shallow-discharge fix 2026-07-15).
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
  const soc = num("BMS_SOC"), rem = num("BMS_Capacity_Remaining_Ah"), volts = num("DCData_Voltage");
  const pLoad = ema("p_load", num("ConextGateway_ACPowerValue"));
  const pPv = ema("p_pv", num("MPPT60_PV_Power"));
  if (![soc, rem, volts, pLoad].every(Number.isFinite) || soc <= RESERVE_PCT) {
    publish(0, "off");
    return;
  }
  const bankAh = rem / soc * 100;
  const usableWh = bankAh * Math.max(soc - RESERVE_PCT, 0) / 100 * volts * ETA;
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

const i = num("DCData_Current");
const st = cache.private.get("ttd_state", () => ({ discharging: false, deep: false, buf: [], tsDisch: 0, tsDeep: 0 }));
const nowMs = Date.now();
if (Number.isFinite(i)) {
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
    else if (st.deep && i >= DEEP_EXIT_A && deepDwellOk) { st.deep = false; st.tsDeep = nowMs; }
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
  const bmsTtf = num("BMS_TimeToFull_Min");
  let ttf = 0;
  if (Number.isFinite(bmsTtf) && bmsTtf > 0) {
    ttf = Math.round(bmsTtf);
  } else {
    const soc = num("BMS_SOC"), rem = num("BMS_Capacity_Remaining_Ah");
    const iChg = ema("i_chg", i);
    if ([soc, rem, iChg].every(Number.isFinite) && soc > 0 && soc < 99 && iChg >= 0.5) {
      const bankAh = rem / soc * 100;
      const missingAh = bankAh * (100 - soc) / 100;
      ttf = Math.round(missingAh / iChg * 60 / 10) * 10;
    }
  }
  if (String(ttf) !== String(parseInt(out.state))) out.postUpdate(ttf);
})();

if (st.discharging && st.deep) {
  const v = num("BMS_TimeToDischarge_Min");
  if (Number.isFinite(v) && v > 0) {
    st.buf.push(v);
    while (st.buf.length > N) st.buf.shift();
    const sorted = [...st.buf].sort((a, b) => a - b);
    publish(sorted[Math.floor(sorted.length / 2)], "bms");
  }
} else if (st.discharging) {
  projection(true);
} else {
  projection(false);
}
