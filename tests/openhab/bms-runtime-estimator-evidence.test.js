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
    expect(resources.triggers).toEqual([{ id: 'freshness', type: 'timer.GenericCronTrigger',
      configuration: { cronExpression: '0/30 * * * * ?' } }]);
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
    expect(h.states.BMS_Runtime_Basis).toBe('bms');
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
