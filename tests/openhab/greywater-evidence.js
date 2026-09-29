export function socEvidence(soc, recordedAt) {
  const observedAt = recordedAt - 1000;
  return JSON.stringify({
    version: 1, streamEpoch: 'aa1f3b9e-147b-4ac0-a69d-1287831fc19c',
    recordedAt, status: 'valid', reason: 'ok', observedAt,
    scaleObservedAt: observedAt, validUntil: observedAt + 120000, soc,
  });
}

// Test-only model of a healthy receipt producer. Explicit receipt overrides
// remain untouched, so stale/missing evidence tests can exercise fail-closed.
export function withGreywaterSocEvidence(h, overrides = {}) {
  if (Object.hasOwn(overrides, 'BMS_SOC_Evidence_JSON')) return h;
  const execute = h.execute;
  h.execute = event => {
    const soc = Number(h.state('BMS_SOC'));
    h.setState('BMS_SOC_Evidence_JSON', Number.isFinite(soc)
      ? socEvidence(soc, h.nowMs()) : 'NULL');
    return execute(event);
  };
  return h;
}
