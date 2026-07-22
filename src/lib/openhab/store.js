import { writable } from 'svelte/store';
import { createClient } from './client.js';
import { createSSE } from './sse.js';

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
const itemLastUpdated = {};

export function getItemLastUpdated() {
  return { ...itemLastUpdated };
}

export function applySnapshot(arr) {
  const at = Date.now();
  items.update((m) => {
    for (const it of arr) { m[it.name] = it.state; itemLastUpdated[it.name] = at; }
    return { ...m };
  });
}
export function applyState(name, value) {
  itemLastUpdated[name] = Date.now();
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
    onThingStatus: applyThingStatus,
    onStatus: (s) => connection.set(s),
    onReconnect: () => resyncSnapshots(client),
  });
  sse.start();
  return client;
}
