import { describe, expect, it } from 'vitest';
import { PRIOR_EFC_ESTIMATE, priorEfcEstimateFor } from '../src/lib/energy/priorEfcEstimate.js';

describe('dated prior EFC estimate', () => {
  it('retains the verified pre-cutover bank-epoch snapshot separately', () => {
    expect(PRIOR_EFC_ESTIMATE).toEqual({
      epochId: 'discover_4_module_2026', firstDate: '2026-07-19',
      throughDate: '2026-09-19', days: 63, insufficientDataDays: 1,
      estimateEfc: 9.80900604534,
    });
  });

  it('shows only alongside a later qualified window in the same bank epoch', () => {
    const result = { epochId: PRIOR_EFC_ESTIMATE.epochId,
      accounting: { policy: 'qualified_power_evidence_v1', windowStart: '2026-09-20' } };
    expect(priorEfcEstimateFor(result)).toBe(PRIOR_EFC_ESTIMATE);
    expect(priorEfcEstimateFor({ ...result, epochId: 'replacement-bank' })).toBeNull();
    expect(priorEfcEstimateFor({ ...result, accounting: { ...result.accounting,
      windowStart: '2026-09-19' } })).toBeNull();
    expect(priorEfcEstimateFor({ ...result, accounting: { ...result.accounting,
      policy: 'different-policy' } })).toBeNull();
    expect(priorEfcEstimateFor({ ...result, accounting: null })).toBeNull();
  });
});
