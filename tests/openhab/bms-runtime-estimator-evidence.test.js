import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/rules/bms-runtime-estimator-evidence.js', import.meta.url), 'utf8');
const resources = JSON.parse(readFileSync(new URL('../../openhab/bms-runtime-estimator-evidence-resources.json', import.meta.url), 'utf8'));
const t0 = 1800000000000;
const field = (value, at, ttl, property = 'value') => ({
  status: 'valid', reason: 'ok', observedAt: at, validUntil: at + ttl, [property]: value,
});
function fixture() {
  let now = t0;
  const states = {
    BMS_SOC: '80', BMS_Capacity_Remaining_Ah: '320', DCData_Current: '-3',
    DCData_Voltage: '50', BMS_TimeToDischarge_Min: '500',
    BMS_TimeToFull_Min: '0', ConextGateway_ACPowerValue: '150', MPPT60_PV_Power: '500',
    Sun_Position_Elevation: '30', BMS_TimeToDischarge_Smoothed: 'NULL',
    BMS_TimeToFull_Smoothed: 'NULL', BMS_Runtime_Basis: 'NULL',
  };
  const sources = {
    BMS_SOC_Evidence_JSON: { version: 1, streamEpoch: 'soc', recordedAt: now,
      status: 'valid', reason: 'ok', observedAt: now, scaleObservedAt: now,
      validUntil: now + 120000, soc: 80 },
    BMS_Aux_Evidence_JSON: { version: 1, basis: 'discover_bms_190_native_aux_v1',
      streamEpoch: 'aux', sequence: 1, recordedAt: now,
      fields: { 'battery.remaining_ah': field(320, now, 120000) } },
    BMS_Runtime_Input_Evidence_JSON: { version: 1, basis: 'native_runtime_inputs_v1',
      streamEpoch: 'runtime', sequence: 1, recordedAt: now, fields: {
        'battery.dc_current_ca': field(-300, now, 90000),
        'battery.dc_voltage_cv': field(5000, now, 90000),
        'battery.ttd_min': field(500, now, 120000),
        'battery.ttf_min': field(0, now, 120000),
      } },
    Inverter_AC_Evidence_JSON: { version: 1, basis: 'inverter_output',
      streamEpoch: 'ac', sequence: 1, recordedAt: now,
      fields: { 'inverter.ac_output_w': field(150, now, 30000, 'watts') } },
    Power_Evidence_JSON: { version: 1, streamEpoch: 'pv', sequence: 1,
      recordedAt: now, fields: { 'pv.input_power_w': field(500, now, 120000, 'watts') } },
  };
  const cache = new Map(), reads = [], posts = [];
  const fakeTime = { toZDT: () => {
    const z = {
      withHour: () => z, withMinute: () => z, withSecond: () => z, withNano: () => z,
      minusDays: () => z, isBefore: () => false,
      toLocalDate: () => ({ toString: () => '2026-10-01' }),
    };
    return z;
  } };
  const openhab = {
    cache: { private: { get: (key, fallback) => {
      if (!cache.has(key) && fallback) cache.set(key, fallback());
      return cache.get(key);
    }, put: (key, value) => cache.set(key, value) } },
    time: fakeTime,
    items: { getItem: name => ({
      get state() {
        reads.push(name);
        return name in sources ? JSON.stringify(sources[name]) : states[name] ?? 'NULL';
      },
      persistence: { averageBetween: () => 100 },
      postUpdate: value => { states[name] = String(value); posts.push([name, value]); },
      sendCommand: () => { throw new Error('control forbidden'); },
    }) },
  };
  return { sources, states, cache, reads, posts,
    advance: ms => { now += ms; },
    run: () => vm.runInNewContext(source, { require: () => openhab,
      Date: { now: () => now } }, { timeout: 1000 }) };
}

describe('source-bound display-only battery runtime candidate', () => {
  it('uses a disabled periodic freshness trigger so stale receipts clear without BMS events', () => {
    expect(resources.replacesRule).toBe('hex_bms_ttd_smooth');
    expect(resources.enabled).toBe(false);
    expect(resources.triggers).toEqual([
      { id: 'evidence', type: 'core.ItemStateUpdateTrigger',
        configuration: { itemName: 'BMS_Runtime_Input_Evidence_JSON' } },
      { id: 'freshness', type: 'timer.GenericCronTrigger',
        configuration: { cronExpression: '0/30 * * * * ?' } },
    ]);
  });

  it('does not weight duplicate timer/evidence reads as new AC, PV or charging samples', () => {
    const h = fixture();
    const runtime = h.sources.BMS_Runtime_Input_Evidence_JSON;
    runtime.fields['battery.dc_current_ca'].value = 500;
    h.run();
    h.advance(1000);
    runtime.recordedAt = t0 + 1000;
    runtime.fields['battery.dc_current_ca'] = field(1000, t0 + 1000, 90000);
    const ac = h.sources.Inverter_AC_Evidence_JSON;
    ac.recordedAt = t0 + 1000;
    ac.fields['inverter.ac_output_w'] = field(250, t0 + 1000, 30000, 'watts');
    const pv = h.sources.Power_Evidence_JSON;
    pv.recordedAt = t0 + 1000;
    pv.fields['pv.input_power_w'] = field(1000, t0 + 1000, 120000, 'watts');
    h.run();
    expect(h.cache.get('i_chg')).toBe(5.25);
    expect(h.cache.get('p_load')).toBe(155);
    expect(h.cache.get('p_pv')).toBe(525);
    const ttf = h.states.BMS_TimeToFull_Smoothed;
    h.run(); h.advance(1000); h.run();
    expect(h.cache.get('i_chg')).toBe(5.25);
    expect(h.cache.get('p_load')).toBe(155);
    expect(h.cache.get('p_pv')).toBe(525);
    expect(h.states.BMS_TimeToFull_Smoothed).toBe(ttf);
  });

  it('produces identical smoothing for the same observations despite extra evaluations and envelope sequences', () => {
    const sparse = fixture(), noisy = fixture();
    let expectedLoad, expectedPv, expectedCharge;
    for (let sample = 0; sample < 12; sample++) {
      const observed = t0 + sample * 1000;
      const load = 150 + sample * 30, pv = 1200 + sample * 20;
      const charge = 5 + sample * 0.2;
      for (const h of [sparse, noisy]) {
        const runtime = h.sources.BMS_Runtime_Input_Evidence_JSON;
        runtime.recordedAt = observed;
        runtime.sequence++;
        runtime.fields['battery.dc_current_ca'] = field(Math.round(charge * 100), observed, 90000);
        const ac = h.sources.Inverter_AC_Evidence_JSON;
        ac.recordedAt = observed;
        ac.fields['inverter.ac_output_w'] = field(load, observed, 30000, 'watts');
        const power = h.sources.Power_Evidence_JSON;
        power.recordedAt = observed;
        power.fields['pv.input_power_w'] = field(pv, observed, 120000, 'watts');
        h.run();
      }
      expectedLoad = sample ? expectedLoad + 0.05 * (load - expectedLoad) : load;
      expectedPv = sample ? expectedPv + 0.05 * (pv - expectedPv) : pv;
      expectedCharge = sample ? expectedCharge + 0.05 * (charge - expectedCharge) : charge;
      for (let reread = 0; reread < 4; reread++) {
        noisy.advance(250);
        // Another field can publish a new envelope without a new current sample.
        noisy.sources.BMS_Runtime_Input_Evidence_JSON.recordedAt = observed + (reread + 1) * 250;
        noisy.sources.BMS_Runtime_Input_Evidence_JSON.sequence++;
        noisy.run();
      }
      sparse.advance(1000);
      for (const [key, expected] of [['p_load', expectedLoad], ['p_pv', expectedPv], ['i_chg', expectedCharge]]) {
        expect(sparse.cache.get(key)).toBeCloseTo(expected, 10);
        expect(noisy.cache.get(key)).toBeCloseTo(expected, 10);
      }
      expect(noisy.states.BMS_TimeToDischarge_Smoothed).toBe(sparse.states.BMS_TimeToDischarge_Smoothed);
      expect(noisy.states.BMS_TimeToFull_Smoothed).toBe(sparse.states.BMS_TimeToFull_Smoothed);
      expect(noisy.states.BMS_Runtime_Basis).toBe(sparse.states.BMS_Runtime_Basis);
    }
  });

  it('reseeds smoothing after a bank-evidence barrier instead of reviving the old average', () => {
    const h = fixture();
    h.sources.BMS_Runtime_Input_Evidence_JSON.fields['battery.dc_current_ca'].value = 500;
    h.run();
    h.sources.BMS_SOC_Evidence_JSON.status = 'unavailable';
    h.advance(1000); h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('off');
    expect(h.cache.get('i_chg')).toBeNull();
    expect(h.cache.get('p_load')).toBeNull();
    h.sources.BMS_SOC_Evidence_JSON.status = 'valid';
    // The same still-qualified source identities are intentionally reused:
    // invalidated caches must seed, not skip because their identities match.
    h.run();
    expect(h.cache.get('i_chg')).toBe(5);
    expect(h.cache.get('p_load')).toBe(150);
    expect(h.states.BMS_Runtime_Basis).toBe('now');
    expect(h.states.BMS_TimeToFull_Smoothed).toBe('960');
  });

  it('uses fresh receipts for the deep BMS basis and never reads held input Items', () => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: true, buf: [],
      tsDisch: t0 - 600000, tsDeep: t0 - 600000 });
    h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('bms');
    expect(h.states.BMS_TimeToDischarge_Smoothed).toBe('500');
    expect(h.reads).not.toContain('BMS_SOC');
    expect(h.reads).not.toContain('BMS_Capacity_Remaining_Ah');
    expect(h.reads).not.toContain('DCData_Current');
    expect(h.reads).not.toContain('DCData_Voltage');
    expect(h.reads).not.toContain('BMS_TimeToDischarge_Min');
    expect(h.reads).not.toContain('ConextGateway_ACPowerValue');
    expect(h.reads).not.toContain('MPPT60_PV_Power');
  });

  it('drops to off and zero when source-bound current expires despite held numeric states', () => {
    const h = fixture(); h.run(); h.advance(90000); h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('off');
    expect(h.states.BMS_TimeToDischarge_Smoothed).toBe('0');
    expect(h.states.BMS_TimeToFull_Smoothed).toBe('0');
    expect(h.cache.get('ttd_state').buf).toHaveLength(0);
    expect(h.cache.get('p_load')).toBeNull();
    expect(h.cache.get('i_chg')).toBeNull();
  });

  it('exits a deep BMS basis promptly on a distinct strong charging receipt', () => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: true, buf: [500],
      tsDisch: t0, tsDeep: t0 });
    h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('bms');
    h.advance(1000);
    const row = h.sources.BMS_Runtime_Input_Evidence_JSON;
    row.recordedAt = t0 + 1000;
    row.fields['battery.dc_current_ca'] = field(150, t0 + 1000, 90000);
    h.run();
    expect(h.cache.get('ttd_state').discharging).toBe(false);
    expect(h.cache.get('ttd_state').buf).toHaveLength(0);
    expect(h.states.BMS_Runtime_Basis).not.toBe('bms');
  });

  it.each([-79, -80])('rejects %i cA TTD samples during a latched deep dwell and rewarms without old samples', currentCa => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: true, buf: [500],
      tsDisch: t0, tsDeep: t0 });
    h.run();
    const row = h.sources.BMS_Runtime_Input_Evidence_JSON;
    function observe(offset, current, ttd) {
      h.advance(1000); row.recordedAt = t0 + offset;
      row.fields['battery.dc_current_ca'] = field(current, t0 + offset, 90000);
      if (ttd !== undefined) row.fields['battery.ttd_min'] = field(ttd, t0 + offset, 120000);
      h.run();
    }
    observe(1000, currentCa, 26000);
    expect(h.cache.get('ttd_state').deep).toBe(true);
    expect(h.cache.get('ttd_state').tsDeep).toBe(t0);
    expect(h.cache.get('ttd_state').buf).toHaveLength(0);
    expect(h.states.BMS_Runtime_Basis).toBe('evening');
    observe(2000, -300, 700);
    h.run(); h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('evening');
    expect(h.cache.get('ttd_state').deepStreak).toBe(1);
    observe(3000, -300);
    expect(h.states.BMS_Runtime_Basis).toBe('bms');
    expect(Array.from(h.cache.get('ttd_state').buf)).toEqual([700]);
    expect(h.states.BMS_TimeToDischarge_Smoothed).toBe('700');
  });

  it('never reclassifies a rejected shallow TTD observation when current later becomes deep', () => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: true, buf: [500],
      tsDisch: t0, tsDeep: t0 });
    h.run();
    const row = h.sources.BMS_Runtime_Input_Evidence_JSON;
    for (const [offset, current] of [[1000, -70], [2000, -300], [3000, -300]]) {
      h.advance(1000); row.recordedAt = t0 + offset;
      row.fields['battery.dc_current_ca'] = field(current, t0 + offset, 90000);
      if (offset === 1000) row.fields['battery.ttd_min'] = field(26000, t0 + offset, 120000);
      h.run();
      expect(h.states.BMS_Runtime_Basis).toBe('evening');
      expect(h.cache.get('ttd_state').buf).toHaveLength(0);
    }
    h.advance(1000); row.recordedAt = t0 + 4000;
    row.fields['battery.ttd_min'] = field(700, t0 + 4000, 120000);
    h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('bms');
    expect(h.states.BMS_TimeToDischarge_Smoothed).toBe('700');
  });

  it('does not use a later current observation to qualify an older unseen TTD sample', () => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: true, buf: [],
      tsDisch: t0, tsDeep: t0 });
    h.advance(1000);
    const row = h.sources.BMS_Runtime_Input_Evidence_JSON;
    row.recordedAt = t0 + 1000;
    row.fields['battery.dc_current_ca'] = field(-300, t0 + 1000, 90000);
    h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('evening');
    expect(h.cache.get('ttd_state').buf).toHaveLength(0);
    h.advance(1000); row.recordedAt = t0 + 2000;
    row.fields['battery.ttd_min'] = field(700, t0 + 2000, 120000);
    h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('bms');
    expect(h.states.BMS_TimeToDischarge_Smoothed).toBe('700');
  });

  it('requires two distinct near-zero current receipts before an early discharge exit', () => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: true, buf: [500],
      tsDisch: t0, tsDeep: t0 });
    h.run();
    h.advance(1000);
    const row = h.sources.BMS_Runtime_Input_Evidence_JSON;
    row.recordedAt = t0 + 1000;
    row.fields['battery.dc_current_ca'] = field(0, t0 + 1000, 90000);
    h.run(); h.run();
    expect(h.cache.get('ttd_state').exitStreak).toBe(1);
    expect(h.cache.get('ttd_state').discharging).toBe(true);
    expect(h.states.BMS_Runtime_Basis).toBe('evening');
    h.advance(1000);
    row.recordedAt = t0 + 2000;
    row.fields['battery.dc_current_ca'] = field(0, t0 + 2000, 90000);
    h.run();
    expect(h.cache.get('ttd_state').discharging).toBe(false);
    expect(h.states.BMS_Runtime_Basis).not.toBe('bms');
  });

  it('counts distinct deep-discharge receipts, not duplicate timer evaluations', () => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: false, buf: [],
      tsDisch: t0 - 600000, tsDeep: t0 - 600000 });
    h.run(); h.run();
    expect(h.cache.get('ttd_state').deepStreak).toBe(1);
    expect(h.states.BMS_Runtime_Basis).not.toBe('bms');
    h.advance(1000);
    const row = h.sources.BMS_Runtime_Input_Evidence_JSON;
    row.recordedAt = t0 + 1000;
    row.fields['battery.dc_current_ca'] = field(-300, t0 + 1000, 90000);
    h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('bms');
  });

  it('fails projection closed for stale SoC, remaining Ah, voltage or AC load', () => {
    for (const key of ['BMS_SOC_Evidence_JSON', 'BMS_Aux_Evidence_JSON',
      'BMS_Runtime_Input_Evidence_JSON', 'Inverter_AC_Evidence_JSON']) {
      const h = fixture();
      if (key === 'BMS_Runtime_Input_Evidence_JSON') {
        h.sources[key].fields['battery.dc_voltage_cv'].validUntil = t0;
      } else if (key === 'BMS_SOC_Evidence_JSON') {
        h.sources[key].status = 'unavailable';
      } else {
        const prop = key === 'BMS_Aux_Evidence_JSON' ? 'battery.remaining_ah' : 'inverter.ac_output_w';
        h.sources[key].fields[prop].status = 'unavailable';
      }
      h.run();
      expect(h.states.BMS_Runtime_Basis, key).toBe('off');
      expect(h.states.BMS_TimeToDischarge_Smoothed, key).toBe('0');
    }
  });

  it('does not retain a deep BMS basis when the independent SoC receipt fails', () => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: true, buf: [500],
      tsDisch: t0 - 600000, tsDeep: t0 - 600000 });
    h.run();
    h.sources.BMS_SOC_Evidence_JSON.status = 'unavailable';
    h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('off');
    expect(h.cache.get('ttd_state').buf).toHaveLength(0);
  });

  it('rejects wrong stream identity, future recording time and value/expiry mismatch', () => {
    const mutations = [
      h => { h.sources.BMS_Runtime_Input_Evidence_JSON.basis = 'untrusted'; },
      h => { h.sources.BMS_Runtime_Input_Evidence_JSON.recordedAt = t0 + 1; },
      h => { h.sources.BMS_Runtime_Input_Evidence_JSON.fields['battery.dc_current_ca'].validUntil += 1; },
      h => { h.sources.BMS_Runtime_Input_Evidence_JSON.fields['battery.dc_current_ca'].value = 40000; },
      h => { h.sources.BMS_SOC_Evidence_JSON.validUntil += 1; },
    ];
    for (const mutate of mutations) {
      const h = fixture(); mutate(h); h.run();
      expect(h.states.BMS_Runtime_Basis).toBe('off');
      expect(h.states.BMS_TimeToDischarge_Smoothed).toBe('0');
    }
  });

  it('does not count the same BMS TTD receipt twice, and falls back on expiry', () => {
    const h = fixture();
    h.cache.set('ttd_state', { discharging: true, deep: true, buf: [],
      tsDisch: t0 - 600000, tsDeep: t0 - 600000 });
    h.run(); h.run();
    expect(h.cache.get('ttd_state').buf).toHaveLength(1);
    h.sources.BMS_Runtime_Input_Evidence_JSON.fields['battery.ttd_min'].validUntil = t0;
    h.run();
    expect(h.states.BMS_Runtime_Basis).toBe('evening');
    expect(h.cache.get('ttd_state').buf).toHaveLength(0);
  });

  it('uses fresh charging current, SoC and capacity for a TTF fallback', () => {
    const h = fixture();
    h.sources.BMS_Runtime_Input_Evidence_JSON.fields['battery.dc_current_ca'].value = 500;
    h.run();
    expect(Number(h.states.BMS_TimeToFull_Smoothed)).toBeGreaterThan(0);
    expect(h.states.BMS_Runtime_Basis).toBe('now');
    h.sources.BMS_SOC_Evidence_JSON.validUntil = t0;
    h.run();
    expect(h.states.BMS_TimeToFull_Smoothed).toBe('0');
    expect(h.states.BMS_Runtime_Basis).toBe('off');
  });

  it('clears a positive BMS time-to-full when fresh current reverses to discharge', () => {
    const h = fixture();
    const row = h.sources.BMS_Runtime_Input_Evidence_JSON;
    row.fields['battery.dc_current_ca'].value = 500;
    row.fields['battery.ttf_min'].value = 120;
    h.run();
    expect(h.states.BMS_TimeToFull_Smoothed).toBe('120');
    h.advance(1000);
    row.recordedAt = t0 + 1000;
    row.fields['battery.dc_current_ca'] = field(-500, t0 + 1000, 90000);
    h.run();
    expect(h.states.BMS_TimeToFull_Smoothed).toBe('0');
    expect(h.cache.get('i_chg')).toBeNull();
  });

  it('clears a lagging charge-current average on discharge and reseeds next charge', () => {
    const h = fixture();
    const row = h.sources.BMS_Runtime_Input_Evidence_JSON;
    row.fields['battery.dc_current_ca'].value = 500;
    h.run();
    expect(Number(h.states.BMS_TimeToFull_Smoothed)).toBeGreaterThan(0);
    expect(h.cache.get('i_chg')).toBe(5);
    h.advance(1000);
    row.recordedAt = t0 + 1000;
    row.fields['battery.dc_current_ca'] = field(-500, t0 + 1000, 90000);
    h.run();
    expect(h.states.BMS_TimeToFull_Smoothed).toBe('0');
    expect(h.cache.get('i_chg')).toBeNull();
    h.advance(1000);
    row.recordedAt = t0 + 2000;
    row.fields['battery.dc_current_ca'] = field(100, t0 + 2000, 90000);
    h.run();
    expect(h.cache.get('i_chg')).toBe(1);
    expect(Number(h.states.BMS_TimeToFull_Smoothed)).toBeGreaterThan(0);
  });
});
