import { describe, it, expect } from 'vitest';
import {
  num,
  fmt,
  socBands,
  runtimeText,
  rainAmountText,
  splitRoundedMinutes,
} from '../src/lib/openhab/values.js';

describe('num', () => {
  it('strips units and parses a numeric state', () => {
    expect(num('53.42 V')).toBe(53.42);
  });
  it('parses common QuantityType unit suffixes', () => {
    expect(num('12.3 mph')).toBe(12.3);
    expect(num('-4.2 A')).toBe(-4.2);
    expect(num('88.9 °F')).toBe(88.9);
  });
  it('preserves scientific notation instead of corrupting the exponent', () => {
    expect(num('1.0E-4 in')).toBe(1e-4);
    expect(num('1.0E-4')).toBe(1e-4);
    expect(num('2.5e3 W')).toBe(2500);
  });
  it('parses plain numbers unchanged', () => {
    expect(num(42)).toBe(42);
    expect(num('-12.6')).toBe(-12.6);
    expect(num(0)).toBe(0);
  });
  it('returns null for non-numeric-leading strings', () => {
    expect(num('abc123')).toBeNull();
    expect(num('ON')).toBeNull();
  });
  it('returns null for NULL', () => {
    expect(num('NULL')).toBeNull();
  });
  it('returns null for UNDEF', () => {
    expect(num('UNDEF')).toBeNull();
  });
  it('returns null for undefined', () => {
    expect(num(undefined)).toBeNull();
  });
  it('returns null for non-numeric strings', () => {
    expect(num('abc')).toBeNull();
  });
  it('returns null for empty string', () => {
    expect(num('')).toBeNull();
  });
});

describe('fmt', () => {
  it('formats a numeric state with unit and rounds to given digits', () => {
    expect(fmt('88.9 °F', '°', 0)).toBe('89°');
  });
  it('formats with non-zero digits', () => {
    expect(fmt('53.42 V', 'V', 1)).toBe('53.4V');
  });
  it('formats with no unit and default digits', () => {
    expect(fmt('12.6')).toBe('13');
  });
  it('renders em-dash for NULL', () => {
    expect(fmt('NULL', '°')).toBe('—');
  });
  it('renders em-dash for undefined', () => {
    expect(fmt(undefined)).toBe('—');
  });
});

describe('socBands - interim mode (bands [60,40,12], explicit full=false)', () => {
  it('returns red at or below 12', () => {
    expect(socBands(12, false)).toBe('#ef4444');
  });
  it('returns orange above 12 up to 40', () => {
    expect(socBands(25, false)).toBe('#f97316');
  });
  it('returns yellow above 40 up to 60', () => {
    expect(socBands(45, false)).toBe('#eab308');
  });
  it('returns green above 60', () => {
    expect(socBands(70, false)).toBe('#22c55e');
  });
  it('returns gray for null', () => {
    expect(socBands(null, false)).toBe('#6b7280');
  });
});

describe('socBands - full mode (bands [50,30,12], the default since 400Ah bank)', () => {
  it('returns red at or below 12', () => {
    expect(socBands(12)).toBe('#ef4444');
  });
  it('returns orange above 12 up to 30', () => {
    expect(socBands(20)).toBe('#f97316');
  });
  it('returns yellow above 30 up to 50', () => {
    expect(socBands(45)).toBe('#eab308');
  });
  it('returns green above 50', () => {
    expect(socBands(70)).toBe('#22c55e');
  });
  it('returns gray for null', () => {
    expect(socBands(null)).toBe('#6b7280');
  });
  it('matches explicit full=true', () => {
    expect(socBands(45)).toBe(socBands(45, true));
  });
});

describe('runtimeText', () => {
  it('formats minutes under an hour as "min"', () => {
    expect(runtimeText(45)).toBe('45 min');
  });
  it('formats minutes as hours and minutes', () => {
    expect(runtimeText(320)).toBe('5 h 20 m');
  });
  it('formats minutes as days and hours', () => {
    expect(runtimeText(3000)).toBe('2 d 2 h');
  });
  it('caps at "> 7 d" for a week or more', () => {
    expect(runtimeText(10080)).toBe('> 7 d');
  });
  it('returns em-dash for zero', () => {
    expect(runtimeText(0)).toBe('—');
  });
  it('returns em-dash for negative values', () => {
    expect(runtimeText(-5)).toBe('—');
  });
  it('returns em-dash for null', () => {
    expect(runtimeText(null)).toBe('—');
  });
  it('rounds to whole minutes before carrying into hours (no "1 h 60 m")', () => {
    expect(runtimeText(119.6)).toBe('2 h 0 m');
    expect(runtimeText(59.6)).toBe('1 h 0 m');
    expect(runtimeText(1439.7)).toBe('24 h 0 m');
  });
  it('carries whole hours into days (no "2 d 24 h")', () => {
    expect(runtimeText(4289.9)).toBe('3 d 0 h');
    expect(runtimeText(2879.7)).toBe('2 d 0 h');
  });
});

describe('splitRoundedMinutes', () => {
  it('rounds to whole minutes first, then splits into hours and minutes', () => {
    expect(splitRoundedMinutes(119.6)).toEqual({ total: 120, hours: 2, minutes: 0 });
    expect(splitRoundedMinutes(320)).toEqual({ total: 320, hours: 5, minutes: 20 });
    expect(splitRoundedMinutes(59.4)).toEqual({ total: 59, hours: 0, minutes: 59 });
    expect(splitRoundedMinutes(59.6)).toEqual({ total: 60, hours: 1, minutes: 0 });
  });
});

describe('rainAmountText', () => {
  it('formats a positive amount to two decimals with a typographic double-prime', () => {
    expect(rainAmountText(0.2)).toBe('0.20″');
    expect(rainAmountText(1.236)).toBe('1.24″');
  });
  it('returns null for zero', () => {
    expect(rainAmountText(0)).toBeNull();
  });
  it('returns null for negative values', () => {
    expect(rainAmountText(-0.1)).toBeNull();
  });
  it('returns null for null', () => {
    expect(rainAmountText(null)).toBeNull();
  });
  it('returns null for undefined', () => {
    expect(rainAmountText(undefined)).toBeNull();
  });
});
