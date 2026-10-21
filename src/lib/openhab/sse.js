import { TEMPERATURE_ITEMS } from '../alerts/staleness.js';
import { ASTRO_EVIDENCE_ITEMS } from '../weather/astroPresentation.js';
const EVIDENCE_ITEMS = [...TEMPERATURE_ITEMS.map(item => item.name), ...ASTRO_EVIDENCE_ITEMS];

export function parseUpdateEvidenceSSEMessage(raw) {
  let message;
  try { message = JSON.parse(raw); } catch { return null; }
  const match = /^openhab\/items\/([^/]+)\/stateupdated$/.exec(message?.topic || '');
  if (!match || !EVIDENCE_ITEMS.includes(match[1])) return null;
  let payload;
  try { payload = JSON.parse(message.payload); } catch { payload = null; }
  return { name: match[1], lastStateUpdate: payload?.lastStateUpdate,
    state: payload?.value == null ? undefined : String(payload.value) };
}

export function parseSSEMessage(raw) {
  let msg;
  try { msg = JSON.parse(raw); } catch { return null; }
  const m = /^openhab\/items\/([^/]+)\/statechanged$/.exec(msg?.topic || '');
  if (!m) return null;
  let payload;
  try { payload = JSON.parse(msg.payload); } catch { return null; }
  if (payload?.value === undefined) return null;
  return { name: m[1], value: String(payload.value) };
}

export function parseThingStatusSSEMessage(raw) {
  let msg;
  try { msg = JSON.parse(raw); } catch { return null; }
  const match = /^openhab\/things\/(.+)\/status$/.exec(msg?.topic || '');
  if (!match) return null;

  let payload;
  try { payload = JSON.parse(msg.payload); } catch { return null; }
  const rawStatus = payload?.status ?? payload?.value;
  if (typeof rawStatus !== 'string' || !rawStatus.trim()) return null;

  return {
    uid: match[1],
    statusInfo: {
      status: rawStatus.trim().toUpperCase(),
      statusDetail: typeof payload.statusDetail === 'string'
        ? payload.statusDetail.trim().toUpperCase()
        : '',
      description: typeof payload.description === 'string'
        ? payload.description.trim()
        : '',
    },
  };
}

export function createSSE({
  openhabUrl, apiToken, onState, onThingStatus = () => {}, onStatus,
  onReconnect = () => {}, onUpdateEvidence = () => {}, staleSeconds = 90,
}) {
  const base = openhabUrl.replace(/\/$/, '');
  const topics = ['openhab/items/*/statechanged', 'openhab/things/*/status',
    ...EVIDENCE_ITEMS.map(name => `openhab/items/${name}/stateupdated`)].join(',');
  const url = `${base}/rest/events?topics=${encodeURIComponent(topics)}`;
  let es = null, backoff = 1000, staleTimer = null, offlineTimer = null, stopped = false;
  let reconnectTimer = null, lastStatus = null;
  function setStatus(s) {
    if (s !== lastStatus) { lastStatus = s; onStatus(s); }
  }
  function armTimers() {
    clearTimeout(staleTimer); clearTimeout(offlineTimer);
    staleTimer = setTimeout(() => setStatus('stale'), staleSeconds * 1000);
    offlineTimer = setTimeout(() => setStatus('offline'), 10 * 60 * 1000);
  }
  function connect() {
    clearTimeout(reconnectTimer);
    if (stopped) return;
    if (es) { es.close(); }
    setStatus('connecting');
    // EventSource cannot set an Authorization header, so openHAB's SSE auth is
    // delegated to the same-origin Vite proxy in household deployments. Keep
    // token-in-query only for explicit direct-OpenHAB development configs.
    const eventUrl = apiToken ? `${url}&accessToken=${encodeURIComponent(apiToken)}` : url;
    es = new EventSource(eventUrl);
    const source = es;
    const isCurrent = () => !stopped && es === source;
    es.onopen = () => {
      if (!isCurrent()) return;
      backoff = 1000;
      // Reconcile even the first open: changes between the boot snapshot and
      // stream subscription are not replayed by OpenHAB.
      onReconnect();
      setStatus('live');
      armTimers();
    };
    es.onmessage = (e) => {
      if (!isCurrent()) return;
      const update = parseUpdateEvidenceSSEMessage(e.data);
      if (update) {
        onUpdateEvidence(update.name, update.lastStateUpdate, update.state);
        setStatus('live');
        armTimers();
        return;
      }
      const itemState = parseSSEMessage(e.data);
      if (itemState) {
        onState(itemState.name, itemState.value);
        setStatus('live');
        armTimers();
        return;
      }
      const thingStatus = parseThingStatusSSEMessage(e.data);
      if (thingStatus) {
        onThingStatus(thingStatus.uid, thingStatus.statusInfo);
        setStatus('live');
        armTimers();
      }
    };
    es.onerror = () => {
      if (!isCurrent()) return;
      source.close();
      es = null;
      clearTimeout(staleTimer); clearTimeout(offlineTimer);
      setStatus('connecting');
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 30000);
    };
  }
  return {
    start() { stopped = false; backoff = 1000; clearTimeout(staleTimer); clearTimeout(offlineTimer); connect(); },
    stop() {
      stopped = true;
      clearTimeout(staleTimer); clearTimeout(offlineTimer); clearTimeout(reconnectTimer);
      if (es) es.close();
      es = null;
      lastStatus = null;
    },
  };
}
