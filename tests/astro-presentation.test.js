import { describe, it, expect } from 'vitest';
import { nativeSeasonLabel, nativeDaylightText, siteTimeLabel, nativeCurrentMoon, nativeCurrentSkyContext } from '../src/lib/weather/astroPresentation.js';

const now = Date.parse('2026-10-12T16:00:00Z');
const base = { Sun_TimeLeft: '6048000 s', Sun_NextSeason: 'WINTER', Sun_Daylight_Duration: '40533.905 s', Sun_Rise_Start: '2026-10-12T07:10:11.662-0600', Sun_Set_End: '2026-10-12T18:31:14.172-0600', Moon_MoonPhaseName: 'THIRD_QUARTER' };
const evidence = Object.fromEntries(Object.entries(base).map(([name, state]) => [name, { available: true, lastKnown: now - 16000, state }]));
const context = { states: base, evidence, now, connected: true, sunOnline: true, moonOnline: true };

describe('native current astronomy presentation', () => {
  it('uses whole-day native season duration including zero and singular wording', () => {
    for (const [raw, expected] of [['6048000 s', '70 days until Winter ❄️'], ['1 d', '1 day until Winter ❄️'], ['0 s', 'less than 1 day until Winter ❄️'], ['86399 s', 'less than 1 day until Winter ❄️']]) {
      const states = { ...base, Sun_TimeLeft: raw };
      expect(nativeSeasonLabel({ ...context, states, evidence: { ...evidence, Sun_TimeLeft: { ...evidence.Sun_TimeLeft, state: raw } } })).toBe(expected);
    }
  });
  it('withholds invalid, disconnected, stale, offline and mixed-generation season pairs', () => {
    for (const patch of [{ connected: false }, { sunOnline: false }, { now: now + 86400000 }, { states: { ...base, Sun_TimeLeft: 'UNDEF' } }, { states: { ...base, Sun_NextSeason: 'SPRING' } }, { evidence: { ...evidence, Sun_NextSeason: { ...evidence.Sun_NextSeason, lastKnown: now - 12000 } } }]) {
      expect(nativeSeasonLabel({ ...context, ...patch })).toBe('Season unavailable');
    }
  });
  it('crosses December into the native next-year season without inferring an event instant', () => {
    const states = { ...base, Sun_NextSeason: 'SUMMER', Sun_TimeLeft: '89 d' };
    const at = Date.parse('2026-12-22T18:00:00Z');
    const e = Object.fromEntries(Object.entries(states).map(([name,state]) => [name,{ available:true,lastKnown:at,state }]));
    expect(nativeSeasonLabel({ ...context, states, evidence:e, now:at })).toBe('89 days until Summer ☀️'); // Binding owns hemisphere policy.
  });
  it('converts native daylight quantities and carries rounded minutes', () => {
    for (const [raw, expected] of [['40533.905 s', '11h 16m'], ['675.565083333 min', '11h 16m'], ['11.2594180556 h', '11h 16m'], ['1.999 h', '2h 0m']]) {
      expect(nativeDaylightText({ ...context, states: { ...base, Sun_Daylight_Duration:raw }, evidence:{ ...evidence, Sun_Daylight_Duration:{ ...evidence.Sun_Daylight_Duration,state:raw } } })).toBe(expected);
    }
    for (const raw of ['0 s','-1 s','NULL','UNDEF','12','2 kg','NaN s']) expect(nativeDaylightText({ ...context,states:{ ...base,Sun_Daylight_Duration:raw } })).toBe('—');
    expect(nativeDaylightText({ ...context,now:now+86400000 })).toBe('—');
  });
  it('formats household time consistently across offsets, DST and browser timezone', () => {
    expect(siteTimeLabel('2026-10-12T13:10:11Z','en-US')).toBe('7:10a');
    expect(siteTimeLabel('2026-10-12T07:10:11-0600','en-US')).toBe('7:10a');
    expect(siteTimeLabel('2026-03-08T08:30:00Z','en-US')).toBe('1:30a');
    expect(siteTimeLabel('2026-03-08T09:30:00Z','en-US')).toBe('3:30a');
    expect(siteTimeLabel('2026-11-01T07:30:00Z','en-US')).toBe('1:30a');
    expect(siteTimeLabel('2026-11-01T08:30:00Z','en-US')).toBe('1:30a');
    expect(siteTimeLabel('2026-10-13T06:00:00Z','en-US')).toBe('12:00a');
    for (const bad of ['NULL','invalid','2026-02-30T12:00:00Z','2026-10-12T07:10:11']) expect(siteTimeLabel(bad,'en-US')).toBe('—');
  });
  it('qualifies native sun bounds for both current consumer paths', () => {
    const sky = nativeCurrentSkyContext(context);
    expect(sky.sunrise).toBe(base.Sun_Rise_Start);
    expect(sky.sunset).toBe(base.Sun_Set_End);
    for (const patch of [{sunOnline:false},{connected:false},{evidence:{}},{now:now+86400000}]) {
      expect(nativeCurrentSkyContext({...context,...patch}).sunrise).toBe(undefined);
      expect(nativeCurrentSkyContext({...context,...patch}).sunset).toBe(undefined);
    }
  });
  it('normalizes all eight native phases and refuses stale or unavailable lunar sources', () => {
    const phases = { NEW:'new',WAXING_CRESCENT:'waxing-crescent',FIRST_QUARTER:'first-quarter',WAXING_GIBBOUS:'waxing-gibbous',FULL:'full',WANING_GIBBOUS:'waning-gibbous',THIRD_QUARTER:'last-quarter',WANING_CRESCENT:'waning-crescent' };
    for (const [phase,icon] of Object.entries(phases)) expect(nativeCurrentMoon({ ...context,states:{ ...base,Moon_MoonPhaseName:phase },evidence:{ ...evidence,Moon_MoonPhaseName:{ ...evidence.Moon_MoonPhaseName,state:phase } } })).toBe('mdi:moon-'+icon);
    expect(nativeCurrentMoon({ ...context,moonOnline:false })).toBe('mdi:weather-night');
    expect(nativeCurrentMoon({ ...context,now:now+86400000 })).toBe('mdi:weather-night');
    expect(nativeCurrentMoon({ ...context,states:{ ...base,Moon_MoonPhaseName:'UNKNOWN' } })).toBe('mdi:weather-night');
  });
});


describe('coherent unavailable native durations', () => {
  it.each(['NULL','UNDEF','NaN s','-1 d','367 d'])('withholds invalid season duration %s even when receipt state matches', raw => {
    const states={...base,Sun_TimeLeft:raw};
    const e={...evidence,Sun_TimeLeft:{...evidence.Sun_TimeLeft,state:raw}};
    expect(nativeSeasonLabel({...context,states,evidence:e})).toBe('Season unavailable');
  });
  it.each(['0 s','-1 s','86400 s','NULL','UNDEF','2 kg','NaN s'])('withholds invalid daylight %s even when receipt state matches', raw => {
    const states={...base,Sun_Daylight_Duration:raw};
    const e={...evidence,Sun_Daylight_Duration:{...evidence.Sun_Daylight_Duration,state:raw}};
    expect(nativeDaylightText({...context,states,evidence:e})).toBe('—');
  });
});
