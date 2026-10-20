import { withReadTimeout, READ_TIMEOUT_MS } from './readRequest.js';

export const MAX_HISTORY_RESPONSE_BYTES = 5 * 1024 * 1024;
export const MAX_HISTORY_ROWS = 300_000;

export class HistoryResponseError extends Error {
  constructor(message, code) {
    super(message);
    this.name = 'HistoryResponseError';
    this.code = code;
  }
}

async function readBoundedJson(response, signal) {
  const declared = Number(response.headers?.get?.('content-length'));
  if (Number.isFinite(declared) && declared > MAX_HISTORY_RESPONSE_BYTES) {
    throw new HistoryResponseError('History response is too large', 'history-response-too-large');
  }

  if (response.body?.getReader) {
    const reader = response.body.getReader();
    const cancel = () => { Promise.resolve(reader.cancel(signal.reason)).catch(() => {}); };
    signal?.addEventListener('abort', cancel, { once: true });
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
      signal?.removeEventListener('abort', cancel);
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

export function createClient({ openhabUrl, apiToken, readTimeoutMs = READ_TIMEOUT_MS }) {
  const h = apiToken ? { Authorization: `Bearer ${apiToken}` } : {};
  const base = openhabUrl.replace(/\/$/, '');
  const read = (path, label, options = {}, parse = response => response.json()) => withReadTimeout(async signal => {
    const response = await fetch(`${base}${path}`, { headers: h, signal });
    if (signal.aborted) throw signal.reason;
    if (!response.ok) throw new Error(`${label} ${response.status}`);
    return parse(response, signal);
  }, { signal: options.signal, timeoutMs: options.timeoutMs ?? readTimeoutMs });
  const collection = async (path, label, options) => {
    const rows = await read(path, label, options);
    const key = label === 'getAllItems' ? 'name' : 'UID';
    if (!Array.isArray(rows) || rows.some(row => typeof row?.[key] !== 'string' || !row[key])) {
      throw new Error(`${label} invalid snapshot`);
    }
    return rows;
  };
  return {
    getAllItems(options = {}) {
      return collection('/rest/items?fields=name,state,type,lastStateUpdate', 'getAllItems', options);
    },
    getAllThings(options = {}) {
      return collection('/rest/things', 'getAllThings', options);
    },
    getItem(name, options = {}) {
      return read(`/rest/items/${encodeURIComponent(name)}`, `getItem ${name}`, options);
    },
    async sendCommand(name, value) {
      const r = await fetch(`${base}/rest/items/${encodeURIComponent(name)}`, {
        method: 'POST', headers: { ...h, 'Content-Type': 'text/plain' }, body: String(value) });
      if (!r.ok) throw new Error(`sendCommand ${name} ${r.status}`);
    },
    async getHistory(name, { starttime, endtime, signal, timeoutMs, includeStartState = false } = {}) {
      let startMs;
      let endMs;
      if (includeStartState) {
        const qualified = (value) => typeof value === 'string'
          && /^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value);
        startMs = qualified(starttime) ? Date.parse(starttime) : NaN;
        endMs = qualified(endtime) ? Date.parse(endtime) : NaN;
        if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) {
          throw new HistoryResponseError('Invalid state history window', 'invalid-history-window');
        }
        if (startMs === endMs) return [];
      }
      const q = new URLSearchParams({ starttime, endtime });
      if (includeStartState) q.set('boundary', 'true');
      const d = await read(`/rest/persistence/items/${encodeURIComponent(name)}?${q}`, `getHistory ${name}`,
        { signal, timeoutMs }, readBoundedJson);
      if (!Array.isArray(d?.data)) {
        throw new HistoryResponseError('Malformed history response data', 'invalid-history-response');
      }
      if (d.data.length > MAX_HISTORY_ROWS) {
        throw new HistoryResponseError('History response has too many rows', 'history-row-limit');
      }
      const rows = includeStartState
        ? d.data.filter((point) => typeof point?.time === 'number'
          && Number.isFinite(point.time) && point.time >= startMs && point.time < endMs)
        : d.data;
      return rows.map((point) => ({
        time: point?.time,
        state: point?.state,
        ...(point?.unit == null ? {} : { unit: point.unit }),
      }));
    },
  };
}
