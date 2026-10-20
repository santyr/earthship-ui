import { get, writable } from 'svelte/store';
import { createClient } from './client.js';
import { createSSE } from './sse.js';
import { withReadTimeout, READ_TIMEOUT_MS } from './readRequest.js';
import { parseSourceTimestamp } from './timestamp.js';
import { TEMPERATURE_ITEMS } from '../alerts/staleness.js';
import { ASTRO_EVIDENCE_ITEMS } from '../weather/astroPresentation.js';
const EVIDENCE_ITEMS = [...TEMPERATURE_ITEMS.map(item => item.name), ...ASTRO_EVIDENCE_ITEMS];

export const items = writable({});
export const thingStatuses = writable({});
export const connection = writable('connecting');
export const reconciliation = writable('pending');
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

// Upstream lastStateUpdate provenance for the two curated temperature items.
// REST snapshots and targeted SSE stateupdated events populate this evidence;
// ordinary statechanged receipt times never do.
export const itemUpdateEvidence = writable({});

export function applyUpdateEvidence(name, rawTimestamp, state) {
  if (!EVIDENCE_ITEMS.includes(name)) return;
  const timestamp = parseSourceTimestamp(rawTimestamp);
  const prior = get(itemUpdateEvidence)[name];
  if (timestamp !== null && prior?.lastKnown != null && timestamp < prior.lastKnown) return false;
  itemUpdateEvidence.update(current => ({
    ...current,
    [name]: { lastKnown: timestamp ?? prior?.lastKnown ?? null, available: timestamp !== null,
      ...(ASTRO_EVIDENCE_ITEMS.includes(name) ? { state } : {}) },
  }));
  if (ASTRO_EVIDENCE_ITEMS.includes(name) && timestamp !== null && typeof state === 'string') applyState(name, state);
  return true;
}

// A complete REST collection replaces the prior collection. Deltas received
// after its request began win, including newly added resources and source clocks.
export function applySnapshot(arr, { preserve = new Set(), preserveEvidence = preserve } = {}) {
  const rows = new Map(arr.map(item => [item.name, item]));
  const accepted = new Map();
  for (const name of EVIDENCE_ITEMS) {
    if (!preserveEvidence.has(name)) accepted.set(name, applyUpdateEvidence(name, rows.get(name)?.lastStateUpdate, rows.get(name)?.state));
  }
  items.update(current => {
    const next = {};
    for (const it of arr) {
      if (preserve.has(it.name)) continue;
      if (ASTRO_EVIDENCE_ITEMS.includes(it.name) && accepted.get(it.name) === false) {
        if (it.name in current) next[it.name] = current[it.name];
      } else next[it.name] = it.state;
    }
    for (const name of preserve) if (name in current) next[name] = current[name];
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

export function applyThingSnapshot(things = [], { preserve = new Set() } = {}) {
  thingStatuses.update(current => {
    const next = {};
    for (const thing of things) {
      if (typeof thing?.UID !== 'string' || !thing.UID || preserve.has(thing.UID)) continue;
      next[thing.UID] = normalizeThingStatus(thing.statusInfo);
    }
    for (const uid of preserve) if (uid in current) next[uid] = current[uid];
    return next;
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

let stopSession = null;

export function stopOpenhab() {
  stopSession?.();
  stopSession = null;
  _client = null;
  clientReady.set(false);
  connection.set('connecting');
  reconciliation.set('pending');
}

export async function initOpenhab(config, {
  clientFactory = createClient,
  sseFactory = createSSE,
  retryBaseMs = INITIAL_SNAPSHOT_RETRY_BASE_MS,
  retryMaxMs = INITIAL_SNAPSHOT_RETRY_MAX_MS,
  requestTimeoutMs = READ_TIMEOUT_MS,
  signal,
} = {}) {
  stopOpenhab();
  const client = clientFactory(config);
  _client = client;
  const lifetime = new AbortController();
  let active = true, sse = null, retryTimer = null, attempt = null;
  let epoch = 0, delay = retryBaseMs, transport = 'connecting', reconciled = false;
  let sequence = 0;
  const itemDeltas = new Map(), thingDeltas = new Map(), evidenceDeltas = new Map();
  const after = (deltas, start) => new Set([...deltas].filter(([, seq]) => seq > start).map(([name]) => name));
  const publishStatus = () => {
    if (active) connection.set(transport === 'live' && !reconciled ? 'reconciling' : transport);
  };
  function stop() {
    if (!active) return;
    active = false;
    lifetime.abort(); attempt?.abort(); clearTimeout(retryTimer);
    sse?.stop(); signal?.removeEventListener('abort', onAbort);
  }
  function onAbort() { if (stopSession === stop) stopOpenhab(); else stop(); }
  stopSession = stop;
  signal?.addEventListener('abort', onAbort, { once: true });
  if (signal?.aborted) onAbort();

  async function fetchSnapshots() {
    attempt?.abort(); clearTimeout(retryTimer);
    const controller = new AbortController();
    attempt = controller;
    const version = ++epoch;
    const start = sequence;
    reconciled = false; reconciliation.set('pending'); publishStatus();
    const [itemResult, thingResult] = await Promise.allSettled([
      withReadTimeout(readSignal => client.getAllItems({ signal: readSignal }), { signal: controller.signal, timeoutMs: requestTimeoutMs }),
      withReadTimeout(readSignal => client.getAllThings({ signal: readSignal }), { signal: controller.signal, timeoutMs: requestTimeoutMs }),
    ]);
    if (!active || version !== epoch) return null;
    const itemOk = itemResult.status === 'fulfilled' && Array.isArray(itemResult.value);
    const thingOk = thingResult.status === 'fulfilled' && Array.isArray(thingResult.value);
    if (itemOk) applySnapshot(itemResult.value, { preserve: after(itemDeltas, start), preserveEvidence: after(evidenceDeltas, start) });
    // A failed optional Thing read is not an authoritative empty inventory.
    // Retain the last observation but gate controls until reconciliation succeeds.
    if (thingOk) applyThingSnapshot(thingResult.value, { preserve: after(thingDeltas, start) });
    reconciled = itemOk && thingOk;
    reconciliation.set(reconciled ? 'ready' : 'retrying'); publishStatus();
    return { itemOk, complete: reconciled };
  }
  function scheduleRetry() {
    if (!active) return;
    clearTimeout(retryTimer);
    retryTimer = setTimeout(async () => {
      const result = await fetchSnapshots();
      if (!result) return;
      if (!result.complete) { delay = Math.min(delay * 2, retryMaxMs); scheduleRetry(); }
      else delay = retryBaseMs;
    }, delay);
  }
  function resync() {
    delay = retryBaseMs;
    void fetchSnapshots().then(result => { if (result && !result.complete) scheduleRetry(); });
  }

  // Items establish the initial display. Optional provider reads are bounded;
  // failed providers leave reconciliation pending while the stream can start.
  while (active) {
    const result = await fetchSnapshots();
    if (!active) break;
    if (result?.itemOk) {
      clientReady.set(true);
      sse = sseFactory({
        ...config, staleSeconds: config.staleBannerSeconds,
        onState: (name, value) => { if (active) { itemDeltas.set(name, ++sequence); applyState(name, value); } },
        onUpdateEvidence: (name, timestamp, state) => {
          if (!active) return;
          evidenceDeltas.set(name, ++sequence);
          if (ASTRO_EVIDENCE_ITEMS.includes(name)) itemDeltas.set(name, sequence);
          applyUpdateEvidence(name, timestamp, state);
        },
        onThingStatus: (uid, status) => { if (active) { thingDeltas.set(uid, ++sequence); applyThingStatus(uid, status); } },
        onStatus: status => { if (active) { transport = status; publishStatus(); } },
        onReconnect: () => { if (active) resync(); },
      });
      sse.start();
      if (!result.complete) scheduleRetry();
      return client;
    }
    await new Promise(resolve => {
      const done = () => { clearTimeout(retryTimer); lifetime.signal.removeEventListener('abort', done); resolve(); };
      lifetime.signal.addEventListener('abort', done, { once: true });
      retryTimer = setTimeout(done, delay);
    });
    delay = Math.min(delay * 2, retryMaxMs);
  }
  throw new DOMException('Initialization canceled', 'AbortError');
}
