// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `../../node_modules/svelte/src/index-client.js`
));

import ThermalModelPlot from '../../src/lib/ui/ThermalModelPlot.svelte';

const HOUR = 60 * 60_000;
const START = Date.parse('2026-08-13T12:00:00Z');

afterEach(cleanup);

describe('ThermalModelPlot bounded SVG', () => {
  it('draws observed and forecast air/mass, interval, and typed action markers accessibly', () => {
    const trajectory = [
      { atMs: START, hallwayF: 74, massF: 72, lowF: 73, highF: 75, actions: [] },
      {
        atMs: START + HOUR,
        hallwayF: 75,
        massF: 72.5,
        lowF: 74,
        highF: 76,
        actions: ['vent_open', 'indoor_shade_close'],
      },
    ];
    const observed = [
      { atMs: START - 5 * 60_000, hallwayF: 73.8, massF: 71.8 },
      { atMs: START, hallwayF: 74, massF: 72 },
    ];
    const { container } = render(ThermalModelPlot, { trajectory, observed });

    const svg = container.querySelector('svg');
    expect(svg.getAttribute('role')).toBe('img');
    expect(svg.getAttribute('aria-label')).toMatch(/observed.*hallway.*mass.*forecast.*interval.*action/i);
    expect(container.querySelectorAll('[data-series="observed-hallway"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-series="observed-mass"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-series="forecast-hallway"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-series="forecast-mass"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-series="forecast-interval"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-action="vent_open"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-action="indoor_shade_close"]')).toHaveLength(1);
  });

  it('preserves missing-time gaps instead of connecting or inventing points', () => {
    const trajectory = [
      { atMs: START, hallwayF: 74, massF: 72, lowF: 73, highF: 75, actions: [] },
      { atMs: START + HOUR, hallwayF: 75, massF: 72.5, lowF: 74, highF: 76, actions: [] },
      { atMs: START + 3 * HOUR, hallwayF: 77, massF: 73, lowF: 76, highF: 78, actions: ['not_a_marker'] },
    ];
    const observed = [
      { atMs: START - 2 * HOUR, hallwayF: 72, massF: 71 },
      { atMs: START - 115 * 60_000, hallwayF: 72.2, massF: 71.1 },
      { atMs: START - 5 * 60_000, hallwayF: 73.8, massF: 71.8 },
    ];
    const { container } = render(ThermalModelPlot, { trajectory, observed });

    expect(container.querySelectorAll('[data-series="forecast-hallway"]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-series="forecast-mass"]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-series="forecast-interval"]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-series="observed-hallway"]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-series="observed-mass"]')).toHaveLength(2);
    expect(container.querySelectorAll('[data-point="forecast"]')).toHaveLength(3);
    expect(container.querySelectorAll('[data-point="observed"]')).toHaveLength(3);
    expect(container.querySelector('[data-action="not_a_marker"]')).toBeNull();
  });

  it('renders an accessible empty state without an SVG when no series exists', () => {
    const { container, getByText } = render(ThermalModelPlot, {
      trajectory: [],
      observed: [],
    });

    expect(getByText('No thermal model series available')).toBeTruthy();
    expect(container.querySelector('svg')).toBeNull();
  });
});
