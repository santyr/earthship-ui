import { describe, it, expect } from 'vitest';
import { get } from 'svelte/store';
import { parseHash, navigate, currentRoute, ROUTES } from '../src/routes.js';

describe('parseHash', () => {
  it('parses a valid hash into its route name', () => {
    expect(parseHash('#/energy')).toBe('energy');
    expect(parseHash('#/weather')).toBe('weather');
    expect(parseHash('#/earthship')).toBe('earthship');
    expect(parseHash('#/home')).toBe('home');
  });

  it('accepts a hash without the leading slash', () => {
    expect(parseHash('#energy')).toBe('energy');
  });

  it('accepts a bare route name with no hash prefix', () => {
    expect(parseHash('energy')).toBe('energy');
  });

  it('defaults to home for an empty hash', () => {
    expect(parseHash('')).toBe('home');
    expect(parseHash(undefined)).toBe('home');
    expect(parseHash(null)).toBe('home');
  });

  it('defaults to home for an unknown route', () => {
    expect(parseHash('#/nonexistent')).toBe('home');
  });
});

describe('navigate + currentRoute', () => {
  it('updates currentRoute to the requested route', () => {
    navigate('energy');
    expect(get(currentRoute)).toBe('energy');
  });

  it('falls back to home when navigating to an unknown route', () => {
    navigate('nonexistent');
    expect(get(currentRoute)).toBe('home');
  });

  it('exposes the four expected routes', () => {
    expect(ROUTES).toEqual(['home', 'energy', 'weather', 'earthship']);
  });
});
