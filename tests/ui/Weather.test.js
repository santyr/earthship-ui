// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
));

vi.mock('echarts', () => ({
  init: vi.fn(() => ({
    dispose: vi.fn(),
    resize: vi.fn(),
    setOption: vi.fn(),
  })),
}));

import Weather from '../../src/screens/Weather.svelte';
import { items } from '../../src/lib/openhab/store.js';

const BASE_ITEMS = {
  Forecast_AQI: 'REFRESH',
  Forecast_Hourly_JSON: '[]',
  Forecast_Daily_JSON: '[]',
};

describe('Weather current AQI', () => {
  beforeEach(() => {
    items.set({ ...BASE_ITEMS });
  });

  afterEach(() => {
    cleanup();
    items.set({});
  });

  it('ignores Forecast_AQI and names missing current AQI as unavailable', () => {
    const { container } = render(Weather);

    expect(screen.getByText('Modeled US AQI')).toBeTruthy();
    expect(screen.getByText('Unavailable')).toBeTruthy();
    expect(container.querySelector('.aqi-body')?.getAttribute('data-source-item'))
      .toBe('Current_US_AQI');
    expect(container.querySelector('.aqi-body')?.textContent).not.toContain('REFRESH');
  });

  it('keeps a numeric Current_US_AQI above 500 visible and critical', () => {
    items.set({
      ...BASE_ITEMS,
      Forecast_AQI: 'Good',
      Current_US_AQI: '501',
    });

    const { container } = render(Weather);
    const body = container.querySelector('.aqi-body');

    expect(screen.getByText('501')).toBeTruthy();
    expect(body?.getAttribute('data-aqi-status')).toBe('critical');
    expect(body?.textContent).not.toContain('Good');
  });
});
