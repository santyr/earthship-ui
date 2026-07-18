import { derived, writable } from 'svelte/store';
import { connection, items } from '../openhab/index.js';
import { controlOutcomes } from '../controls/outcomeStore.js';
import { createAlertProjector, selectHeaderAlerts } from './consoleAlerts.js';

const projector = createAlertProjector();

export const alertContext = writable({ staleEssentials: [], batteryAlarms: [] });

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
