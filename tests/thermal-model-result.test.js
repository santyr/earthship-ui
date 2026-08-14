import { describe, expect, it } from 'vitest';

import validShadow from './fixtures/thermal-shadow-v1-available.json';
import { parseThermalModelResult } from '../src/lib/thermal/modelResult.js';

const GENERATED_AT_MS = Date.parse(validShadow.generatedAt);

function fixture(mutator = () => {}) {
  const payload = structuredClone(validShadow);
  mutator(payload);
  return payload;
}

function unavailableFixture() {
  return fixture((payload) => {
    payload.model = {};
    payload.current = { hallwayF: null, massF: null, glazingF: null };
    payload.forecast = {
      availableHours: 0,
      hallwayHighF: null,
      hallwayHighAt: null,
      hallwayLowF: null,
      hallwayLowAt: null,
      morningMassF: null,
      intervalLowF: null,
      intervalHighF: null,
      trajectory: [],
      observed: [],
    };
    payload.schedule = {};
    payload.confidence = { grade: 'unavailable', actionLabels: 'unknown' };
    payload.provenance.actions = 'unknown';
    payload.provenance.currentAgeMinutes = {
      air: null,
      mass: null,
      glazing: null,
      outdoor: null,
      radiation: null,
    };
    payload.provenance.modelAgeHours = null;
    payload.provenance.trainingDataAgeHours = null;
    payload.reasons = ['stale hallway temperature'];
  });
}

describe('parseThermalModelResult', () => {
  it('parses a complete fresh v1 shadow result and preserves zero effects', () => {
    const result = parseThermalModelResult(
      JSON.stringify(validShadow),
      GENERATED_AT_MS + 10 * 60_000,
    );

    expect(result).toMatchObject({
      state: 'ready',
      badge: 'SHADOW',
      generatedAtMs: GENERATED_AT_MS,
      hallwayHigh: 80,
      hallwayLow: 68,
      morningMass: 70,
      ventWindow: null,
      effect: { morningMassDeltaF: 0, hallwayPeakDeltaF: 0 },
      confidence: 'low',
      reasons: ['minimum modeled improvement not met; no candidate emitted'],
    });
    expect(result.trajectory).toHaveLength(2);
    expect(result.observed).toHaveLength(1);
  });

  it('formats a complete candidate vent window in the configured local timezone', () => {
    const payload = fixture((value) => {
      value.schedule.candidate = {
        ventOpenAt: '2026-08-14T03:00:00+00:00',
        ventCloseAt: '2026-08-14T10:30:00+00:00',
      };
      value.schedule.effect = {
        morningMassDeltaF: -1.5,
        hallwayPeakDeltaF: -0.75,
      };
    });
    const expectedOpen = new Date(payload.schedule.candidate.ventOpenAt)
      .toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const expectedClose = new Date(payload.schedule.candidate.ventCloseAt)
      .toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

    const result = parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS);

    expect(result.ventWindow).toBe(`${expectedOpen}–${expectedClose}`);
    expect(result.effect).toEqual({
      morningMassDeltaF: -1.5,
      hallwayPeakDeltaF: -0.75,
    });
  });

  it('marks results stale only after three hours', () => {
    expect(parseThermalModelResult(
      JSON.stringify(validShadow),
      GENERATED_AT_MS + 3 * 60 * 60_000,
    ).state).toBe('ready');
    expect(parseThermalModelResult(
      JSON.stringify(validShadow),
      GENERATED_AT_MS + 3 * 60 * 60_000 + 1,
    ).state).toBe('stale');
  });

  it('marks results unavailable only after twenty-six hours', () => {
    expect(parseThermalModelResult(
      JSON.stringify(validShadow),
      GENERATED_AT_MS + 26 * 60 * 60_000,
    ).state).toBe('stale');
    expect(parseThermalModelResult(
      JSON.stringify(validShadow),
      GENERATED_AT_MS + 26 * 60 * 60_000 + 1,
    ).state).toBe('unavailable');
  });

  it('keeps a structurally valid unavailable shadow unavailable and strips advice fields', () => {
    const result = parseThermalModelResult(
      JSON.stringify(unavailableFixture()),
      GENERATED_AT_MS,
    );

    expect(result).toMatchObject({
      state: 'unavailable',
      badge: 'SHADOW',
      hallwayHigh: null,
      hallwayLow: null,
      morningMass: null,
      ventWindow: null,
      effect: { morningMassDeltaF: null, hallwayPeakDeltaF: null },
      confidence: 'unavailable',
      trajectory: [],
      observed: [],
      reasons: ['stale hallway temperature'],
    });
  });

  it.each(['', 'NULL', 'UNDEF', '{bad', '{"version":2}'])('fails closed for %s', (raw) => {
    expect(parseThermalModelResult(raw, GENERATED_AT_MS).state).toBe('unavailable');
  });

  it.each([
    ['an advisory status', (payload) => { payload.status = 'advisory'; }],
    ['a partial top-level payload', (payload) => { delete payload.schedule; }],
    ['a partial forecast row', (payload) => { delete payload.forecast.trajectory[0].massF; }],
    ['an unknown top-level field', (payload) => { payload.command = 'open vents'; }],
    ['an unknown action marker', (payload) => { payload.forecast.trajectory[1].actions = ['vent_start']; }],
    ['an incomplete candidate schedule', (payload) => {
      payload.schedule.candidate = { ventOpenAt: '2026-08-14T03:00:00+00:00' };
    }],
  ])('fails closed for %s', (_label, mutate) => {
    const payload = fixture(mutate);
    const result = parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS);

    expect(result.state).toBe('unavailable');
    expect(result.ventWindow).toBeNull();
    expect(result.trajectory).toEqual([]);
  });

  it.each([
    ['a numeric string', (payload) => { payload.forecast.hallwayHighF = '80'; }],
    ['a boolean', (payload) => { payload.schedule.effect.hallwayPeakDeltaF = false; }],
    ['a non-finite JSON number', null],
  ])('rejects %s rather than coercing it', (_label, mutate) => {
    const raw = mutate
      ? JSON.stringify(fixture(mutate))
      : JSON.stringify(validShadow).replace('"hallwayHighF":80', '"hallwayHighF":1e309');

    expect(parseThermalModelResult(raw, GENERATED_AT_MS).state).toBe('unavailable');
  });

  it('accepts semantically exact sensor provenance regardless of object key order', () => {
    const payload = fixture((value) => {
      const items = value.provenance.sensorItems;
      value.provenance.sensorItems = {
        radiation: items.radiation,
        outdoor: items.outdoor,
        glazing: items.glazing,
        mass: items.mass,
        air: items.air,
      };
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state).toBe('ready');
  });

  it('preserves bounded printable Unicode reasons from the Task 8 contract', () => {
    const payload = fixture((value) => {
      value.reasons = ['modeled spread is 2°F'];
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).reasons)
      .toEqual(['modeled spread is 2°F']);
  });

  it('rejects future-generated results and invalid clocks', () => {
    expect(parseThermalModelResult(
      JSON.stringify(validShadow),
      GENERATED_AT_MS - 1,
    ).state).toBe('unavailable');
    expect(parseThermalModelResult(JSON.stringify(validShadow), Number.NaN).state)
      .toBe('unavailable');
  });
});
