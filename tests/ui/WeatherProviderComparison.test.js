// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
vi.mock('echarts', () => ({ init: vi.fn(() => ({ dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() })) }));
import Weather from '../../src/screens/Weather.svelte';
import { items, connection } from '../../src/lib/openhab/store.js';
import fixture from '../fixtures/weathernext-shadow-v2.json';
afterEach(() => { cleanup(); items.set({}); connection.set('connecting'); vi.useRealTimers(); });
it('shows the read-only comparison when shadow Items arrive after initial load', async () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-01-01T00:31:00Z'));
  items.set({ Forecast_Hourly_JSON:'[]', Forecast_Daily_JSON:'[]' }); connection.set('live');
  render(Weather);
  expect(screen.queryByRole('button', { name:/WeatherNext model/ })).toBeNull();
  const raw=JSON.stringify(fixture);
  items.set({ Forecast_Hourly_JSON:'[]', Forecast_Daily_JSON:'[]', Forecast_Provider_Status_JSON:raw, Forecast_Comparison_JSON:raw, Forecast_Local_Shadow_JSON:raw });
  await tick();
  await fireEvent.click(screen.getByRole('button', { name:/WeatherNext model/ }));
  const dialog=screen.getByRole('dialog');
  expect(within(dialog).getByText('Raw WeatherNext')).toBeTruthy();
  expect(within(dialog).getByText('Shadow — not controlling equipment')).toBeTruthy();
  expect(within(dialog).queryByRole('button', { name:/apply|actuate|run/i })).toBeNull();
});
