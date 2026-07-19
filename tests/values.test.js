import { describe, it, expect } from 'vitest';
import { num, fmt, socBands, runtimeText, rainAmountText } from '../src/lib/openhab/values.js';

describe('num', () => {
  it('strips units and parses a numeric state', () => {
    expect(num('53.42 V')).toBe(53.42);
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
