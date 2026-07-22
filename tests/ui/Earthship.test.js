// @vitest-environment jsdom
import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `../../node_modules/svelte/src/index-client.js`
));

import Earthship from '../../src/screens/Earthship.svelte';
import { items } from '../../src/lib/openhab/store.js';
import { chartStore, closeChart } from '../../src/lib/ui/chartStore.js';

beforeEach(() => {
  items.set({
    AmbientWeatherWS2902A_WH31E_193_Temperature: '66.8',
    AmbientWeatherWS2902A_IndoorSensor_Temperature: '69.1',
    Shelly_HT1_Indoor_Temperature: '71.5',
    AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature: '68.2',
  });
});

afterEach(() => {
  cleanup();
  closeChart();
  items.set({});
  vi.useRealTimers();
});

function setItems(extra = {}) {
  items.update((current) => ({ ...current, ...extra }));
}

describe('Earthship four-zone thermal contract', () => {
  it('opens history in physical left-to-right order using the four live items', async () => {
    const { container } = render(Earthship);

    expect([...container.querySelectorAll('.zone-label')].map((node) => node.textContent))
      .toEqual(['North Mass', 'Room Air', 'South Wall', 'Outdoor']);
    expect([...container.querySelectorAll('.humidity-label')].map((node) => node.textContent))
      .toEqual(['North Mass', 'Room Air', 'South Wall']);

    await fireEvent.click(container.querySelector('.zone-group'));
    const chart = get(chartStore);
    expect(chart.series.map(({ label }) => label))
      .toEqual(['North Mass', 'Room Air', 'South Wall', 'Outdoor']);
    expect(chart.series.map(({ name }) => name)).toEqual([
      'AmbientWeatherWS2902A_WH31E_193_Temperature',
      'AmbientWeatherWS2902A_IndoorSensor_Temperature',
      'Shelly_HT1_Indoor_Temperature',
      'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
    ]);
  });
});

describe('Earthship greywater honesty', () => {
  it('renders Unavailable when the switch state is missing, matching Home semantics', () => {
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-state').textContent).toBe('Unavailable');
  });

  it.each([
    ['NULL', 'Unavailable'],
    ['UNDEF', 'Unavailable'],
    ['OFF', 'Idle'],
    ['ON', 'Running'],
  ])('renders switch state %s as %s', (state, label) => {
    setItems({ SouthOutlet_Outlet2_Switch: state });
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-state').textContent).toBe(label);
  });

  it('lights the running dot only for ON', () => {
    setItems({ SouthOutlet_Outlet2_Switch: 'ON' });
    const running = render(Earthship);
    expect(running.container.querySelector('.gw-dot.active')).not.toBeNull();
    cleanup();

    setItems({ SouthOutlet_Outlet2_Switch: 'NULL' });
    const unavailable = render(Earthship);
    expect(unavailable.container.querySelector('.gw-dot.active')).toBeNull();
  });

  it('carries fallback minutes into hours without a "1h 60m" boundary', () => {
    setItems({ SouthOutlet_AutoStatus: 'reason=waiting_for_solar,fallbackInMin=119.6' });
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-status').textContent)
      .toBe('waiting for solar · fallback in 2h 0m');
  });
});

describe('Earthship last-run wall clock', () => {
  it('advances the "last run" label on a quiet stream via the minute tick', async () => {
    vi.useFakeTimers();
    const { tick } = await import('../../node_modules/svelte/src/index-client.js');
    setItems({
      SouthOutlet_LastAutoRun: new Date(Date.now() - 2 * 60_000).toISOString(),
    });
    const { container } = render(Earthship);
    const footer = () => container.querySelector('.gw-footer span').textContent;
    expect(footer()).toBe('last run 2 m ago');

    // No item changes at all — only wall-clock time passes.
    vi.advanceTimersByTime(10 * 60_000);
    await tick();
    expect(footer()).toBe('last run 12 m ago');
  });
});
