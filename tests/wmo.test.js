import { describe, it, expect } from 'vitest';
import { wmoIcon, wmoLabel } from '../src/lib/ui/wmo.js';

describe('wmoIcon', () => {
  it('maps code 0 to sunny', () => {
    expect(wmoIcon(0)).toBe('mdi:weather-sunny');
  });
  it('maps code 1 to sunny', () => {
    expect(wmoIcon(1)).toBe('mdi:weather-sunny');
  });
  it('maps code 2 to partly cloudy', () => {
    expect(wmoIcon(2)).toBe('mdi:weather-partly-cloudy');
  });
  it('maps code 3 to cloudy', () => {
    expect(wmoIcon(3)).toBe('mdi:weather-cloudy');
  });
  it('maps code 45 to fog', () => {
    expect(wmoIcon(45)).toBe('mdi:weather-fog');
  });
  it('maps code 63 to pouring', () => {
    expect(wmoIcon(63)).toBe('mdi:weather-pouring');
  });
  it('maps code 71 to snowy', () => {
    expect(wmoIcon(71)).toBe('mdi:weather-snowy');
  });
  it('maps code 80 to showers (pouring)', () => {
    expect(wmoIcon(80)).toBe('mdi:weather-pouring');
  });
  it('maps code 95 to thunderstorm', () => {
    expect(wmoIcon(95)).toBe('mdi:weather-lightning');
  });
  it('returns a fallback icon for unknown/null codes', () => {
    expect(wmoIcon(null)).toBe('mdi:help-circle-outline');
    expect(wmoIcon(undefined)).toBe('mdi:help-circle-outline');
    expect(wmoIcon('NULL')).toBe('mdi:help-circle-outline');
  });
});

describe('wmoLabel', () => {
  it('labels code 0 as Sunny', () => {
    expect(wmoLabel(0)).toBe('Sunny');
  });
  it('labels code 63 as Rain', () => {
    expect(wmoLabel(63)).toBe('Rain');
  });
  it('labels code 71 as Snow', () => {
    expect(wmoLabel(71)).toBe('Snow');
  });
  it('labels code 95 as Thunderstorm', () => {
    expect(wmoLabel(95)).toBe('Thunderstorm');
  });
  it('returns em-dash for unknown/null codes', () => {
    expect(wmoLabel(null)).toBe('—');
    expect(wmoLabel(undefined)).toBe('—');
  });
});
