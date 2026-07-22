// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
));

const mocks = vi.hoisted(() => {
  const charts = [];
  const init = vi.fn((el) => {
    const chart = {
      el,
      disposed: false,
      dispose: vi.fn(function dispose() { this.disposed = true; }),
      resize: vi.fn(),
      setOption: vi.fn(),
      getDom: () => el,
    };
    charts.push(chart);
    return chart;
  });
  return {
    charts,
    get chart() { return charts[charts.length - 1]; },
    init,
  };
});

vi.mock('../../src/lib/charts/loadEcharts.js', () => ({
  getEcharts: async () => ({ init: mocks.init }),
}));

import HourlyStrip from '../../src/lib/ui/HourlyStrip.svelte';

afterEach(() => {
  cleanup();
  mocks.init.mockClear();
  mocks.charts.length = 0;
});

const baseHour = { h: '9 AM', t: 70, p: 20, r: 100, w: 1 };

describe('HourlyStrip', () => {
  it('renders the rain amount for an hour when its precip amount is positive', async () => {
    const { container } = render(HourlyStrip, {
      props: { hours: [{ ...baseHour, a: 0.24 }] },
    });
    await waitFor(() => expect(mocks.init).toHaveBeenCalled());

    const amount = screen.getByTestId('hour-rain-amount');
    expect(amount.textContent).toBe('0.24″');
    expect(amount.getAttribute('style')).toContain('rgb(59, 130, 246)');
    expect(container.querySelectorAll('[data-testid="hour-rain-amount"]')).toHaveLength(1);
  });

  it('renders no rain amount when the hourly precip amount is zero, null, or missing', async () => {
    const { container } = render(HourlyStrip, {
      props: {
        hours: [
          { ...baseHour, a: 0 },
          { ...baseHour, a: null },
          { ...baseHour },
        ],
      },
    });
    await waitFor(() => expect(mocks.init).toHaveBeenCalled());

    expect(container.querySelectorAll('[data-testid="hour-rain-amount"]')).toHaveLength(0);
    expect(container.textContent).not.toContain('″');
  });

  it('disposes the chart when hours empty and re-initializes when they refill', async () => {
    const { container, rerender } = render(HourlyStrip, {
      props: { hours: [baseHour] },
    });
    await waitFor(() => expect(mocks.init).toHaveBeenCalledTimes(1));
    const firstChart = mocks.charts[0];

    // Transient NULL forecast: hours empty, the chart div unmounts. The
    // detached ECharts instance must be disposed, not leaked.
    await rerender({ hours: [] });
    await waitFor(() => expect(firstChart.dispose).toHaveBeenCalled());
    expect(container.querySelector('.hs-chart')).toBeNull();

    // Forecast returns: a fresh instance must be created on the NEW element —
    // painting the old detached node would leave the panel blank forever.
    await rerender({ hours: [baseHour, { ...baseHour, h: '10 AM' }] });
    await waitFor(() => expect(mocks.init).toHaveBeenCalledTimes(2));
    const el = container.querySelector('.hs-chart');
    expect(el).not.toBeNull();
    expect(mocks.init).toHaveBeenLastCalledWith(el, null, { renderer: 'svg' });
    await waitFor(() => expect(mocks.charts[1].setOption).toHaveBeenCalled());
  });

  it('escapes hostile hour labels in the tooltip formatter (no HTML injection)', async () => {
    render(HourlyStrip, {
      props: {
        hours: [{ ...baseHour, h: '<img src=x onerror=window.__pwned=1>' }],
      },
    });
    await waitFor(() => expect(mocks.chart.setOption).toHaveBeenCalled());

    const option = mocks.chart.setOption.mock.calls.at(-1)[0];
    const html = option.tooltip.formatter([{ dataIndex: 0 }]);

    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;img');
    expect(html).toContain('temp: 70°');
  });
});
