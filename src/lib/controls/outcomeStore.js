import { writable } from 'svelte/store';

export const CONTROL_OUTCOME_TTL_MS = 15 * 60_000;

const PHASE_ALIASES = Object.freeze({
  error: 'failed',
  unknown: 'outcome-unknown',
  accepted: 'sent-unconfirmed',
});

function normalize(record, now) {
  const controlId = String(record?.controlId ?? '').trim();
  if (!controlId) throw new TypeError('control outcome requires controlId');
  const rawPhase = String(record?.phase ?? '').trim().toLowerCase();
  const phase = PHASE_ALIASES[rawPhase] ?? rawPhase;
  const transitionAt = Number.isFinite(Number(record?.transitionAt))
    ? Number(record.transitionAt)
    : now();
  return {
    ...record,
    controlId,
    controlLabel: String(record?.controlLabel ?? controlId),
    phase,
    reason: String(record?.reason ?? ''),
    transitionAt,
  };
}

export function createOutcomeStore({
  now = Date.now,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
} = {}) {
  const { subscribe, set } = writable([]);
  const records = new Map();
  let expiryTimer = null;

  function publish() {
    set([...records.values()].sort((a, b) => (
      a.transitionAt - b.transitionAt || a.controlId.localeCompare(b.controlId)
    )));
  }

  function expireAndSchedule() {
    if (expiryTimer !== null) {
      clearTimer(expiryTimer);
      expiryTimer = null;
    }
    const current = now();
    for (const [controlId, record] of records) {
      if (record.transitionAt + CONTROL_OUTCOME_TTL_MS <= current) records.delete(controlId);
    }
    publish();
    const nextExpiry = Math.min(
      Infinity,
      ...[...records.values()].map((record) => record.transitionAt + CONTROL_OUTCOME_TTL_MS),
    );
    if (Number.isFinite(nextExpiry)) {
      expiryTimer = setTimer(expireAndSchedule, Math.max(0, nextExpiry - current));
    }
  }

  return {
    subscribe,
    record(record) {
      const normalized = normalize(record, now);
      const current = records.get(normalized.controlId);
      if (!current || normalized.transitionAt >= current.transitionAt) {
        records.set(normalized.controlId, normalized);
      }
      expireAndSchedule();
      return normalized;
    },
    clear(controlId) {
      records.delete(String(controlId));
      expireAndSchedule();
    },
    reset() {
      records.clear();
      expireAndSchedule();
    },
    destroy() {
      if (expiryTimer !== null) clearTimer(expiryTimer);
      expiryTimer = null;
      records.clear();
      publish();
    },
  };
}

export const controlOutcomes = createOutcomeStore();

export function recordControlOutcome(record) {
  return controlOutcomes.record(record);
}
