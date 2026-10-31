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
    itemUpdateEvidence: writable({}),
    clientReady: writable(false),
    connection: writable('live'),
    num: (value) => {
      const parsed = Number.parseFloat(value);
      return Number.isFinite(parsed) ? parsed : null;
    },
  };
});

import { connection, items } from '../../src/lib/openhab/index.js';
import Header from '../../src/lib/ui/Header.svelte';
import Clock from '../../src/lib/ui/Clock.svelte';
import { currentRoute } from '../../src/routes.js';
import { tick } from 'svelte';

function thermalWarningReceipt(now = Date.now()) {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver',
    year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(now);
  const date = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return JSON.stringify({ version: 1,
    predictionDay: `${date.year}-${date.month}-${date.day}`,
    issuedAt: new Date(now).toISOString(), pvTodayKwh: 3.3, curtailmentHoursToday: 0,
    overnightTroughSocPct: 55,
    thermalAdvisory: 'close_up_tomorrow|Close up for thermal storage' });
}

describe('Header alerts UI', () => {
  beforeEach(() => {
    mocks.navigate.mockReset();
    currentRoute.set('home');
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
      BMS_DevicePresent: '0',
    }));
    render(Header);

    const winner = screen.getByRole('button', { name: /openHAB offline/i });
    expect(winner).toHaveAttribute('data-header-alert-winner');
    expect(screen.getByRole('button', { name: /show 1 additional alert/i })).toHaveTextContent('+1');
    await fireEvent.click(winner);

    const list = screen.getByRole('dialog', { name: 'Active alerts' });
    expect(list).toHaveTextContent('openHAB offline');
    expect(list).toHaveTextContent('The battery-management device is not present.');
    expect(list.querySelectorAll('[data-alert-list-item]')).toHaveLength(2);
  });

  it('navigates a routed winner and never wraps the fixed-height header', async () => {
    const now = Date.now();
    items.update((value) => ({
      ...value,
      BMS_SOC: '12',
      BMS_SOC_Evidence_JSON: JSON.stringify({
        version: 1, streamEpoch: '123e4567-e89b-42d3-a456-426614174000',
        recordedAt: now, status: 'valid', reason: 'ok', observedAt: now,
        scaleObservedAt: now, validUntil: now + 120_000, soc: 12,
      }),
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

    items.update((value) => ({ ...value, Forecast_Prediction_Receipt_JSON: thermalWarningReceipt() }));
    await vi.waitFor(() => {
      expect(container.querySelector('[aria-live="polite"]')).toHaveTextContent('No active alerts');
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
  it('keeps only the date in Home header and restores compact time on another route', async () => {
    const { container } = render(Header);
    const date = new Date().toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
    expect(container.querySelector('.clock')).toHaveTextContent(date);
    expect(container.querySelector('.time')).toBeNull();

    currentRoute.set('energy');
    await tick();
    expect(container.querySelector('.time')).toHaveTextContent(/\d{1,2}:\d{2} [AP]M/);
    expect(container.querySelector('.date')).toHaveTextContent(date);

    currentRoute.set('home');
    await tick();
    expect(container.querySelector('.time')).toBeNull();
    expect(container.querySelectorAll('.date')).toHaveLength(1);
  });

  it('ticks conditional Clock content across midnight and clears its interval on teardown', async () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date('2026-10-26T23:59:59-06:00'));
      const baseline = vi.getTimerCount();
      const view = render(Clock, { showTime: false });
      expect(view.container.querySelector('.time')).toBeNull();
      const oldDate = view.container.textContent;
      await vi.advanceTimersByTimeAsync(1000);
      await tick();
      expect(view.container.textContent).not.toBe(oldDate);
      await view.rerender({ showTime: true, showDate: false });
      expect(view.container.querySelector('.date')).toBeNull();
      expect(view.container.querySelector('.time')).toHaveTextContent('12:00 AM');
      await vi.advanceTimersByTimeAsync(60_000);
      await tick();
      expect(view.container.querySelector('.time')).toHaveTextContent('12:01 AM');
      expect(vi.getTimerCount()).toBe(baseline + 1);
      view.unmount();
      expect(vi.getTimerCount()).toBe(baseline);
    } finally {
      cleanup();
      vi.useRealTimers();
    }
  });

});
