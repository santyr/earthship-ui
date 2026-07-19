// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '../../node_modules/svelte/src/index-client.js'
));

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock('../../src/routes.js', async () => {
  const { writable } = await import('svelte/store');
  return {
    currentRoute: writable('home'),
    navigate: mocks.navigate,
  };
});

vi.mock('../../src/lib/openhab/index.js', async () => {
  const { writable } = await import('svelte/store');
  return {
    items: writable({}),
    connection: writable('live'),
    num: (value) => {
      const parsed = Number.parseFloat(value);
      return Number.isFinite(parsed) ? parsed : null;
    },
  };
});

import { connection, items } from '../../src/lib/openhab/index.js';
import Header from '../../src/lib/ui/Header.svelte';

describe('Header alerts UI', () => {
  beforeEach(() => {
    mocks.navigate.mockReset();
    connection.set('live');
    items.set({
      BMS_Comms_Status: 'OK',
      BMS_DevicePresent: '1',
      BMS_SOC: '55',
      Predicted_SoC_Trough_Tomorrow: '55',
      Current_US_AQI: '42',
      Forecast_AQI: '501',
      Thermal_Advisory: 'none',
    });
  });

  afterEach(cleanup);

  it('is visually blank with an accessible status when no alerts are active', () => {
    const { container } = render(Header);

    expect(screen.getByText('No active alerts')).toHaveClass('sr-only');
    expect(container.querySelector('[data-header-alert-winner]')).toBeNull();
    expect(screen.getByRole('img', { name: 'openHAB connection: live' })).toHaveTextContent('');
  });

  it('shows a winner plus count and opens the compact full list for a global alert', async () => {
    connection.set('offline');
    items.update((value) => ({
      ...value,
      Current_US_AQI: '119',
    }));
    render(Header);

    const winner = screen.getByRole('button', { name: /openHAB offline/i });
    expect(winner).toHaveAttribute('data-header-alert-winner');
    expect(screen.getByRole('button', { name: /show 1 additional alert/i })).toHaveTextContent('+1');
    await fireEvent.click(winner);

    const list = screen.getByRole('dialog', { name: 'Active alerts' });
    expect(list).toHaveTextContent('openHAB offline');
    expect(list).toHaveTextContent('Modeled US AQI 119');
    expect(list.querySelectorAll('[data-alert-list-item]')).toHaveLength(2);
  });

  it('navigates a routed winner and never wraps the fixed-height header', async () => {
    items.update((value) => ({
      ...value,
      BMS_SOC: '12',
    }));
    const { container } = render(Header);

    await fireEvent.click(screen.getByRole('button', { name: /Battery SoC critical/i }));
    expect(mocks.navigate).toHaveBeenCalledWith('energy');
    expect(getComputedStyle(container.querySelector('.header')).height).toBe('44px');
    expect(
      getComputedStyle(container.querySelector('[data-header-alerts]')).whiteSpace,
    ).toBe('nowrap');
  });

  it('announces only newly entered offline or critical transitions assertively', async () => {
    const { container } = render(Header);
    const assertive = container.querySelector('[aria-live="assertive"]');
    expect(assertive).toHaveTextContent('');

    items.update((value) => ({ ...value, Current_US_AQI: '110' }));
    await vi.waitFor(() => {
      expect(container.querySelector('[aria-live="polite"]')).toHaveTextContent(/AQI 110/);
    });
    expect(assertive).toHaveTextContent('');

    connection.set('offline');
    await vi.waitFor(() => {
      expect(assertive).toHaveTextContent('openHAB offline');
    });

    items.update((value) => ({ ...value }));
    await vi.waitFor(() => {
      expect(assertive).toHaveTextContent('openHAB offline');
    });
  });
});
