import { describe, it, expect } from 'vitest';
import { moonPhaseIcon, isDaylight, contextualSkyIcon } from '../src/lib/weather/celestial.js';
import { wmoIcon, wmoLabel, wmoColor, CONDITION_COLORS } from '../src/lib/ui/wmo.js';

describe('shared astronomical weather icons', () => {
  const night = { at: '2026-09-20T23:00:00-06:00', isDay: false };
  it('uses the forecast instant and keeps weather conditions distinct', () => {
    expect(wmoIcon(0, night)).toBe(moonPhaseIcon(night.at));
    expect(wmoIcon(1, night)).toMatch(/^mdi:moon-/);
    expect(wmoIcon(0, { ...night, isDay: true })).toBe('mdi:weather-sunny');
    expect(wmoIcon(2, night)).toBe('mdi:weather-night-partly-cloudy');
    for (const code of [3, 45, 61, 71, 95]) expect(wmoIcon(code, night)).toBe(wmoIcon(code));
    expect(wmoLabel(0, night)).toBe('Clear');
    expect(wmoColor(0, night)).toBe(CONDITION_COLORS.clearNight);
    expect(contextualSkyIcon('iconify:mdi:weather-sunny', night)).toBe(wmoIcon(0, night));
    expect(contextualSkyIcon('iconify:mdi:white-balance-sunny', night)).toBe(wmoIcon(0, night));
  });
  it('uses supplied native current moon while preserving dated future forecast phases', () => {
    expect(contextualSkyIcon('mdi:weather-sunny', { ...night,currentMoonIcon:'mdi:moon-last-quarter' })).toBe('mdi:moon-last-quarter');
    expect(contextualSkyIcon('mdi:weather-sunny', { ...night,currentMoonIcon:'mdi:weather-night' })).toBe('mdi:weather-night');
    expect(contextualSkyIcon('mdi:weather-partly-cloudy', { ...night,currentMoonIcon:'mdi:moon-full' })).toBe('mdi:weather-night-partly-cloudy');
    expect(contextualSkyIcon('mdi:weather-pouring', { ...night,currentMoonIcon:'mdi:moon-full' })).toBe('mdi:weather-pouring');
    expect(wmoIcon(0,night)).toBe(moonPhaseIcon(night.at));
    expect(contextualSkyIcon('mdi:weather-sunny',{ ...night,isDay:true,currentMoonIcon:'mdi:moon-full' })).toBe('mdi:weather-sunny');
  });
  it('withholds a retained clear-night moon phase when native daily sun bounds are stale', () => {
    const stale = {at:'2026-10-13T05:00:00-06:00',sunrise:'2026-10-12T07:10:00-06:00',sunset:'2026-10-12T18:30:00-06:00',currentMoonIcon:'mdi:weather-night'};
    expect(contextualSkyIcon('iconify:mdi:moon-full',stale)).toBe('mdi:weather-night');
    expect(contextualSkyIcon('mdi:weather-pouring',stale)).toBe('mdi:weather-pouring');
    expect(contextualSkyIcon('iconify:mdi:moon-full',{...stale,currentMoonIcon:'mdi:moon-waning-gibbous'})).toBe('mdi:weather-night');
  });
  it('covers all eight phases and equivalent instants across offsets', () => {
    const phases = new Set(Array.from({ length: 30 }, (_, i) => moonPhaseIcon(Date.UTC(2026, 8, i + 1))));
    expect(phases.size).toBe(8);
    expect(moonPhaseIcon(night.at)).toBe(moonPhaseIcon('2026-09-21T05:00:00Z'));
    expect(moonPhaseIcon('invalid')).toBe('mdi:weather-night');
    expect(moonPhaseIcon(null)).toBe('mdi:weather-night');
  });
  it('uses current-day Astro boundaries only, with sunrise inclusive and sunset exclusive', () => {
    const context = { sunrise: '2026-09-20T06:50:00-0600', sunset: '2026-09-20T19:05:00-0600' };
    expect(isDaylight({ ...context, at: '2026-09-20T06:50:00-06:00' })).toBe(true);
    expect(isDaylight({ ...context, at: '2026-09-20T19:05:00-06:00' })).toBe(false);
    expect(isDaylight({ ...context, at: '2026-09-21T12:00:00-06:00' })).toBe(null);
    expect(isDaylight({})).toBe(null);
    expect(wmoIcon(0)).toBe('mdi:weather-sunny'); // Whole-day summary, not an instant.
  });
});


describe('dated forecast lunar acceptance', () => {
  it('keeps a later same-day forecast phase independent of the current native moon', () => {
    const current = { at:'2026-09-02T00:30:00-06:00',isDay:false,currentMoonIcon:'mdi:moon-waning-gibbous' };
    expect(contextualSkyIcon('mdi:weather-sunny',current)).toBe('mdi:moon-waning-gibbous');
    const later = { at:'2026-09-02T23:30:00-06:00',isDay:false };
    expect(wmoIcon(0,later)).toBe('mdi:moon-last-quarter');
    expect(wmoIcon(0,later)).not.toBe(contextualSkyIcon('mdi:weather-sunny',current));
  });
  it('preserves equivalent forecast instants across DST offsets and unavailable clocks', () => {
    for (const [offset,utc] of [
      ['2026-03-08T01:30:00-07:00','2026-03-08T08:30:00Z'],
      ['2026-03-08T03:30:00-06:00','2026-03-08T09:30:00Z'],
      ['2026-11-01T01:30:00-06:00','2026-11-01T07:30:00Z'],
      ['2026-11-01T01:30:00-07:00','2026-11-01T08:30:00Z'],
    ]) expect(wmoIcon(0,{at:offset,isDay:false})).toBe(wmoIcon(0,{at:utc,isDay:false}));
    expect(wmoIcon(0,{at:'invalid',isDay:false})).toBe('mdi:weather-night');
    expect(wmoIcon(0,{at:'2026-09-02T23:30:00-06:00',isDay:true})).toBe('mdi:weather-sunny');
    expect(wmoIcon(0)).toBe('mdi:weather-sunny');
  });
});
