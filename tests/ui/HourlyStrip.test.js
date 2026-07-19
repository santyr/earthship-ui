// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
));

const mocks = vi.hoisted(() => {
  const chart = {
    dispose: vi.fn(),
    resize: vi.fn(),
    setOption: vi.fn(),
  };
  return {
    chart,
    init: vi.fn(() => chart),
  };
});

vi.mock('../../src/lib/charts/loadEcharts.js', () => ({
  getEcharts: async () => ({ init: mocks.init }),
}));

import HourlyStrip from '../../src/lib/ui/HourlyStrip.svelte';

afterEach(() => {
  cleanup();
  mocks.init.mockClear();
  mocks.chart.setOption.mockClear();
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
});
