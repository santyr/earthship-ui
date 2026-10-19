// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/svelte';
import { afterEach, expect, it, vi } from 'vitest';
vi.mock('svelte', async () => import('../../node_modules/svelte/src/index-client.js'));
vi.mock('echarts', () => ({ init: vi.fn(() => ({ dispose: vi.fn(), resize: vi.fn(), setOption: vi.fn() })) }));
import Home from '../../src/screens/Home.svelte';
import Weather from '../../src/screens/Weather.svelte';
import { items, connection } from '../../src/lib/openhab/store.js';
afterEach(() => { cleanup(); items.set({}); connection.set('connecting'); vi.useRealTimers(); });
for (const [name, Component] of [['Home', Home], ['Weather', Weather]]) {
  it(`${name} hides old forecast arrays while Google publication is withdrawn`, () => {
    vi.useFakeTimers(); vi.setSystemTime(new Date('2026-01-01T00:31:00Z'));
    items.set({
      Forecast_10Day_JSON: JSON.stringify({ version:1, generatedAt:'2026-01-01T00:30:00Z', timezone:'America/Denver', provider:'weathernext3', providerStatus:'UNAVAILABLE', providerReason:'PUBLICATION_PENDING', source:null, issueSha256:null, days:[] }),
      Forecast_Daily_JSON: JSON.stringify([{ d:'OLD DAILY', hi:111, lo:99, p:0, w:1, pv:8.5 }]),
      Forecast_Hourly_JSON: JSON.stringify([{ at:'2026-01-01T01:00:00Z', h:'6p', t:111, p:0, r:900, w:0 }]),
    }); connection.set('live');
    const { container } = render(Component);
    expect(container.textContent).not.toContain('OLD DAILY');
    expect(container.textContent).not.toContain('111');
  });
}
