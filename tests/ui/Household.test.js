// @vitest-environment jsdom
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
import Household from '../../src/screens/Household.svelte';
import { observation, proposal, AT } from '../fixtures/household-observation.js';

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function serve(row) {
  vi.spyOn(Date, 'now').mockReturnValue(AT);
  const fetcher = vi.fn(async () => new Response(JSON.stringify(row), { status: 200 }));
  vi.stubGlobal('fetch', fetcher); return fetcher;
}
describe('household operator inspection', () => {
  it('shows mode, snapshot age, models, no selection, confidence and unavailable owner comparison', async () => {
    const row = observation(); const fetcher = serve(row);
    const { container, getByText, unmount } = render(Household);
    await waitFor(() => expect(getByText('Shadow')).toBeTruthy());
    expect(getByText('20 seconds')).toBeTruthy();
    expect(getByText('No action selected')).toBeTruthy();
    expect(getByText('Effects unqualified')).toBeTruthy();
    expect(getByText(/Current OpenHAB policy comparison: unavailable/)).toBeTruthy();
    expect(container.textContent).toContain(row.model_identities[0].projection_sha256);
    expect(container.textContent).toContain('battery soc');
    expect(container.textContent).toContain('Confidence: unavailable');
    expect(container.querySelector('button, form, input, select')).toBeNull();
    expect(fetcher.mock.calls[0][0]).toBe('/api/household-observation');
    const signal = fetcher.mock.calls[0][1].signal;
    unmount(); expect(signal.aborted).toBe(true);
  });
  it('shows proposed effects as unknown and exposes the blocking hard constraint', async () => {
    const row = observation(); row.proposals = [proposal()]; serve(row);
    const { container, getByText } = render(Household);
    await waitFor(() => expect(getByText('RUN_FEEDER_CYCLE')).toBeTruthy());
    expect(container.textContent).toContain('battery reserve: unknown');
    expect(container.textContent).toContain('unqualified effect');
    expect(container.textContent).toContain('batteryKwh: unknown');
    expect(container.textContent).toContain('Shadow proposal');
  });
  it('withholds current planning for an expired artifact while keeping identities inspectable', async () => {
    const row = observation(); serve(row); vi.spyOn(Date, 'now').mockReturnValue(AT + 60_000);
    const { container, getByText } = render(Household);
    await waitFor(() => expect(getByText('Original plan expired')).toBeTruthy());
    expect(getByText('Unavailable')).toBeTruthy();
    expect(container.textContent).toContain(row.snapshot_id);
    expect(container.textContent).toContain('expired');
  });
  it('fails unavailable on bad transport without rendering raw private fields', async () => {
    serve({ private_path: '/operator-only-path' });
    const { container, getByText } = render(Household);
    await waitFor(() => expect(getByText('Verified observation unavailable')).toBeTruthy());
    expect(container.textContent).not.toContain('/operator-only-path');
  });
});

it('recalculates original expiry on polling and stops all requests after navigation', async () => {
  const row = observation(); const fetcher = serve(row);
  vi.useFakeTimers();
  const { container, unmount } = render(Household);
  await vi.advanceTimersByTimeAsync(1);
  expect(container.textContent).toContain('Shadow');
  vi.spyOn(Date, 'now').mockReturnValue(AT + 60_000);
  await vi.advanceTimersByTimeAsync(30_000);
  expect(container.textContent).toContain('Original plan expired');
  expect(fetcher).toHaveBeenCalledTimes(2);
  unmount();
  await vi.advanceTimersByTimeAsync(90_000);
  expect(fetcher).toHaveBeenCalledTimes(2);
});
