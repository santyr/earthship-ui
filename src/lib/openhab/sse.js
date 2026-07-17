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

export function createSSE({ openhabUrl, apiToken, onState, onStatus, staleSeconds = 90 }) {
  const base = openhabUrl.replace(/\/$/, '');
  const url = `${base}/rest/events?topics=openhab/items/*/statechanged`;
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
    if (stopped) return;
    if (es) { es.close(); }
    // EventSource cannot set an Authorization header, so openHAB's SSE auth is
    // done via an accessToken query param instead of a Bearer header. Verified
    // live against openHAB (see task-1.3-report.md): the token-in-query
    // approach is accepted (no 401), so this is not just a fallback guess.
    es = new EventSource(`${url}&accessToken=${encodeURIComponent(apiToken)}`);
    es.onopen = () => { backoff = 1000; setStatus('live'); armTimers(); };
    es.onmessage = (e) => {
      const parsed = parseSSEMessage(e.data);
      if (parsed) { onState(parsed.name, parsed.value); setStatus('live'); armTimers(); }
    };
    es.onerror = () => {
      es.close();
      if (stopped) return;
      reconnectTimer = setTimeout(connect, backoff);
      backoff = Math.min(backoff * 2, 30000);
    };
  }
  return {
    start() { stopped = false; connect(); },
    stop() {
      stopped = true;
      clearTimeout(staleTimer); clearTimeout(offlineTimer); clearTimeout(reconnectTimer);
      if (es) es.close();
      lastStatus = null;
    },
  };
}
