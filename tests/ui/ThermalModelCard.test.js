// @vitest-environment jsdom
import { readFileSync } from 'node:fs';

import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `../../node_modules/svelte/src/index-client.js`
));

import ThermalModelCard from '../../src/lib/ui/ThermalModelCard.svelte';

const NOW = Date.parse('2026-08-13T12:30:00Z');

function readyResult(overrides = {}) {
  return {
    state: 'ready',
    badge: 'SHADOW',
    generatedAtMs: NOW - 30 * 60_000,
    hallwayHigh: 80,
    hallwayLow: 68,
    morningMass: 70,
    ventWindow: '9:00 PM–4:30 AM',
    effect: { morningMassDeltaF: -1.5, hallwayPeakDeltaF: 0 },
    confidence: 'low',
    trajectory: [
      { atMs: NOW, hallwayF: 74, massF: 72, lowF: 73, highF: 75, actions: [] },
      { atMs: NOW + 60 * 60_000, hallwayF: 75, massF: 72.2, lowF: 74, highF: 76, actions: ['vent_open'] },
    ],
    observed: [
      { atMs: NOW - 5 * 60_000, hallwayF: 73.9, massF: 71.9 },
    ],
    reasons: ['candidate evaluated against the learned baseline'],
    ...overrides,
  };
}

afterEach(cleanup);

describe('ThermalModelCard shadow-only presentation', () => {
  it('labels modeled values, candidate timing, confidence, and age without promising action', () => {
    const { container, getByText } = render(ThermalModelCard, {
      result: readyResult(),
      nowMs: NOW,
    });

    expect(getByText('SHADOW')).toBeTruthy();
    expect(getByText('Next hallway high')).toBeTruthy();
    expect(getByText('Next hallway low')).toBeTruthy();
    expect(getByText('80°F')).toBeTruthy();
    expect(getByText('68°F')).toBeTruthy();
    expect(getByText('70°F')).toBeTruthy();
    expect(getByText('9:00 PM–4:30 AM')).toBeTruthy();
    expect(getByText('0°F modeled')).toBeTruthy();
    expect(getByText('−1.5°F modeled')).toBeTruthy();
    expect(getByText(/Low confidence/i)).toBeTruthy();
    expect(getByText(/30m old/i)).toBeTruthy();

    const copy = container.textContent.toLowerCase();
    expect(copy).not.toMatch(/\bsaved\b|\bwill\b|\brecommend(?:ed|ation)?\b|\bautom(?:ate|ation)\b|\bactuat(?:e|or)\b|\bcommand\b/);
    expect(container.querySelector('button, form, input, select, textarea, a[href]')).toBeNull();
  });

  it('renders stale age explicitly while retaining the shadow badge', () => {
    const { getByText } = render(ThermalModelCard, {
      result: readyResult({ state: 'stale', generatedAtMs: NOW - 4 * 60 * 60_000 }),
      nowMs: NOW,
    });

    expect(getByText('SHADOW')).toBeTruthy();
    expect(getByText(/Stale · 4h old/i)).toBeTruthy();
  });

  it('renders unavailable without exposing forecast or candidate copy as advice', () => {
    const { container, getByText, queryByText } = render(ThermalModelCard, {
      result: readyResult({
        state: 'unavailable',
        generatedAtMs: null,
        hallwayHigh: null,
        hallwayLow: null,
        morningMass: null,
        ventWindow: null,
        effect: { morningMassDeltaF: null, hallwayPeakDeltaF: null },
        confidence: 'unavailable',
        trajectory: [],
        observed: [],
        reasons: [],
      }),
      nowMs: NOW,
    });

    expect(getByText('SHADOW')).toBeTruthy();
    expect(getByText('Thermal model unavailable')).toBeTruthy();
    expect(queryByText('Candidate vent window')).toBeNull();
    expect(queryByText(/modeled/i)).toBeNull();
    expect(container.textContent.toLowerCase()).not.toMatch(/recommend|advice|will open|will close/);
  });

  it('uses a native disclosure for the accessible plot and has no scripted event handlers', () => {
    const { container, getByText } = render(ThermalModelCard, {
      result: readyResult(),
      nowMs: NOW,
    });

    const details = container.querySelector('details');
    expect(details).not.toBeNull();
    expect(details.querySelector('summary')).toBe(getByText('Model details'));
    expect(details.querySelector('svg[role="img"][aria-label]')).not.toBeNull();

    const source = readFileSync('src/lib/ui/ThermalModelCard.svelte', 'utf8');
    expect(source).not.toMatch(/\bon(?:click|change|input|submit|keydown|keyup|pointerdown|pointerup)\s*=/i);
    const plotSource = readFileSync('src/lib/ui/ThermalModelPlot.svelte', 'utf8');
    expect(plotSource).not.toMatch(/\bon(?:click|change|input|submit|keydown|keyup|pointerdown|pointerup)\s*=/i);
  });
});
