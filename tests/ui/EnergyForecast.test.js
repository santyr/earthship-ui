// @vitest-environment jsdom
import { cleanup, render, waitFor, fireEvent } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
import EnergyForecast from '../../src/lib/ui/EnergyForecast.svelte';
import { energyObservation, energyPerformance, ENERGY_NOW } from '../fixtures/household-energy.js';
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function serve(energy = energyObservation(), performance = energyPerformance(), at = ENERGY_NOW) {
  vi.spyOn(Date, 'now').mockReturnValue(at);
  vi.stubGlobal('fetch', async url => new Response(JSON.stringify(url === '/api/household-energy-observation' ? energy : performance)));
}
it('shows distinct potential/capture, hourly inspection and matched three-model errors', async () => {
  serve(); const { container, getByLabelText } = render(EnergyForecast);
  await waitFor(() => expect(container.textContent).toContain('12.00 kWh'));
  expect(container.textContent).toContain('9.60 kWh'); expect(container.textContent).toContain('380 W');
  expect(container.textContent).toContain('Solar/load scenario'); expect(container.textContent).toContain('Constant power'); expect(container.textContent).toContain('Hold SoC');
  expect(container.textContent).toContain('1.00'); expect(container.textContent).toContain('2.00'); expect(container.textContent).toContain('3.00');
  expect(container.textContent).toContain('Collecting'); expect(container.querySelector('svg[aria-label]')).not.toBeNull();
  const slider = getByLabelText('Forecast hour'); await fireEvent.input(slider, { target: { value: '6' } });
  expect(container.textContent).toContain('Hour 6'); expect(container.querySelector('form')).toBeNull();
});
it('keeps expired forecasts visibly stale and never turns empty accuracy into zero error', async () => {
  serve(energyObservation(), energyPerformance(), ENERGY_NOW + 40 * 60000); const { container } = render(EnergyForecast);
  await waitFor(() => expect(container.textContent).toContain('Forecast is stale'));
  expect(container.textContent).toContain('Accuracy report is stale'); expect(container.textContent).toContain('Collecting');
});
it('withholds private fields and comparisons from a different model cohort', async () => {
  const performance = energyPerformance(); performance.cohort_id = 'f'.repeat(64); serve(energyObservation(), performance);
  const { container } = render(EnergyForecast);
  await waitFor(() => expect(container.textContent).toContain('Collecting comparisons for this model'));
  expect(container.textContent).not.toContain('1.00');
});
