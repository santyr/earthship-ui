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
// Atomic REST state/clock pairs populate this evidence. Temperature SSE events
// trigger targeted reads; ordinary statechanged receipt times never do.
export const itemUpdateEvidence = writable({});

export function applyUpdateEvidence(name, rawTimestamp, state, { updateState = true } = {}) {
  if (!EVIDENCE_ITEMS.includes(name)) return;
  const timestamp = parseSourceTimestamp(rawTimestamp);
  const prior = get(itemUpdateEvidence)[name];
  if (timestamp !== null && prior?.lastKnown != null && timestamp < prior.lastKnown) return false;
  // A source clock identifies a value, not an independently renewable label.
  // Equal-clock contradictions cannot be ordered: retain the accepted pair but
  // withhold freshness until an unambiguous newer pair is observed.
  if (timestamp !== null && timestamp === prior?.lastKnown && prior?.conflicted) return false;
  if (timestamp !== null && timestamp === prior?.lastKnown
      && typeof state === 'string' && typeof prior.state === 'string' && state !== prior.state) {
    itemUpdateEvidence.update(current => ({ ...current, [name]: { ...prior, available: false, conflicted: true } }));
    return false;
  }
  const validPair = timestamp !== null && typeof state === 'string';
  itemUpdateEvidence.update(current => ({
    ...current,
    [name]: { lastKnown: validPair ? timestamp : prior?.lastKnown ?? null, available: validPair,
      state: validPair ? state : prior?.state,
      ...(!validPair && prior?.conflicted ? { conflicted: true } : {}) },
  }));
  if (updateState && validPair && get(items)[name] !== state) applyState(name, state);
  return true;
}

// Validate before publishing any part of an authoritative collection. A bad
// row is a failed read, not an empty collection or partial inventory withdrawal.
export function applySnapshot(arr, { preserve = new Set(), preserveEvidence = preserve } = {}) {
  if (!Array.isArray(arr) || arr.some(item => !item || typeof item.name !== 'string'
      || !item.name || typeof item.state !== 'string')
      || new Set(arr.map(item => item.name)).size !== arr.length) return false;
  const rows = new Map(arr.map(item => [item.name, item]));
  const accepted = new Map();
  for (const name of EVIDENCE_ITEMS) {
    if (!preserveEvidence.has(name)) accepted.set(name, applyUpdateEvidence(name, rows.get(name)?.lastStateUpdate, rows.get(name)?.state, { updateState: false }));
  }
  items.update(current => {
    const next = {};
    for (const it of arr) {
      if (preserve.has(it.name)) continue;
      if (EVIDENCE_ITEMS.includes(it.name) && accepted.get(it.name) === false) {
        if (it.name in current) next[it.name] = current[it.name];
      } else next[it.name] = it.state;
    }
    for (const name of preserve) if (name in current) next[name] = current[name];
    return next;
  });
  return true;
}
export function applyState(name, value) {
  if (TEMPERATURE_ITEMS.some(item => item.name === name)) {
    const prior = get(itemUpdateEvidence)[name];
    if (prior?.available && prior.state !== value) {
      itemUpdateEvidence.update(current => ({ ...current, [name]: { ...prior, available: false } }));
    }
  }
  items.update((m) => { m[name] = value; return { ...m }; });
}

// An absent optional field is unavailable, never an implied ONLINE state.
// Explicit non-object status data or non-string fields invalidate the read.
function normalizeThingStatus(statusInfo) {
  if (!statusInfo || typeof statusInfo !== 'object' || Array.isArray(statusInfo)) return null;
  for (const key of ['status', 'statusDetail', 'description']) {
    if (statusInfo[key] !== undefined && typeof statusInfo[key] !== 'string') return null;
  }
  return {
    status: (statusInfo.status ?? '').trim().toUpperCase(),
    statusDetail: (statusInfo.statusDetail ?? '').trim().toUpperCase(),
    description: (statusInfo.description ?? '').trim(),
  };
}

export function applyThingSnapshot(things, { preserve = new Set() } = {}) {
  if (!Array.isArray(things)) return false;
  const accepted = new Map();
  for (const thing of things) {
    if (!thing || typeof thing !== 'object' || Array.isArray(thing)
        || typeof thing.UID !== 'string' || !thing.UID || thing.UID.trim() !== thing.UID
        || accepted.has(thing.UID)) return false;
    const status = normalizeThingStatus(thing.statusInfo);
    if (!status) return false;
    accepted.set(thing.UID, status);
  }
  // Publish only after the entire inventory is valid, including preserved rows.
  thingStatuses.update(current => {
    const next = new Map([...accepted].filter(([uid]) => !preserve.has(uid)));
    for (const uid of preserve) if (Object.hasOwn(current, uid)) next.set(uid, current[uid]);
    return Object.fromEntries(next);
  });
  return true;
}

export function applyThingStatus(uid, statusInfo) {
  if (typeof uid !== 'string' || !uid || uid.trim() !== uid) return false;
  const status = normalizeThingStatus(statusInfo);
  if (!status) return false;
  thingStatuses.update((current) => ({ ...current, [uid]: status }));
  return true;
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
  // Reinitialization declares a new source/session epoch. A reconnect within
  // this session does not reset clocks, even after an authoritative removal.
  items.set({}); thingStatuses.set({}); itemUpdateEvidence.set({});
  const client = clientFactory(config);
  _client = client;
  const lifetime = new AbortController();
  let active = true, sse = null, retryTimer = null, attempt = null;
  let epoch = 0, inventoryGeneration = 0, delay = retryBaseMs, transport = 'connecting', reconciled = false;
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
    let itemOk = itemResult.status === 'fulfilled' && Array.isArray(itemResult.value);
    let thingOk = thingResult.status === 'fulfilled' && Array.isArray(thingResult.value);
    try {
      if (itemOk) {
        itemOk = applySnapshot(itemResult.value, { preserve: after(itemDeltas, start), preserveEvidence: after(evidenceDeltas, start) });
        if (itemOk) { ++inventoryGeneration; pendingTemperatureReads.clear(); }
      }
      // Failed or malformed Thing reads retain prior observations. Controls
      // stay gated until the complete current inventory has reconciled.
      if (thingOk) thingOk = applyThingSnapshot(thingResult.value, { preserve: after(thingDeltas, start) });
    } catch {
      // Processing happens after HTTP settlement and can also fail. Recover
      // through the same bounded read retry, without replaying commands.
      itemOk = false; thingOk = false;
    }
    reconciled = itemOk && thingOk;
    reconciliation.set(reconciled ? 'ready' : 'retrying'); publishStatus();
    return { itemOk, complete: reconciled };
  }
  async function reconcile(increaseDelay) {
    const requestEpoch = epoch + 1;
    try {
      const result = await fetchSnapshots();
      if (!active || !result || requestEpoch !== epoch) return;
      if (result.complete) delay = retryBaseMs;
      else {
        if (increaseDelay) delay = Math.min(delay * 2, retryMaxMs);
        scheduleRetry();
      }
    } catch {
      // Guard both asynchronous entry points as well as snapshot validation.
      if (!active || requestEpoch !== epoch) return;
      reconciled = false; reconciliation.set('retrying'); publishStatus();
      if (increaseDelay) delay = Math.min(delay * 2, retryMaxMs);
      scheduleRetry();
    }
  }
  function scheduleRetry() {
    if (!active) return;
    clearTimeout(retryTimer);
    retryTimer = setTimeout(() => {
      retryTimer = null;
      void reconcile(true);
    }, delay);
  }
  function resync() {
    delay = retryBaseMs;
    void reconcile(false);
  }

  const pendingTemperatureReads = new Set(), activeTemperatureReads = new Set(), temperatureNotifications = new Map();
  function refreshTemperatureEvidence(name) {
    pendingTemperatureReads.add(name);
    if (activeTemperatureReads.has(name)) return;
    activeTemperatureReads.add(name);
    void (async () => {
      try {
        while (active && pendingTemperatureReads.delete(name)) {
          const start = sequence, sourceEpoch = epoch, inventory = inventoryGeneration;
          try {
            const row = await withReadTimeout(signal => client.getItem(name, { signal }),
              { signal: lifetime.signal, timeoutMs: requestTimeoutMs });
            if (!active) return;
            // Reconciliation supersedes older reads, including withdrawn Items.
            if (sourceEpoch !== epoch || inventory !== inventoryGeneration) continue;
            // A newer stream delta may have overtaken this REST snapshot.
            if (Math.max(itemDeltas.get(name) ?? 0, temperatureNotifications.get(name) ?? 0) > start) { pendingTemperatureReads.add(name); continue; }
            if (row?.name !== name || typeof row.state !== 'string') continue;
            if (applyUpdateEvidence(name, row.lastStateUpdate, row.state)) {
              evidenceDeltas.set(name, ++sequence); itemDeltas.set(name, sequence);
            }
          } catch {
            // Keep the last verified source clock. A later notification may
            // retry; failed or timed-out reads never renew freshness.
          }
        }
      } finally { activeTemperatureReads.delete(name); }
    })();
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
          ++sequence;
          if (TEMPERATURE_ITEMS.some(item => item.name === name)) {
            temperatureNotifications.set(name, sequence);
            // The live OpenHAB stateupdated event can pair a new temperature
            // value with its previous update time. Use it only as a trigger
            // for an atomic REST state/clock read, never as source evidence.
            refreshTemperatureEvidence(name);
          } else {
            itemDeltas.set(name, sequence);
            evidenceDeltas.set(name, sequence);
            applyUpdateEvidence(name, timestamp, state);
          }
        },
        onThingStatus: (uid, status) => { if (active && applyThingStatus(uid, status)) thingDeltas.set(uid, ++sequence); },
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
