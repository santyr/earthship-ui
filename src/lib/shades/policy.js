// Presentation of backend evaluations only. This module cannot authorize,
// schedule or dispatch movement, and never derives policy from browser Items.
const ZONES = ['kitchen', 'living', 'bathroom', 'bedroom'];
const STATUSES = new Set(['automation_off', 'nightly_override', 'policy_unavailable', 'override_unavailable',
  'awaiting_commissioning', 'automation_not_released', 'eligible']);

export function validateShadePolicySnapshot(snapshot) {
  return snapshot?.schemaVersion === 1
    && Number.isSafeInteger(snapshot.generation) && snapshot.generation >= 0
    && typeof snapshot.sessionId === 'string' && snapshot.sessionId.length > 0
    && typeof snapshot.connected === 'boolean'
    && ZONES.every(zone => {
      const entry = snapshot.zones?.[zone];
      return entry && ['ON', 'OFF', null].includes(entry.saved)
        && typeof entry.authoritative === 'boolean' && STATUSES.has(entry.status)
        && typeof entry.label === 'string' && entry.label.length > 0 && entry.label.length <= 160;
    });
}

export function shadePolicyPresentation(snapshot, zone) {
  const valid = validateShadePolicySnapshot(snapshot) && ZONES.includes(zone);
  const entry = valid ? snapshot.zones[zone] : null;
  const confirmed = valid && snapshot.connected && entry.authoritative && entry.saved !== null;
  return {
    checked: confirmed ? entry.saved === 'ON' : 'mixed',
    savedLabel: confirmed ? `Saved ${entry.saved}` : 'Unknown',
    label: confirmed ? entry.label : 'Paused — policy unavailable',
    canSave: Boolean(confirmed),
  };
}

// Allow the backend's sequential, bounded OpenHAB reconciliation to finish,
// while ensuring a lost transport or response body cannot retain confirmation
// or block subsequent polling forever.
export const SHADE_POLICY_REQUEST_TIMEOUT_MS = 30_000;

export function createShadePolicyRequests({ fetchImpl = fetch } = {}) {
  const active = new Set();
  let disposed = false;
  const aborted = message => new DOMException(message, 'AbortError');
  return {
    async request(options = {}) {
      if (disposed) throw aborted('Policy screen unmounted');
      const controller = new AbortController();
      active.add(controller);
      let rejectAbort;
      const cancellation = new Promise((_, reject) => { rejectAbort = reject; });
      const onAbort = () => rejectAbort(controller.signal.reason);
      controller.signal.addEventListener('abort', onAbort, { once: true });
      const timer = setTimeout(() => controller.abort(aborted('Policy request timed out')), SHADE_POLICY_REQUEST_TIMEOUT_MS);
      try {
        const read = (async () => {
          const response = await fetchImpl('/api/shades-policy', { ...options, cache: 'no-store', signal: controller.signal });
          const snapshot = await response.json();
          return { response, snapshot };
        })();
        // Race cancellation through body parsing too. Even a late result from
        // an abort-insensitive transport must never reach the screen.
        return await Promise.race([read, cancellation]);
      } finally {
        clearTimeout(timer);
        controller.signal.removeEventListener('abort', onAbort);
        active.delete(controller);
      }
    },
    dispose() {
      disposed = true;
      for (const controller of active) controller.abort(aborted('Policy screen unmounted'));
    },
  };
}
