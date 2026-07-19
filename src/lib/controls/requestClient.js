import { items as liveItems, getClientOnce } from '../openhab/index.js';
import { controlIdFor } from './catalog.js';
import { recordControlOutcome } from './outcomeStore.js';

// The correlated request client never retries and never re-POSTs. A single
// request is posted and the matching result item is awaited. The submission
// resolves once, at the first terminal phase for the UI:
//   - 'confirmed' when the rule posts a terminal success (complete/completed)
//   - 'error' when the rule rejects (denied/failed)
//   - 'accepted' when the rule posts accepted/running — the request is sent and
//     owned by the rule but not yet confirmed. An approved greywater cycle
//     completes at ~5 min, far past the pre-accept window, so treating accepted
//     as terminal is what keeps a successful submission from surfacing as
//     "Outcome unknown".
//   - 'unknown' on the pre-accept timeout or a transport break that may have
//     reached openHAB.
// After an 'accepted' resolution a bounded background listener keeps watching
// the result item and upgrades the recorded outcome to confirmed/error when the
// terminal result finally lands (via the outcomeStore record path — a later
// transitionAt wins). It never issues a second POST.
export const REQUEST_TIMEOUT_MS = 30_000;
export const BACKGROUND_TIMEOUT_MS = 6 * 60_000;

// Feeder posts 'complete'; greywater and night-load post 'completed'. Both are
// terminal success. 'denied'/'failed' are terminal rejections. 'accepted' and
// 'running' resolve the submission as sent-unconfirmed (phase 'accepted').
const SUCCESS_STATUSES = new Set(['complete', 'completed']);
const FAILURE_STATUSES = new Set(['denied', 'failed']);
const ACCEPTED_STATUSES = new Set(['accepted', 'running']);

// A non-2xx POST is an explicit rejection (openHAB refused the request); the
// client.sendCommand contract throws `sendCommand <item> <status>`.
const EXPLICIT_REJECTION_RE = /sendCommand\s+\S+\s+\d{3}/;

// Classifies a result status into a UI phase and whether it is terminal for the
// background listener (confirmed/error tear the listener down; accepted keeps it
// alive for a possible upgrade).
function classifyStatus(status) {
  const normalized = String(status ?? '').trim().toLowerCase();
  if (SUCCESS_STATUSES.has(normalized)) return { phase: 'confirmed', terminal: true };
  if (FAILURE_STATUSES.has(normalized)) return { phase: 'error', terminal: true };
  if (ACCEPTED_STATUSES.has(normalized)) return { phase: 'accepted', terminal: false };
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
    backgroundTimeoutMs = BACKGROUND_TIMEOUT_MS,
    setTimer = setTimeout,
    clearTimer = clearTimeout,
    recordOutcome = recordControlOutcome,
    now = Date.now,
  } = deps;

  const payload = buildRequestPayload(payloadExtras);
  const body = JSON.stringify(payload);

  return new Promise((resolve) => {
    let settled = false; // the submission promise has resolved
    let finished = false; // the subscription/timers have been torn down
    let unsubscribe = () => {};
    let timer = null;

    const teardown = () => {
      if (finished) return;
      finished = true;
      if (timer !== null) clearTimer(timer);
      unsubscribe();
    };

    const settle = (result) => {
      if (settled) return;
      settled = true;
      resolve(result);
    };

    const recordUpgrade = (phase, reason) => {
      if (typeof recordOutcome !== 'function') return;
      try {
        recordOutcome({
          controlId: controlIdFor(control),
          controlLabel: control.label ?? controlIdFor(control),
          phase,
          reason,
          transitionAt: now(),
        });
      } catch {
        // The outcome store is best-effort; the submission already resolved.
      }
    };

    // Subscribe before POSTing so a fast result is never missed. A fresh
    // requestId guarantees the synchronous initial emit cannot match.
    unsubscribe = items.subscribe((snapshot) => {
      if (finished) return;
      const parsed = parseResult(snapshot?.[control.resultItem]);
      if (!parsed || parsed.requestId !== payload.requestId) return;
      const classified = classifyStatus(parsed.status);
      if (!classified) return;
      const reason = String(parsed.reason ?? '');

      if (classified.terminal) {
        // confirmed/error is terminal for both the promise and the background.
        if (settled) recordUpgrade(classified.phase, reason);
        else settle({ phase: classified.phase, reason });
        teardown();
        return;
      }

      // accepted/running — resolve the submission now, then keep a bounded
      // background listener alive for a confirmed/error upgrade.
      if (!settled) {
        settle({ phase: 'accepted', reason });
        if (timer !== null) clearTimer(timer);
        timer = setTimer(teardown, backgroundTimeoutMs);
      }
    });

    timer = setTimer(() => {
      settle({ phase: 'unknown', reason: 'Outcome unknown' });
      teardown();
    }, timeoutMs);

    if (!client?.sendCommand) {
      settle({ phase: 'unknown', reason: 'Outcome unknown' });
      teardown();
      return;
    }

    const handlePostError = (error) => {
      if (settled) return; // a break after the result landed changes nothing
      if (EXPLICIT_REJECTION_RE.test(String(error?.message ?? ''))) {
        settle({ phase: 'error', reason: 'request_rejected' });
      } else {
        // A transport break after POST may still have reached openHAB, so it is
        // deliberately uncertain and never retried.
        settle({ phase: 'unknown', reason: 'Outcome unknown' });
      }
      teardown();
    };

    try {
      Promise.resolve(client.sendCommand(control.requestItem, body)).catch(handlePostError);
    } catch (error) {
      handlePostError(error);
    }
  });
}
