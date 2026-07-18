export const MAX_HISTORY_RESPONSE_BYTES = 5 * 1024 * 1024;
export const MAX_HISTORY_ROWS = 300_000;

export class HistoryResponseError extends Error {
  constructor(message, code) {
    super(message);
    this.name = 'HistoryResponseError';
    this.code = code;
  }
}

async function readBoundedJson(response) {
  const declared = Number(response.headers?.get?.('content-length'));
  if (Number.isFinite(declared) && declared > MAX_HISTORY_RESPONSE_BYTES) {
    throw new HistoryResponseError('History response is too large', 'history-response-too-large');
  }

  if (response.body?.getReader) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let bytes = 0;
    let text = '';
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        bytes += value?.byteLength || 0;
        if (bytes > MAX_HISTORY_RESPONSE_BYTES) {
          await reader.cancel();
          throw new HistoryResponseError('History response is too large', 'history-response-too-large');
        }
        text += decoder.decode(value, { stream: true });
      }
      text += decoder.decode();
      return JSON.parse(text);
    } finally {
      reader.releaseLock?.();
    }
  }

  if (typeof response.arrayBuffer === 'function') {
    const buffer = await response.arrayBuffer();
    if (!(buffer instanceof ArrayBuffer)) {
      throw new HistoryResponseError(
        'History response body cannot be bounded safely',
        'history-response-unbounded',
      );
    }
    if (buffer.byteLength > MAX_HISTORY_RESPONSE_BYTES) {
      throw new HistoryResponseError('History response is too large', 'history-response-too-large');
    }
    return JSON.parse(new TextDecoder().decode(buffer));
  }

  if (typeof response.text === 'function') {
    const text = await response.text();
    if (typeof text !== 'string') {
      throw new HistoryResponseError(
        'History response body cannot be bounded safely',
        'history-response-unbounded',
      );
    }
    const encodedBytes = new TextEncoder().encode(text).byteLength;
    if (encodedBytes > MAX_HISTORY_RESPONSE_BYTES) {
      throw new HistoryResponseError('History response is too large', 'history-response-too-large');
    }
    return JSON.parse(text);
  }

  throw new HistoryResponseError(
    'History response body cannot be bounded safely',
    'history-response-unbounded',
  );
}

export function createClient({ openhabUrl, apiToken }) {
  const h = apiToken ? { Authorization: `Bearer ${apiToken}` } : {};
  const base = openhabUrl.replace(/\/$/, '');
  return {
    async getAllItems() {
      const r = await fetch(`${base}/rest/items?fields=name,state,type`, { headers: h });
      if (!r.ok) throw new Error(`getAllItems ${r.status}`);
      return r.json();
    },
    async getAllThings() {
      const r = await fetch(`${base}/rest/things`, { headers: h });
      if (!r.ok) throw new Error(`getAllThings ${r.status}`);
      return r.json();
    },
    async getItem(name) {
      const r = await fetch(`${base}/rest/items/${encodeURIComponent(name)}`, { headers: h });
      if (!r.ok) throw new Error(`getItem ${name} ${r.status}`);
      return r.json();
    },
    async sendCommand(name, value) {
      const r = await fetch(`${base}/rest/items/${encodeURIComponent(name)}`, {
        method: 'POST', headers: { ...h, 'Content-Type': 'text/plain' }, body: String(value) });
      if (!r.ok) throw new Error(`sendCommand ${name} ${r.status}`);
    },
    async getHistory(name, { starttime, endtime, signal } = {}) {
      const q = new URLSearchParams({ starttime, endtime });
      const r = await fetch(`${base}/rest/persistence/items/${encodeURIComponent(name)}?${q}`, {
        headers: h,
        signal,
      });
      if (!r.ok) throw new Error(`getHistory ${name} ${r.status}`);
      const d = await readBoundedJson(r);
      if (!Array.isArray(d?.data)) {
        throw new HistoryResponseError('Malformed history response data', 'invalid-history-response');
      }
      if (d.data.length > MAX_HISTORY_ROWS) {
        throw new HistoryResponseError('History response has too many rows', 'history-row-limit');
      }
      return d.data.map((point) => ({
        time: point?.time,
        state: point?.state,
        ...(point?.unit == null ? {} : { unit: point.unit }),
      }));
    },
  };
}
