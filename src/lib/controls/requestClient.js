import { items as liveItems, getClientOnce } from '../openhab/index.js';
import { REQUEST_POST_ITEMS } from './catalog.js';

// Re-exported so proxyPolicy.js can source the POST allowlist from the request
// client surface (the canonical list lives in catalog.js — no svelte-store
// import is pulled into the Vite config graph through this path).
export { REQUEST_POST_ITEMS };

// The correlated request client never retries and never re-POSTs. A single
// request is posted, the matching result item is awaited, and the outcome is
// resolved once — confirmed on a terminal success, error on a rule rejection,
// unknown on timeout or a transport break that may have reached openHAB.
export const REQUEST_TIMEOUT_MS = 30_000;

// Feeder posts 'complete'; greywater and night-load post 'completed'. Both are
// terminal success. 'denied'/'failed' are terminal rejections. 'accepted' and
// 'running' are non-terminal and keep the request pending.
const SUCCESS_STATUSES = new Set(['complete', 'completed']);
const FAILURE_STATUSES = new Set(['denied', 'failed']);

// A non-2xx POST is an explicit rejection (openHAB refused the request); the
// client.sendCommand contract throws `sendCommand <item> <status>`.
const EXPLICIT_REJECTION_RE = /sendCommand\s+\S+\s+\d{3}/;

function terminalPhaseFor(status) {
  const normalized = String(status ?? '').trim().toLowerCase();
  if (SUCCESS_STATUSES.has(normalized)) return 'confirmed';
  if (FAILURE_STATUSES.has(normalized)) return 'error';
  return null;
}

function parseResult(raw) {
  if (typeof raw !== 'string' || raw.length === 0) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || typeof parsed.requestId !== 'string') return null;
    return parsed;
  } catch {
    return null;
  }
}

function newRequestId() {
  const uuid = globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  return `ui-${uuid}`;
}

// requestedAt MUST be current time — the owner rules deny anything outside the
// staleness window with reason 'request_stale'.
export function buildRequestPayload(extras = {}) {
  return {
    requestId: newRequestId(),
    requestedAt: new Date().toISOString(),
    ...extras,
  };
}

export function submitControlRequest(control, payloadExtras = {}, deps = {}) {
  const {
    client = getClientOnce(),
    items = liveItems,
    timeoutMs = REQUEST_TIMEOUT_MS,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
  } = deps;

  const payload = buildRequestPayload(payloadExtras);
  const body = JSON.stringify(payload);

  return new Promise((resolve) => {
    let settled = false;
    let unsubscribe = () => {};
    let timer = null;

    const finish = (result) => {
      if (settled) return;
      settled = true;
      if (timer !== null) clearTimer(timer);
      unsubscribe();
      resolve(result);
    };

    // Subscribe before POSTing so a fast result is never missed. A fresh
    // requestId guarantees the synchronous initial emit cannot match.
    unsubscribe = items.subscribe((snapshot) => {
      if (settled) return;
      const parsed = parseResult(snapshot?.[control.resultItem]);
      if (!parsed || parsed.requestId !== payload.requestId) return;
      const phase = terminalPhaseFor(parsed.status);
      if (!phase) return; // accepted/running — keep waiting
      finish({ phase, reason: String(parsed.reason ?? '') });
    });

    timer = setTimer(() => finish({ phase: 'unknown', reason: 'Outcome unknown' }), timeoutMs);

    if (!client?.sendCommand) {
      finish({ phase: 'unknown', reason: 'Outcome unknown' });
      return;
    }

    const handlePostError = (error) => {
      if (EXPLICIT_REJECTION_RE.test(String(error?.message ?? ''))) {
        finish({ phase: 'error', reason: 'request_rejected' });
      } else {
        // A transport break after POST may still have reached openHAB, so it is
        // deliberately uncertain and never retried.
        finish({ phase: 'unknown', reason: 'Outcome unknown' });
      }
    };

    try {
      Promise.resolve(client.sendCommand(control.requestItem, body)).catch(handlePostError);
    } catch (error) {
      handlePostError(error);
    }
  });
}
