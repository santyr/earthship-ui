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
