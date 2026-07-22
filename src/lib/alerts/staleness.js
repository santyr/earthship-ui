// Item-staleness detection for the curated "essential" telemetry set.
//
// openHAB only pushes statechanged events, so a dead sensor simply goes
// quiet — nothing arrives to say it failed. The openhab store records a
// lastUpdated wall-clock per item (snapshot + statechanged); this module
// turns that into the staleEssentials context the console-alert projector
// (consoleAlerts.js) already knows how to render.
//
// The list is deliberately small and limited to items that are known to
// change more often than their threshold, so silence is meaningful:
// - Temperatures jitter continuously; 15 min of total silence means the
//   sensor (or its ingest path) is dead.
// - BMS_SOC can legitimately plateau (e.g. hours at 100% in float), so it
//   gets a longer 60-minute threshold to avoid false alarms.
export const ESSENTIAL_STALE_THRESHOLD_MS = 15 * 60_000;
export const STALENESS_CHECK_INTERVAL_MS = 60_000;

export const ESSENTIAL_ITEMS = Object.freeze([
  Object.freeze({
    name: 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
    label: 'Outdoor temperature',
    route: 'home',
  }),
  Object.freeze({
    name: 'AmbientWeatherWS2902A_IndoorSensor_Temperature',
    label: 'Indoor temperature',
    route: 'home',
  }),
  Object.freeze({
    name: 'BMS_SOC',
    label: 'Battery SoC',
    route: 'energy',
    thresholdMs: 60 * 60_000,
  }),
]);

// Pure: (lastUpdatedByName, nowMs) -> staleEssentials entries in the exact
// element shape projectConsoleAlerts() consumes. Items never seen (no
// snapshot yet) are skipped — boot/connection problems are covered by the
// connection alerts, not fabricated per-item staleness.
export function computeStaleEssentials(lastUpdatedByName = {}, nowMs = Date.now(), {
  essentials = ESSENTIAL_ITEMS,
  thresholdMs = ESSENTIAL_STALE_THRESHOLD_MS,
} = {}) {
  const stale = [];
  for (const item of essentials) {
    const lastSeen = lastUpdatedByName[item.name];
    if (!Number.isFinite(lastSeen)) continue;
    const limit = Number.isFinite(item.thresholdMs) ? item.thresholdMs : thresholdMs;
    if (nowMs - lastSeen <= limit) continue;
    stale.push({
      name: item.name,
      label: item.label,
      route: item.route,
      severity: 'warning',
      fullText: `${item.label} has not updated in over ${Math.round(limit / 60_000)} minutes.`,
      transitionAt: lastSeen + limit,
    });
  }
  return stale;
}
