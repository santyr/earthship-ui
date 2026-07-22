import { derived, writable } from 'svelte/store';
import { connection, items, getItemLastUpdated } from '../openhab/index.js';
import { controlOutcomes } from '../controls/outcomeStore.js';
import { createAlertProjector, selectHeaderAlerts } from './consoleAlerts.js';
import { computeStaleEssentials, STALENESS_CHECK_INTERVAL_MS } from './staleness.js';

const projector = createAlertProjector();

// staleEssentials is fed by startStalenessMonitor() below (App.svelte owns
// its lifecycle). batteryAlarms stays unwired: no BMS alarm items exist in
// this deployment's item surface (only BMS_Comms_Status/BMS_DevicePresent,
// which the projector reads directly), so nothing is invented here.
export const alertContext = writable({ staleEssentials: [], batteryAlarms: [] });

// Periodically recompute which essential items have gone silent and publish
// them into alertContext. Returns a stop() function for teardown.
export function startStalenessMonitor({
  intervalMs = STALENESS_CHECK_INTERVAL_MS,
  now = Date.now,
} = {}) {
  const check = () => {
    const staleEssentials = computeStaleEssentials(getItemLastUpdated(), now());
    alertContext.update((context) => ({ ...context, staleEssentials }));
  };
  check();
  const timer = setInterval(check, intervalMs);
  return () => clearInterval(timer);
}

export const consoleAlerts = derived(
  [connection, items, controlOutcomes, alertContext],
  ([$connection, $items, $outcomes, $context]) => {
    const projection = projector.update({
      connection: $connection,
      items: $items,
      outcomes: $outcomes,
      staleEssentials: $context.staleEssentials,
      batteryAlarms: $context.batteryAlarms,
    });
    return { ...projection, ...selectHeaderAlerts(projection.alerts) };
  },
  { alerts: [], diagnostics: [], winner: null, additionalCount: 0, ordered: [] },
);
