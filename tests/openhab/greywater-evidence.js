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


// Existing owner regressions assume healthy live Astro alongside healthy BMS.
// The dedicated freshness suite supplies timestamps/bounds explicitly instead.
export function withGreywaterEvidence(h, overrides = {}) {
  h = withGreywaterSocEvidence(h, overrides);
  const execute = h.execute;
  h.execute = event => {
    const at = h.nowMs();
    // These broad same-day bounds are fixtures, not a solar calculation.
    const local = new Date(at - 6 * 3600000).toISOString().slice(0, 10);
    if (!Object.hasOwn(overrides, 'Sun_Daylight_Start')) h.setState('Sun_Daylight_Start', `${local}T00:01:00-0600`);
    if (!Object.hasOwn(overrides, 'Sun_Set_Start')) h.setState('Sun_Set_Start', `${local}T23:59:00-0600`);
    h.setThingStatus('astro:sun:local', 'ONLINE');
    h.setLastUpdate('Sun_Position_Elevation', at - 1000);
    return execute(event);
  };
  return h;
}
