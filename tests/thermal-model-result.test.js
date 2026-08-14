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

  it('preserves model timestamps and finite zero ages in the normalized view model', () => {
    const payload = fixture((value) => {
      value.model.createdAt = value.generatedAt;
      value.model.trainedThrough = value.generatedAt;
      value.provenance.modelAgeHours = 0;
      value.provenance.trainingDataAgeHours = 0;
    });

    const result = parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS);

    expect(result).toMatchObject({
      modelCreatedAtMs: GENERATED_AT_MS,
      trainedThroughMs: GENERATED_AT_MS,
      modelAgeHours: 0,
      trainingDataAgeHours: 0,
    });
  });

  it('preserves stale model and training ages independently of fresh output age', () => {
    const payload = fixture((value) => {
      value.model.createdAt = '2026-08-10T12:00:00Z';
      value.model.trainedThrough = '2026-08-09T12:00:00Z';
      value.provenance.modelAgeHours = 72;
      value.provenance.trainingDataAgeHours = 96;
      value.reasons = ['accepted model daily training cadence missed'];
    });

    const result = parseThermalModelResult(
      JSON.stringify(payload), GENERATED_AT_MS + 10 * 60_000,
    );

    expect(result.state).toBe('ready');
    expect(result.modelAgeHours).toBe(72);
    expect(result.trainingDataAgeHours).toBe(96);
    expect(result.reasons).toEqual(['accepted model daily training cadence missed']);
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

  it('rejects impossible calendar dates instead of accepting Date.parse normalization', () => {
    const raw = JSON.stringify(validShadow)
      .replaceAll('2026-08-13', '2026-02-30')
      .replaceAll('2026-08-14', '2026-03-03');
    const normalizedNow = Date.parse('2026-03-02T12:10:00Z');

    expect(parseThermalModelResult(raw, normalizedNow).state).toBe('unavailable');
  });

  it.each([
    ['a normalized 24:00 hour', '2026-08-13T24:00:00+00:00'],
    ['an out-of-range timezone offset', '2026-08-13T18:00:00+24:00'],
  ])('rejects %s in every timestamp field', (_label, timestamp) => {
    const payload = fixture((value) => {
      value.forecast.hallwayHighAt = timestamp;
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('unavailable');
  });

  it('rejects model chronology hidden below millisecond precision across offsets', () => {
    const payload = fixture((value) => {
      value.model.createdAt = '2026-08-13T11:00:00.000100+01:00';
      value.model.trainedThrough = '2026-08-13T10:00:00.000900Z';
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('unavailable');
  });

  it('accepts strictly ordered submillisecond observations across offsets', () => {
    const payload = fixture((value) => {
      value.forecast.observed = [
        { at: '2026-08-13T11:55:00.000100Z', hallwayF: 73.8, massF: 71.8 },
        { at: '2026-08-13T12:55:00.000900+01:00', hallwayF: 73.9, massF: 71.9 },
      ];
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('ready');
  });

  it('accepts a complete submillisecond schedule window', () => {
    const payload = fixture((value) => {
      value.schedule.baseline = {
        ventOpenAt: '2026-08-14T02:30:00.000100Z',
        ventCloseAt: '2026-08-14T02:30:00.000900Z',
      };
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('ready');
  });

  it('rejects a submillisecond future observation expressed with another offset', () => {
    const payload = fixture((value) => {
      value.forecast.observed[0].at = '2026-08-13T13:00:00.000100+01:00';
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('unavailable');
  });

  it('rejects a submillisecond forecast time beyond the exact horizon boundary', () => {
    const payload = fixture((value) => {
      value.forecast.hallwayHighAt = '2026-08-14T12:00:00.000100Z';
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('unavailable');
  });

  it('rejects a generated instant microscopically ahead of the millisecond clock', () => {
    const payload = fixture((value) => {
      value.generatedAt = '2026-08-13T12:00:00.000100Z';
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('unavailable');
  });

  it('uses the generated offset when computing the exact local horizon boundary', () => {
    const payload = fixture((value) => {
      value.generatedAt = '2026-08-13T12:02:00+00:02';
      value.forecast.hallwayHighAt = '2026-08-14T11:59:00Z';
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('unavailable');
  });

  it('matches Python microsecond truncation for longer fractional seconds', () => {
    const payload = fixture((value) => {
      value.model.createdAt = '2026-08-13T10:00:00.0001001Z';
      value.model.trainedThrough = '2026-08-13T10:00:00.0001009Z';
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('ready');
  });

  it.each([
    ['zero-width format', '\u200b'],
    ['private-use', '\ue000'],
    ['non-breaking separator', '\u00a0'],
  ])('rejects canonical non-printable %s characters in reasons', (_label, character) => {
    const payload = fixture((value) => {
      value.reasons = [`modeled${character}spread`];
    });

    expect(parseThermalModelResult(JSON.stringify(payload), GENERATED_AT_MS).state)
      .toBe('unavailable');
  });

  it('counts raw UTF-8 bytes before trimming surrounding JSON whitespace', () => {
    const json = JSON.stringify(validShadow);
    const padding = ' '.repeat(16 * 1024 - new TextEncoder().encode(json).length);
    const raw = `${padding}${json}`;
    expect(new TextEncoder().encode(raw)).toHaveLength(16 * 1024);

    expect(parseThermalModelResult(raw, GENERATED_AT_MS).state).toBe('unavailable');
  });

  it.each([
    ['a leading BOM', (json) => '\uFEFF' + json],
    ['a trailing BOM', (json) => json + '\uFEFF'],
    ['leading non-breaking space', (json) => '\u00A0' + json],
    ['trailing line separator', (json) => json + '\u2028'],
  ])('rejects valid JSON wrapped in %s', (_label, wrap) => {
    expect(parseThermalModelResult(wrap(JSON.stringify(validShadow)), GENERATED_AT_MS).state)
      .toBe('unavailable');
  });

  it('accepts surrounding JSON whitespace when the complete raw state stays below 16 KiB', () => {
    const raw = ' \n' + JSON.stringify(validShadow) + '\t ';

    expect(parseThermalModelResult(raw, GENERATED_AT_MS).state).toBe('ready');
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
