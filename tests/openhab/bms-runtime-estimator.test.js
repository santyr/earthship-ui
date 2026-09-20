import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import vm from 'node:vm';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../openhab/rules/bms-runtime-estimator.js', import.meta.url), 'utf8');
const begin = source.indexOf('function overnightW()');
const end = source.indexOf('// projection(forceEvening)');
const overnightSource = source.slice(begin, end);
const format = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver',
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  second: '2-digit', hourCycle: 'h23' });

// Calendar operations in Denver; epoch conversion uses the host IANA data,
// not a fixed -06:00 approximation. Test boundaries avoid ambiguous wall times.
class ZDT {
  constructor(local) { this.wall = new Date(`${local}Z`); }
  changed(fn) { const copy = new ZDT(this.wall.toISOString().slice(0, -1)); fn(copy.wall); return copy; }
  withHour(v) { return this.changed(d => d.setUTCHours(v)); }
  withMinute(v) { return this.changed(d => d.setUTCMinutes(v)); }
  withSecond(v) { return this.changed(d => d.setUTCSeconds(v)); }
  withNano(v) { expect(v).toBe(0); return this.changed(d => d.setUTCMilliseconds(0)); }
  minusDays(v) { return this.changed(d => d.setUTCDate(d.getUTCDate() - v)); }
  toLocalDate() { return { toString: () => this.wall.toISOString().slice(0, 10) }; }
  epoch() {
    const target = this.wall.getTime();
    let guess = target;
    for (let n = 0; n < 4; n++) {
      const p = Object.fromEntries(format.formatToParts(new Date(guess)).map(x => [x.type, x.value]));
      const represented = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second,
        this.wall.getUTCMilliseconds());
      guess += target - represented;
    }
    return guess;
  }
  isBefore(other) { return this.epoch() < other.epoch(); }
}

function harness(local) {
  let now = new ZDT(local), watts = 100, fails = false, clockReads = 0;
  const values = new Map(), queries = [], posts = [];
  const states = { DCData_Current: '-0.6', BMS_SOC: '80', BMS_Capacity_Remaining_Ah: '320',
    DCData_Voltage: '50', ConextGateway_ACPowerValue: '150', MPPT60_PV_Power: '0',
    Sun_Position_Elevation: '-10', BMS_TimeToFull_Min: '0', BMS_TimeToDischarge_Min: '500' };
  const openhab = {
    cache: { private: { get: (k, fallback) => {
      if (!values.has(k) && fallback) values.set(k, fallback());
      return values.get(k);
    }, put: (k, v) => values.set(k, v) } },
    time: { toZDT: () => { clockReads++; return now; } },
    items: { getItem: name => ({ state: states[name] ?? 'NULL',
      persistence: { averageBetween: (start, end) => {
        expect(name).toBe('ConextGateway_ACPowerValue');
        queries.push({ start, end, at: now });
        if (fails) throw new Error('unavailable');
        return watts;
      } },
      postUpdate: value => {
        expect(['BMS_TimeToDischarge_Smoothed', 'BMS_Runtime_Basis', 'BMS_TimeToFull_Smoothed']).toContain(name);
        posts.push([name, value]);
      }, sendCommand: () => { throw new Error('command forbidden'); } }) },
  };
  const run = () => vm.runInNewContext(`const {items,cache,time}=require('openhab'); const NIGHT_FALLBACK_W=155; ${overnightSource}; overnightW();`,
    { require: () => openhab }, { timeout: 1000 });
  return { run, values, queries, posts, setNow: v => { now = new ZDT(v); },
    setWatts: v => { watts = v; }, setFail: v => { fails = v; }, clockReads: () => clockReads,
    fullRun: () => vm.runInNewContext(source, { require: () => openhab, Date: { now: () => now.epoch() } }, { timeout: 1000 }) };
}

describe('completed overnight runtime cache', () => {
  it('preserves every byte of the hash-verified live rule outside overnightW', () => {
    expect(createHash('sha256').update(source.slice(0, begin) + source.slice(end)).digest('hex'))
      .toBe('4b3ff6febf483a0a1cd5014d9cef31927f0e7d7e20bd552c9d1bea8f8380001d');
  });
  it('keeps the completed window across midnight then refreshes exactly at 06:00', () => {
    const h = harness('2026-09-09T23:59:59.999');
    expect(h.run()).toBe(100);
    h.setNow('2026-09-10T00:30:00.000'); h.setWatts(200);
    expect(h.run()).toBe(100); expect(h.queries).toHaveLength(1);
    h.setNow('2026-09-10T05:59:59.999'); expect(h.run()).toBe(100);
    h.setNow('2026-09-10T06:00:00.000'); expect(h.run()).toBe(200);
    expect(h.queries).toHaveLength(2);
    expect(h.values.get('p_night')).toEqual({ day: '2026-09-10', w: 200 });
    expect(h.clockReads()).toBe(4);
    for (const q of h.queries) expect(q.end.epoch()).toBeLessThanOrEqual(q.at.epoch());
  });
  it.each(['2026-01-15', '2026-07-15', '2026-03-08', '2026-11-01'])('restart before 06:00 never queries an unfinished night on %s', day => {
    const h = harness(`${day}T00:30:00.123`); h.run();
    const q = h.queries[0];
    expect(q.end.epoch()).toBeLessThan(q.at.epoch());
    expect(q.end.wall.getUTCHours()).toBe(6);
    expect(q.start.wall.getUTCHours()).toBe(20);
    expect(q.start.wall.getUTCMinutes()).toBe(30);
    expect(q.end.wall.getUTCMilliseconds()).toBe(0);
  });
  it.each([['2026-03-08', 8.5], ['2026-11-01', 10.5], ['2026-07-15', 9.5]])('uses local calendar boundaries across %s', (day, hours) => {
    const h = harness(`${day}T06:00:00.123`); h.run();
    const q = h.queries[0];
    expect((q.end.epoch() - q.start.epoch()) / 3600000).toBe(hours);
  });
  it.each([null, NaN, 'invalid'])('preserves numeric fallback for %s', bad => {
    const h = harness('2026-09-10T06:00:00'); h.setWatts(bad);
    expect(h.run()).toBe(155);
  });
  it('preserves failure fallback but refreshes it for the next completed window', () => {
    const h = harness('2026-09-10T00:30:00'); h.setFail(true);
    expect(h.run()).toBe(155);
    h.setFail(false); h.setWatts(200); h.setNow('2026-09-10T06:00:00');
    expect(h.run()).toBe(200);
  });
  it('exercises the real shallow-discharge caller with no command authority', () => {
    const h = harness('2026-09-10T00:30:00'); h.fullRun();
    expect(h.queries).toHaveLength(1);
    expect(h.queries[0].end.epoch()).toBeLessThan(h.queries[0].at.epoch());
    expect(h.posts).toContainEqual(['BMS_Runtime_Basis', 'evening']);
  });
});
