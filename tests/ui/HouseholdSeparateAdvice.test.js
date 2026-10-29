// @vitest-environment jsdom
import { cleanup, render, waitFor } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
import HouseholdObservation from '../../src/lib/ui/HouseholdObservation.svelte';
import { householdObservationRaw, recommendationClock } from '../../src/lib/household/recommendationState.js';
vi.mock('../../src/lib/household/recommendationState.js', async () => { const { writable } = await import('svelte/store'); return { householdObservationRaw: writable(null), recommendationClock: writable(0) }; });
import { separateAdvice, ADVICE_AT } from '../fixtures/household-separate-advice.js';
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
it.each([false, true])('renders separate advice honestly with model-present=%s and no command affordance', async shadow => {
  const row = separateAdvice({ shadow });
  householdObservationRaw.set(JSON.stringify(row)); recommendationClock.set(ADVICE_AT);
  vi.stubGlobal('fetch', async () => new Response('{"status":"unavailable"}'));
  const { container, getByText } = render(HouseholdObservation);
  await waitFor(() => expect(getByText('Human advice is separate')).toBeTruthy());
  expect(container.textContent).toContain('No command proposals are generated');
  expect(container.textContent).toContain('No intent families are assessed');
  expect(container.textContent).toContain('Effects unqualified');
  expect(container.textContent).toContain(row.snapshot_id);
  expect(container.textContent).toContain('input incomplete');
  expect(container.querySelector('button, form, input, select')).toBeNull();
  recommendationClock.set(ADVICE_AT + 40000);
  await waitFor(() => expect(getByText('Original plan expired')).toBeTruthy());
  expect(container.textContent).toContain(row.receipt_sha256);
});
