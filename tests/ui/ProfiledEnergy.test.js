// @vitest-environment jsdom
import { cleanup, render, waitFor, fireEvent } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
import ProfiledEnergy from '../../src/lib/ui/ProfiledEnergy.svelte';
import { profiledObservation, profiledPerformance, PROFILE_NOW } from '../fixtures/household-profiled-energy.js';
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function serve(view = profiledObservation(), report = profiledPerformance(), at = PROFILE_NOW) {
  vi.spyOn(Date, 'now').mockReturnValue(at);
  vi.stubGlobal('fetch', async url => new Response(JSON.stringify(url === '/api/household-profiled-energy-observation' ? view : report)));
}
it('shows learned load alongside the original constant assumption and matched errors', async () => {
  serve(); const { container, getByLabelText } = render(ProfiledEnergy);
  await waitFor(() => expect(container.textContent).toContain('9.60 kWh'));
  expect(container.textContent).toContain('500 W'); expect(container.textContent).toContain('400 W');
  expect(container.textContent).toContain('Training data through'); expect(container.textContent).toContain('0.050');
  expect(container.textContent).toContain('Collecting'); expect(container.textContent).toContain('Constant power'); expect(container.textContent).toContain('Hold SoC'); expect(container.querySelectorAll('svg[aria-label]')).toHaveLength(2);
  await fireEvent.input(getByLabelText('Demand forecast hour'), { target: { value: '6' } });
  expect(container.textContent).toContain('Hour 6'); expect(container.querySelector('form')).toBeNull();
});
it('labels old forecasts and reports stale without changing the original source dates', async () => {
  serve(profiledObservation(), profiledPerformance(), PROFILE_NOW + 40 * 60000); const { container } = render(ProfiledEnergy);
  await waitFor(() => expect(container.textContent).toContain('Demand forecast is stale'));
  expect(container.textContent).toContain('Demand accuracy report is stale');
});
it('withholds a different algorithm cohort rather than mixing its errors', async () => {
  const report = profiledPerformance(); report.cohort_id = 'f'.repeat(64); serve(profiledObservation(), report);
  const { container } = render(ProfiledEnergy);
  await waitFor(() => expect(container.textContent).toContain('Collecting comparisons for this model'));
  expect(container.textContent).not.toContain('0.050');
});
