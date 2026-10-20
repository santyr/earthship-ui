// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/svelte';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
const mocks = vi.hoisted(() => ({ config: vi.fn(), init: vi.fn(), stop: vi.fn(), stopAlerts: vi.fn() }));
vi.mock('../../src/lib/config.js', () => ({ loadConfig: mocks.config }));
vi.mock('../../src/lib/openhab/index.js', async importOriginal => ({
  ...await importOriginal(), initOpenhab: mocks.init, stopOpenhab: mocks.stop,
}));
vi.mock('../../src/routes.js', async () => {
  const { readable } = await import('svelte/store'); return { currentRoute: readable('startup-test') };
});
vi.mock('../../src/lib/alerts/alertStore.js', async importOriginal => ({
  ...await importOriginal(), startStalenessMonitor: () => mocks.stopAlerts,
}));
import App from '../../src/App.svelte';
beforeEach(() => {
  vi.useFakeTimers(); mocks.config.mockReset(); mocks.init.mockReset(); mocks.stop.mockClear(); mocks.stopAlerts.mockClear();
  mocks.init.mockResolvedValue({});
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

it('retries a transient config failure and starts OpenHAB without reloading the application', async () => {
  const config = { openhabUrl: '', apiToken: '' };
  mocks.config.mockRejectedValueOnce(new Error('503')).mockResolvedValue(config);
  render(App);
  await vi.advanceTimersByTimeAsync(2000);
  expect(mocks.init).toHaveBeenCalledWith(config, expect.objectContaining({ signal: expect.any(AbortSignal) }));
});

it('cancels configuration and stream ownership when the application is destroyed', async () => {
  mocks.config.mockReturnValue(new Promise(() => {}));
  const view = render(App); await vi.advanceTimersByTimeAsync(0);
  const signal = mocks.config.mock.calls[0][0]?.signal;
  view.unmount();
  expect(signal?.aborted).toBe(true);
  expect(mocks.stop).toHaveBeenCalledOnce();
  expect(mocks.stopAlerts).toHaveBeenCalledOnce();
  expect(vi.getTimerCount()).toBe(0);
});
