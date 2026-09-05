import { get, writable } from 'svelte/store';
import { createClient } from './client.js';
import { createSSE } from './sse.js';
import { parseSourceTimestamp } from './timestamp.js';
import { TEMPERATURE_ITEMS } from '../alerts/staleness.js';

export const items = writable({});
export const thingStatuses = writable({});
export const connection = writable('connecting');
// Flips true once initOpenhab() has created the client AND loaded the
// initial item snapshot. Components that fetch via getClientOnce() on
// mount (e.g. HistoryChart) can react to this instead of racing App.svelte's
// onMount — critical for a direct/reload load of a chart route, where child
// components mount before initOpenhab() has run.
export const clientReady = writable(false);

let _client = null;

// Returns the singleton openHAB client created by initOpenhab(), or null if
// initOpenhab() hasn't run yet. Lets any component reach the client (for
// getHistory/sendCommand) without threading it through props.
export function getClientOnce() {
  return _client;
}

// Per-item wall-clock of the last snapshot/statechanged write. Feeds the
// item-staleness alerts (src/lib/alerts/staleness.js): a dead sensor stops
// producing statechanged events, so "last written" is the honest freshness
// signal the UI has.
export const itemUpdateEvidence = writable({});

export function applyUpdateEvidence(name, rawTimestamp) {
  if (!TEMPERATURE_ITEMS.some(item => item.name === name)) return;
  const timestamp = parseSourceTimestamp(rawTimestamp);
  const prior = get(itemUpdateEvidence)[name];
  if (timestamp !== null && prior?.lastKnown != null && timestamp < prior.lastKnown) return;
  itemUpdateEvidence.update(current => ({
    ...current,
    [name]: { lastKnown: timestamp ?? prior?.lastKnown ?? null, available: timestamp !== null },
  }));
}

export function applySnapshot(arr) {
  const rows = new Map(arr.map(item => [item.name, item]));
  for (const item of TEMPERATURE_ITEMS) applyUpdateEvidence(item.name, rows.get(item.name)?.lastStateUpdate);
  items.update((m) => {
    const next = { ...m };
    for (const name of ['BMS_SOC_LastUpdate', 'BMS_Comms_Status', 'BMS_DevicePresent']) {
      if (!rows.has(name)) delete next[name];
    }
    for (const it of arr) next[it.name] = it.state;
    return next;
  });
}
export function applyState(name, value) {
  items.update((m) => { m[name] = value; return { ...m }; });
}

function normalizeThingStatus(statusInfo = {}) {
  return {
    status: typeof statusInfo.status === 'string' ? statusInfo.status.trim().toUpperCase() : '',
    statusDetail: typeof statusInfo.statusDetail === 'string'
      ? statusInfo.statusDetail.trim().toUpperCase()
      : '',
    description: typeof statusInfo.description === 'string'
      ? statusInfo.description.trim()
      : '',
  };
}

export function applyThingSnapshot(things = []) {
  thingStatuses.update((current) => {
    for (const thing of things) {
      if (typeof thing?.UID !== 'string' || !thing.UID) continue;
      current[thing.UID] = normalizeThingStatus(thing.statusInfo);
    }
    return { ...current };
  });
}

export function applyThingStatus(uid, statusInfo) {
  if (typeof uid !== 'string' || !uid) return;
  thingStatuses.update((current) => ({ ...current, [uid]: normalizeThingStatus(statusInfo) }));
}

// Initial-snapshot retry: this display reboots together with openHAB, so the
// first getAllItems() regularly races openHAB's startup. Retry forever with
// capped doubling backoff — the wall display must self-heal, never sit dead
// behind an unhandled rejection until someone reloads it.
const INITIAL_SNAPSHOT_RETRY_BASE_MS = 2_000;
const INITIAL_SNAPSHOT_RETRY_MAX_MS = 30_000;

async function fetchSnapshots(client) {
  const [itemSnapshot, thingSnapshot] = await Promise.all([
    client.getAllItems(),
    client.getAllThings().catch(() => []),
  ]);
  applySnapshot(itemSnapshot);
  applyThingSnapshot(thingSnapshot);
}

// Re-fetch after an SSE reconnect: statechanged events that happened during
// the outage never replay, so without this the display stays stale forever
// under a green "live" badge. A failed resync is swallowed — if openHAB drops
// again the SSE loop reconnects and fires this hook once more.
async function resyncSnapshots(client) {
  try {
    await fetchSnapshots(client);
  } catch {
    /* next reconnect retries */
  }
}

export async function initOpenhab(config, {
  clientFactory = createClient,
  sseFactory = createSSE,
  retryBaseMs = INITIAL_SNAPSHOT_RETRY_BASE_MS,
  retryMaxMs = INITIAL_SNAPSHOT_RETRY_MAX_MS,
} = {}) {
  const client = clientFactory(config);
  _client = client;
  let delay = retryBaseMs;
  for (;;) {
    try {
      await fetchSnapshots(client);
      break;
    } catch {
      connection.set('connecting');
      await new Promise((resolve) => setTimeout(resolve, delay));
      delay = Math.min(delay * 2, retryMaxMs);
    }
  }
  clientReady.set(true);
  // SSE starts only once the first snapshot has landed (ordering preserved):
  // statechanged deltas without a base snapshot would render a misleading
  // partial picture.
  const sse = sseFactory({
    ...config,
    staleSeconds: config.staleBannerSeconds,
    onState: applyState,
    onUpdateEvidence: applyUpdateEvidence,
    onThingStatus: applyThingStatus,
    onStatus: (s) => connection.set(s),
    onReconnect: () => resyncSnapshots(client),
  });
  sse.start();
  return client;
}
