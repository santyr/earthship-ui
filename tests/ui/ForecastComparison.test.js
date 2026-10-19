// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
import ForecastComparison from '../../src/lib/ui/ForecastComparison.svelte';
import fixture from '../fixtures/weathernext-shadow-v2.json';
afterEach(cleanup);
const raw = JSON.stringify(fixture);
const props = { statusRaw: raw, comparisonRaw: raw, localRaw: raw, nowMs: Date.parse('2026-01-01T00:31:00Z') };
it('opens an accessible read-only comparison with distinct sources and evidence', async () => {
  render(ForecastComparison, props);
  await fireEvent.click(screen.getByRole('button', { name: /WeatherNext model/ }));
  const dialog = screen.getByRole('dialog');
  expect(dialog.textContent).toContain('Shadow — not controlling equipment');
  expect(within(screen.getAllByRole('row')[0]).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(['Local time','Raw WeatherNext','Local candidate']);
  expect(dialog.textContent).toContain('Raw WeatherNext');
  expect(dialog.textContent).toContain('Local candidate');
  expect(dialog.textContent).toContain('1 training pair');
  expect(dialog.textContent).toContain('Validation unavailable');
  expect(screen.queryByRole('button', { name: /apply|actuate|run/i })).toBeNull();
  await fireEvent.keyDown(dialog, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).toBeNull();
});
it('shows stale status without presenting old temperatures as current', async () => {
  render(ForecastComparison, { ...props, nowMs: props.nowMs + 3 * 3600000 });
  await fireEvent.click(screen.getByRole('button', { name: /WeatherNext model/ }));
  expect(screen.getByRole('dialog').textContent).toContain('WeatherNext forecast stale');
  expect(screen.queryByRole('table')).toBeNull();
});
