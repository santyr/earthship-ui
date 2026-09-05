import { TEMPERATURE_ITEMS } from '../alerts/staleness.js';

export function parseUpdateEvidenceSSEMessage(raw) {
  let message;
  try { message = JSON.parse(raw); } catch { return null; }
  const match = /^openhab\/items\/([^/]+)\/stateupdated$/.exec(message?.topic || '');
  if (!match || !TEMPERATURE_ITEMS.some(item => item.name === match[1])) return null;
  let payload;
  try { payload = JSON.parse(message.payload); } catch { payload = null; }
  return { name: match[1], lastStateUpdate: payload?.lastStateUpdate };
}

export function parseSSEMessage(raw) {
  let msg;
  try { msg = JSON.parse(raw); } catch { return null; }
  const m = /^openhab\/items\/([^/]+)\/statechanged$/.exec(msg.topic || '');
  if (!m) return null;
  let payload;
  try { payload = JSON.parse(msg.payload); } catch { return null; }
  if (payload.value === undefined) return null;
  return { name: m[1], value: String(payload.value) };
}

export function parseThingStatusSSEMessage(raw) {
  let msg;
  try { msg = JSON.parse(raw); } catch { return null; }
  const match = /^openhab\/things\/(.+)\/status$/.exec(msg.topic || '');
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
    ...TEMPERATURE_ITEMS.map(item => `openhab/items/${item.name}/stateupdated`)].join(',');
  const url = `${base}/rest/events?topics=${encodeURIComponent(topics)}`;
  let es = null, backoff = 1000, staleTimer = null, offlineTimer = null, stopped = false;
  let reconnectTimer = null, lastStatus = null, hasOpened = false;
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
    // EventSource cannot set an Authorization header, so openHAB's SSE auth is
    // delegated to the same-origin Vite proxy in household deployments. Keep
    // token-in-query only for explicit direct-OpenHAB development configs.
    const eventUrl = apiToken ? `${url}&accessToken=${encodeURIComponent(apiToken)}` : url;
    es = new EventSource(eventUrl);
    es.onopen = () => {
      backoff = 1000;
      // Items that changed while the stream was down never replay as
      // statechanged events, so every open AFTER the first one triggers a
      // snapshot resync. The very first open is skipped: the caller has just
      // fetched the boot snapshot (no double-fetch storm at startup).
      const isReconnect = hasOpened;
      hasOpened = true;
      setStatus('live');
      armTimers();
      if (isReconnect) onReconnect();
    };
    es.onmessage = (e) => {
      const update = parseUpdateEvidenceSSEMessage(e.data);
      if (update) {
        onUpdateEvidence(update.name, update.lastStateUpdate);
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
      es.close();
      if (stopped) return;
      reconnectTimer = setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 30000);
    };
  }
  return {
    start() { stopped = false; backoff = 1000; hasOpened = false; connect(); },
    stop() {
      stopped = true;
      clearTimeout(staleTimer); clearTimeout(offlineTimer); clearTimeout(reconnectTimer);
      if (es) es.close();
      lastStatus = null;
    },
  };
}
