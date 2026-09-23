// Read-only cutover snapshot from energy_analytics.daily_battery, captured
// 2026-09-23. The legacy series is frozen at the qualified-power cutover;
// it is not part of qualified observed throughput or a BMS lifetime counter.
export const PRIOR_EFC_ESTIMATE = Object.freeze({
  epochId: 'discover_4_module_2026',
  firstDate: '2026-07-19',
  throughDate: '2026-09-19',
  days: 63,
  insufficientDataDays: 1,
  estimateEfc: 9.80900604534,
});

export function priorEfcEstimateFor(result) {
  const baseline = PRIOR_EFC_ESTIMATE;
  if (!result?.accounting || result.epochId !== baseline.epochId
      || result.accounting.windowStart <= baseline.throughDate
      || result.accounting.policy !== 'qualified_power_evidence_v1') return null;
  return baseline;
}
