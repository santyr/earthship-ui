// @vitest-environment jsdom
import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `/home/sat/earthship-ui/node_modules/svelte/src/index-client.js`
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
});

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
