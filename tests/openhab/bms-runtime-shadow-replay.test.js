import { describe, expect, it } from 'vitest';
import { replayRuntime } from '../../openhab/scripts/bms_runtime_shadow_replay.mjs';

const at = 1800000000000;
const field = (value, ttl, property = 'value', observedAt = at) => ({
  status: 'valid', reason: 'ok', observedAt, validUntil: observedAt + ttl, [property]: value,
});
const row = (value, time = at) => ({ time, state: typeof value === 'string' ? value : JSON.stringify(value) });
function histories() {
  return {
    BMS_SOC_Evidence_JSON: [row({ version: 1, streamEpoch: 'soc', recordedAt: at,
      status: 'valid', reason: 'ok', observedAt: at, scaleObservedAt: at,
      validUntil: at + 120000, soc: 80 })],
    BMS_Aux_Evidence_JSON: [row({ version: 1, basis: 'discover_bms_190_native_aux_v1',
      streamEpoch: 'aux', sequence: 1, recordedAt: at,
      fields: { 'battery.remaining_ah': field(320, 120000) } })],
    BMS_Runtime_Input_Evidence_JSON: [row({ version: 1, basis: 'native_runtime_inputs_v1',
      streamEpoch: 'runtime', sequence: 1, recordedAt: at, fields: {
        'battery.dc_current_ca': field(-300, 90000),
        'battery.dc_voltage_cv': field(5000, 90000),
        'battery.ttd_min': field(500, 120000),
        'battery.ttf_min': field(0, 120000),
      } })],
    Power_Evidence_JSON: [row({ version: 1, streamEpoch: 'pv', sequence: 1,
      recordedAt: at, fields: { 'pv.input_power_w': field(500, 120000, 'watts') } })],
    Inverter_AC_Evidence_JSON: [row({ version: 1, basis: 'inverter_output',
      streamEpoch: 'ac', sequence: 1, recordedAt: at,
      fields: { 'inverter.ac_output_w': field(150, 30000, 'watts') } }),
    row({ version: 1, basis: 'inverter_output', streamEpoch: 'ac', sequence: 2,
      recordedAt: at + 30000, fields: {
        'inverter.ac_output_w': field(150, 30000, 'watts', at + 30000),
      } }, at + 30000)],
    Sun_Position_Elevation: [row('30')],
    BMS_Runtime_Basis: [row('bms')],
    BMS_TimeToDischarge_Smoothed: [row('500')],
    BMS_TimeToFull_Smoothed: [row('0')],
  };
}

describe('bounded read-only runtime estimator replay', () => {
  it('does not count duplicate cron reads as distinct deep current observations', () => {
    const h = histories();
    const result = replayRuntime(h, { startMs: at, endMs: at + 30000 });
    expect(result.ticks).toBe(2);
    expect(result.candidateBasisTicks.bms || 0).toBe(0);
    expect(result.candidateBasisTicks.evening).toBe(2);
    expect(result.firstNonOffAt).toBe(new Date(at).toISOString());
    expect(result.disagreementPairs['bms -> evening']).toEqual({
      ticks: 2, firstAt: new Date(at).toISOString(), lastAt: new Date(at + 30000).toISOString(),
    });
    expect(result.firstBasisDisagreements).toHaveLength(2);
    expect(result.ttfReversalViolations).toEqual([]);
    expect(result.overnightLoadInputs['2027-01-14']).toEqual({ source: 'rule_fallback_155w', watts: 155 });
  });

  it('uses an explicitly audited completed-night load without claiming Java parity', () => {
    const h = histories();
    const fallback = replayRuntime(h, { startMs: at, endMs: at });
    const audited = replayRuntime(h, { startMs: at, endMs: at,
      nightLoadByDay: { '2027-01-14': 200 } });
    expect(audited.candidateBasisTicks).toEqual(fallback.candidateBasisTicks);
    expect(audited.overnightLoadInputs['2027-01-14']).toEqual({
      source: 'as_persisted_weighted_diagnostic', watts: 200,
    });
    expect(Number(audited.lastCandidate.ttdMin)).toBeLessThan(Number(fallback.lastCandidate.ttdMin));
    expect(audited.caveat).toContain('not source-fresh or proven equivalent');
  });

  it('rejects malformed or unbounded night-load injections', () => {
    const h = histories();
    for (const nightLoadByDay of [null, [], { '2027-01-14': -1 },
      { '2027-01-14': Infinity }, { '2027-01-14': 20001 }, { bogus: 150 },
      { '2027-01-14': 150, '2027-01-15': 160, '2027-01-16': 170 }]) {
      expect(() => replayRuntime(h, { startMs: at, endMs: at, nightLoadByDay }))
        .toThrow('invalid bounded night-load');
    }
  });

  it('admits BMS after a second naturally persisted current observation', () => {
    const h = histories();
    const r = JSON.parse(h.BMS_Runtime_Input_Evidence_JSON[0].state);
    r.sequence = 2; r.recordedAt = at + 30000;
    r.fields['battery.dc_current_ca'] = field(-300, 90000, 'value', at + 30000);
    h.BMS_Runtime_Input_Evidence_JSON.push(row(r, at + 30000));
    const result = replayRuntime(h, { startMs: at, endMs: at + 30000 });
    expect(result.candidateBasisTicks).toEqual({ evening: 1, bms: 1 });
    expect(result.lastCandidate.basis).toBe('bms');
  });

  it('rejects unbounded, unordered and future-only histories', () => {
    const h = histories();
    expect(() => replayRuntime(h, { startMs: at, endMs: at + 4 * 3600000 + 1 })).toThrow('bounded');
    h.Power_Evidence_JSON.push(row('future', at - 1));
    expect(() => replayRuntime(h, { startMs: at, endMs: at + 30000 })).toThrow('unordered');
    h.Power_Evidence_JSON = [row('future', at + 30001)];
    const result = replayRuntime(h, { startMs: at, endMs: at });
    expect(result.candidateBasisTicks.evening).toBe(1);
    expect(result.firstNonOffAt).toBe(new Date(at).toISOString());
  });

  it('counts every disagreement even when the example list is capped', () => {
    const h = histories();
    const result = replayRuntime(h, { startMs: at, endMs: at + 10 * 60000 });
    expect(result.firstBasisDisagreements).toHaveLength(12);
    expect(Object.values(result.disagreementPairs).reduce((sum, pair) => sum + pair.ticks, 0))
      .toBeGreaterThan(12);
  });
});
