// @vitest-environment jsdom
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
import HouseholdObservation from '../../src/lib/ui/HouseholdObservation.svelte';
import { observation, proposal, AT } from '../fixtures/household-observation.js';

afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function serve(row) {
  vi.spyOn(Date, 'now').mockReturnValue(AT);
  const fetcher = vi.fn(async url => new Response(JSON.stringify(url === '/api/household-observation' ? row : { status: 'unavailable' }), { status: 200 }));
  vi.stubGlobal('fetch', fetcher); return fetcher;
}
describe('Earthship household observation panels', () => {
  it('shows mode, snapshot age, models, no selection, confidence and unavailable owner comparison', async () => {
    const row = observation(); const fetcher = serve(row);
    const { container, getByText, unmount } = render(HouseholdObservation);
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
    const { container, getByText } = render(HouseholdObservation);
    await waitFor(() => expect(getByText('RUN_FEEDER_CYCLE')).toBeTruthy());
    expect(container.textContent).toContain('battery reserve: unknown');
    expect(container.textContent).toContain('unqualified effect');
    expect(container.textContent).toContain('batteryKwh: unknown');
    expect(container.textContent).toContain('Shadow proposal');
  });
  it('withholds current planning for an expired artifact while keeping identities inspectable', async () => {
    const row = observation(); serve(row); vi.spyOn(Date, 'now').mockReturnValue(AT + 60_000);
    const { container, getByText } = render(HouseholdObservation);
    await waitFor(() => expect(getByText('Original plan expired')).toBeTruthy());
    expect(getByText('Unavailable')).toBeTruthy();
    expect(container.textContent).toContain(row.snapshot_id);
    expect(container.textContent).toContain('expired');
  });
  it('fails unavailable on bad transport without rendering raw private fields', async () => {
    serve({ private_path: '/operator-only-path' });
    const { container, getByText } = render(HouseholdObservation);
    await waitFor(() => expect(getByText('Verified observation unavailable')).toBeTruthy());
    expect(container.textContent).not.toContain('/operator-only-path');
  });
});

it('recalculates original expiry on polling and stops all requests after navigation', async () => {
  const row = observation(); const fetcher = serve(row);
  vi.useFakeTimers();
  const { container, unmount } = render(HouseholdObservation);
  await vi.advanceTimersByTimeAsync(1);
  expect(container.textContent).toContain('Shadow');
  vi.spyOn(Date, 'now').mockReturnValue(AT + 60_000);
  await vi.advanceTimersByTimeAsync(30_000);
  expect(container.textContent).toContain('Original plan expired');
  expect(fetcher).toHaveBeenCalledTimes(6);
  unmount();
  await vi.advanceTimersByTimeAsync(90_000);
  expect(fetcher).toHaveBeenCalledTimes(6);
});

it('expires the displayed plan independently of a slow network polling interval', async () => {
  const fetcher = serve(observation()); vi.useFakeTimers();
  const { container } = render(HouseholdObservation);
  await vi.advanceTimersByTimeAsync(1);
  expect(container.textContent).toContain('Shadow');
  vi.spyOn(Date, 'now').mockReturnValue(AT + 60_000);
  await vi.advanceTimersByTimeAsync(1_000);
  expect(container.textContent).toContain('Original plan expired');
  expect(fetcher).toHaveBeenCalledTimes(3);
});

it('shows measured battery baseline errors and distinct empty horizons without requiring current planning', async () => {
  const { batteryPerformance } = await import('../fixtures/household-battery-performance.js');
  vi.spyOn(Date, 'now').mockReturnValue(AT);
  vi.stubGlobal('fetch', async url => new Response(JSON.stringify(url === '/api/household-battery-performance' ? batteryPerformance() : { status: 'unavailable' })));
  const { container, getByText } = render(HouseholdObservation);
  await waitFor(() => expect(container.textContent).toContain('2.56'));
  expect(getByText('Battery forecast accuracy')).toBeTruthy(); expect(container.textContent).toContain('5.00');
  expect(container.textContent).toContain('percentage points'); expect(container.textContent).toContain('Collecting');
  expect(container.textContent).toContain('Assumes current battery power continues');
  expect(container.querySelector('button, form, input, select')).toBeNull();
});

async function serveCapturedPv(row) {
  vi.spyOn(Date, 'now').mockReturnValue(AT);
  vi.stubGlobal('fetch', async url => new Response(JSON.stringify(url === '/api/household-captured-pv-performance' ? row : { status: 'unavailable' })));
}
it('renders captured-controller PV paired errors and uncollected learned horizons independently of planning', async () => {
  const { capturedPvPerformance } = await import('../fixtures/household-captured-pv.js');
  await serveCapturedPv(capturedPvPerformance());
  const { container, getByText } = render(HouseholdObservation);
  await waitFor(() => expect(getByText('Captured-PV forecast accuracy')).toBeTruthy());
  await waitFor(() => expect(container.textContent).toContain('0.300'));
  expect(container.textContent).toContain('0.200'); expect(container.textContent).toContain('-50.0%');
  expect(container.textContent).toContain('99%'); expect(container.textContent).toContain('same observed intervals');
  expect(container.textContent).toContain('Controller DC output'); expect(container.textContent).toContain('Potential array yield remains unscored');
  expect(container.textContent).toContain('Learned AC load'); expect(container.textContent).toContain('Collecting');
  expect(container.querySelector('button, form, input, select')).toBeNull();
});
it('marks captured-PV stale on the display clock and withholds malformed accuracy', async () => {
  const { capturedPvPerformance } = await import('../fixtures/household-captured-pv.js');
  await serveCapturedPv(capturedPvPerformance()); vi.useFakeTimers();
  const { container } = render(HouseholdObservation); await vi.advanceTimersByTimeAsync(1);
  expect(container.textContent).toContain('0.300');
  vi.spyOn(Date, 'now').mockReturnValue(AT + 31 * 60000); await vi.advanceTimersByTimeAsync(1000);
  expect(container.textContent).toContain('Captured-PV accuracy report is stale');
});
it('does not expose malformed captured-PV fields or claim accuracy from an unavailable report', async () => {
  await serveCapturedPv({ private_path: '/do-not-display', automatic_actuation: true });
  const { container, getByText } = render(HouseholdObservation);
  await waitFor(() => expect(getByText('Captured-PV accuracy report unavailable')).toBeTruthy());
  expect(container.textContent).not.toContain('/do-not-display');
});
it('shows an as-issued matching greywater block without implying performance or physical permission', async () => {
  const { policyObservation }=await import('../fixtures/household-observation.js');serve(policyObservation());
  const {container,getByText}=render(HouseholdObservation);
  await waitFor(()=>expect(getByText('Observed greywater policy')).toBeTruthy());
  expect(container.textContent).toContain('matching block');expect(container.textContent).toContain('after dark');
  expect(container.textContent).toContain('Action eligibility and performance benefits remain unknown');
  expect(container.querySelector('button, form, input, select')).toBeNull();
});
it('expires the displayed owner observation at its original clock independently of polling', async () => {
  const {policyObservation}=await import('../fixtures/household-observation.js');serve(policyObservation());vi.useFakeTimers();
  const {container}=render(HouseholdObservation);await vi.advanceTimersByTimeAsync(1);
  vi.spyOn(Date,'now').mockReturnValue(AT+120000);await vi.advanceTimersByTimeAsync(1000);
  expect(container.textContent).toContain('Owner policy observation is stale');
});
