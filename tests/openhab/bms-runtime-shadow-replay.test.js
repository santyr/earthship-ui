import { describe, expect, it } from 'vitest';
import { replayRuntime, summarizeMinutes } from '../../openhab/scripts/bms_runtime_shadow_replay.mjs';

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
  it('separates numerical deltas from sentinel and malformed values', () => {
    expect(summarizeMinutes([
      { live: '100.0', candidate: '120' }, { live: '100', candidate: '90' },
      { live: '0.0', candidate: '0' }, { live: '0', candidate: '50' },
      { live: '50', candidate: '0' }, { live: 'NULL', candidate: '0' },
      { live: '', candidate: '0' }, { live: '-1', candidate: '1' },
      { live: '10 minutes', candidate: '10' }, { live: 'Infinity', candidate: '10' },
      { live: '9007199254740992', candidate: '10' },
    ])).toEqual({ positivePairs: 2, bothSentinel: 1, sentinelMismatch: 2,
      invalidPairs: 6, meanDeltaMin: 5, meanAbsDeltaMin: 15, maxAbsDeltaMin: 20 });
    expect(summarizeMinutes([{ live: '0', candidate: '0' }]).meanAbsDeltaMin).toBeNull();
    expect(() => summarizeMinutes(Array(12482).fill({ live: '1', candidate: '1' }))).toThrow('bounded');
  });

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
    expect(result.minuteComparisonByBasisPair['bms -> bms']).toEqual({ ticks: 1,
      ttd: { positivePairs: 1, bothSentinel: 0, sentinelMismatch: 0, invalidPairs: 0,
        meanDeltaMin: 0, meanAbsDeltaMin: 0, maxAbsDeltaMin: 0 },
      ttf: { positivePairs: 0, bothSentinel: 1, sentinelMismatch: 0, invalidPairs: 0,
        meanDeltaMin: null, meanAbsDeltaMin: null, maxAbsDeltaMin: null },
    });
    expect(result.minuteComparisonByBasisPair['bms -> evening'].ticks).toBe(1);
    expect(result.largestMinuteDifferencesByBasisPair['bms -> bms'].ttd).toEqual({
      at: new Date(at + 30000).toISOString(), liveMin: 500, candidateMin: 500, absDeltaMin: 0,
      candidateBmsBufferMin: [500], candidateLastTtdAt: new Date(at).toISOString(),
    });
    expect(result.largestMinuteDifferencesByBasisPair['bms -> bms'].ttf).toBeUndefined();
  });

  it('evaluates intermediate evidence receipts as well as aligned expiry ticks', () => {
    const h = histories();
    for (const [offset, ttd] of [[1000, 6330], [2000, 6818]]) {
      const receipt = JSON.parse(h.BMS_Runtime_Input_Evidence_JSON[0].state);
      receipt.sequence = offset / 1000 + 1; receipt.recordedAt = at + offset;
      receipt.fields['battery.dc_current_ca'] = field(-300, 90000, 'value', at + offset);
      receipt.fields['battery.ttd_min'] = field(ttd, 120000, 'value', at + offset);
      h.BMS_Runtime_Input_Evidence_JSON.push(row(receipt, at + offset));
    }
    const result = replayRuntime(h, { startMs: at, endMs: at + 30000 });
    expect(result.ticks).toBe(4); // seed, two receipt events, cron
    expect(result.candidateBasisTicks).toEqual({ evening: 1, bms: 3 });
    expect(result.lastCandidate.ttdMin).toBe('6818');
    expect(result.evaluationSchedule).toBe('runtime_evidence_updates_and_aligned_30s_expiry');
    expect(Object.values(result.minuteComparisonByBasisPair).reduce((sum, pair) => sum + pair.ticks, 0)).toBe(2);
  });

  it('pinpoints an expired auxiliary source at a fail-closed off tick', () => {
    const h = histories();
    const soc = JSON.parse(h.BMS_SOC_Evidence_JSON[0].state);
    soc.recordedAt = at + 60000;
    soc.observedAt = at + 60000;
    soc.scaleObservedAt = at + 60000;
    soc.validUntil = at + 180000;
    h.BMS_SOC_Evidence_JSON.push(row(soc, at + 60000));
    const runtime = JSON.parse(h.BMS_Runtime_Input_Evidence_JSON[0].state);
    runtime.sequence = 2;
    runtime.recordedAt = at + 60000;
    for (const key of ['battery.dc_current_ca', 'battery.dc_voltage_cv']) {
      runtime.fields[key] = field(runtime.fields[key].value, 90000, 'value', at + 60000);
    }
    h.BMS_Runtime_Input_Evidence_JSON.push(row(runtime, at + 60000));

    const result = replayRuntime(h, { startMs: at + 120000, endMs: at + 120000 });
    expect(result.candidateBasisTicks).toEqual({ off: 1 });
    expect(result.firstOffSourceSnapshots).toHaveLength(1);
    expect(result.firstOffSourceSnapshots[0]).toMatchObject({
      remainingAh: { status: 'valid', validForMs: 0 },
      soc: { status: 'valid', validForMs: 60000 },
      current: { status: 'valid', validForMs: 30000 },
      voltage: { status: 'valid', validForMs: 30000 },
    });
  });

  it('audits a fresh charging crossover through the dwell gate and subsequent reversal', () => {
    const h = histories();
    for (const [offset, value] of [[30000, -300], [60000, 150], [90000, -300]]) {
      const r = JSON.parse(h.BMS_Runtime_Input_Evidence_JSON[0].state);
      r.sequence = offset / 30000 + 1;
      r.recordedAt = at + offset;
      r.fields['battery.dc_current_ca'] = field(value, 90000, 'value', at + offset);
      h.BMS_Runtime_Input_Evidence_JSON.push(row(r, at + offset));
    }
    const ac = JSON.parse(h.Inverter_AC_Evidence_JSON[0].state);
    ac.sequence = 3; ac.recordedAt = at + 60000;
    ac.fields['inverter.ac_output_w'] = field(150, 30000, 'watts', at + 60000);
    h.Inverter_AC_Evidence_JSON.push(row(ac, at + 60000));
    const result = replayRuntime(h, { startMs: at, endMs: at + 90000 });
    expect(result.confirmedChargingTicks).toBe(1);
    expect(result.chargingBmsBasisViolations).toEqual([]);
    expect(result.confirmedChargingTransitions).toEqual([{
      at: new Date(at + 60000).toISOString(), priorBasis: 'bms', candidateBasis: 'now',
      currentA: 1.5, observedAt: new Date(at + 60000).toISOString(),
    }]);
    expect(result.ttfReversalViolations).toEqual([]);
    expect(result.lastCandidate.ttfMin).toBe('0');
  });

  it('does not treat a malformed current receipt as qualified charging evidence', () => {
    const h = histories();
    const r = JSON.parse(h.BMS_Runtime_Input_Evidence_JSON[0].state);
    r.fields['battery.dc_current_ca'] = field(150, 90000);
    r.basis = 'wrong_source';
    h.BMS_Runtime_Input_Evidence_JSON = [row(r)];
    const result = replayRuntime(h, { startMs: at, endMs: at });
    expect(result.confirmedChargingTicks).toBe(0);
    expect(result.confirmedChargingTransitions).toEqual([]);
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
