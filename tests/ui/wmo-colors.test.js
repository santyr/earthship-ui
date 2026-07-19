import { describe, expect, it } from 'vitest';
import { wmoColor, skyIconColor, CONDITION_COLORS } from '../../src/lib/ui/wmo.js';

describe('wmoColor', () => {
  it('maps band edges to condition colors', () => {
    expect(wmoColor(0)).toBe(CONDITION_COLORS.sunny);      // clear
    expect(wmoColor(2)).toBe(CONDITION_COLORS.partly);
    expect(wmoColor(3)).toBe(CONDITION_COLORS.cloudy);
    expect(wmoColor(45)).toBe(CONDITION_COLORS.fog);
    expect(wmoColor(51)).toBe(CONDITION_COLORS.rain);      // drizzle
    expect(wmoColor(61)).toBe(CONDITION_COLORS.pouring);   // rain band renders pouring icon
    expect(wmoColor(63)).toBe(CONDITION_COLORS.pouring);   // heavy split
    expect(wmoColor(71)).toBe(CONDITION_COLORS.snow);
    expect(wmoColor(80)).toBe(CONDITION_COLORS.pouring);   // showers
    expect(wmoColor(85)).toBe(CONDITION_COLORS.snow);
    expect(wmoColor(95)).toBe(CONDITION_COLORS.thunder);
  });

  it('returns null for unknown or invalid codes', () => {
    for (const code of [null, undefined, '', 'NULL', 'UNDEF', 'abc', 44]) {
      expect(wmoColor(code)).toBeNull();
    }
  });
});

describe('skyIconColor', () => {
  it('maps openHAB condition icon names by category', () => {
    expect(skyIconColor('iconify:mdi:weather-sunny')).toBe(CONDITION_COLORS.sunny);
    expect(skyIconColor('mdi:weather-night')).toBe(CONDITION_COLORS.clearNight);
    expect(skyIconColor('iconify:mdi:weather-night-partly-cloudy')).toBe(CONDITION_COLORS.partly);
    expect(skyIconColor('iconify:mdi:weather-partly-cloudy')).toBe(CONDITION_COLORS.partly);
    expect(skyIconColor('iconify:bi:cloud-sun-fill')).toBe(CONDITION_COLORS.partly);
    expect(skyIconColor('mdi:weather-cloudy')).toBe(CONDITION_COLORS.cloudy);
    expect(skyIconColor('mdi:weather-fog')).toBe(CONDITION_COLORS.fog);
    expect(skyIconColor('mdi:weather-rainy')).toBe(CONDITION_COLORS.rain);
    expect(skyIconColor('mdi:weather-pouring')).toBe(CONDITION_COLORS.pouring);
    expect(skyIconColor('mdi:weather-snowy')).toBe(CONDITION_COLORS.snow);
    expect(skyIconColor('mdi:weather-snowy-heavy')).toBe(CONDITION_COLORS.snow);
    expect(skyIconColor('mdi:weather-lightning')).toBe(CONDITION_COLORS.thunder);
  });

  it('returns null for unknown, empty, or non-weather names', () => {
    for (const name of [null, undefined, '', 'NULL', 'UNDEF', 'mdi:home-thermometer']) {
      expect(skyIconColor(name)).toBeNull();
    }
  });
});

describe('CONDITION_COLORS palette', () => {
  it('pins the exact spec palette', () => {
    expect(CONDITION_COLORS).toEqual({
      sunny: '#eab308',
      clearNight: '#cbd5e1',
      partly: '#cbd5e1',
      cloudy: '#94a3b8',
      fog: '#8b93a1',
      rain: '#3b82f6',
      pouring: '#2563eb',
      snow: '#bfdbfe',
      thunder: '#8b5cf6',
    });
  });
});
