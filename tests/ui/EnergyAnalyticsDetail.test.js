// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
));

import EnergyAnalyticsDetail from '../../src/lib/ui/EnergyAnalyticsDetail.svelte';
import { parseEnergyAnalyticsResult } from '../../src/lib/energy/analyticsResult.js';
import {
  GENERATED_AT_MS,
  energyAnalyticsFixture,
  energyAnalyticsV3Fixture,
} from '../fixtures/energyAnalytics.js';


function result(payload = energyAnalyticsFixture()) {
  return parseEnergyAnalyticsResult(JSON.stringify(payload), GENERATED_AT_MS + 60_000);
}

afterEach(() => {
  cleanup();
  document.body.innerHTML = '';
  document.body.style.overflow = '';
});

describe('EnergyAnalyticsDetail observational presentation', () => {
  it('labels qualified window EFC, coverage and missing days without lifetime claims', async () => {
    const { container } = render(EnergyAnalyticsDetail, { result: result(energyAnalyticsV3Fixture()) });
    expect(screen.getByText('0.33 observed EFC')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Open energy analytics details' }));
    expect(screen.getByText('Window observed EFC')).toBeTruthy();
    expect(screen.getByText('Daily observed EFC')).toBeTruthy();
    expect(container.textContent).toContain('1 days present; 1 missing');
    expect(container.textContent).toContain('80.0%');
    expect(container.textContent).toContain('Legacy estimates are excluded');
    expect(screen.queryByText('Ending estimated EFC')).toBeNull();
  });
  it('shows compact evidence and opens all six labeled detail sections', async () => {
    const { container } = render(EnergyAnalyticsDetail, { result: result() });

    expect(screen.getByText('Analytics')).toBeTruthy();
    expect(screen.getByText('4.36 EFC')).toBeTruthy();
    expect(screen.getByText('through Aug 19')).toBeTruthy();
    const open = screen.getByRole('button', { name: 'Open energy analytics details' });
    await fireEvent.click(open);

    expect(screen.getByRole('dialog', { name: 'Energy analytics details' })).toBeTruthy();
    for (const heading of ['Battery', 'Energy', 'Winter', 'Lifecycle', 'Forecast', 'Health']) {
      expect(screen.getByRole('heading', { name: heading })).toBeTruthy();
    }
    expect(screen.getByText('8.0 kWh')).toBeTruthy();
    expect(screen.getByText('7.2 kWh')).toBeTruthy();
    expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0);
    expect(container.textContent.toLowerCase()).not.toMatch(/turn on|turn off|run now|authorize/);
    expect(container.querySelector('form, input, select, textarea')).toBeNull();
  });

  it('focuses close, closes on Escape, restores opener and body overflow', async () => {
    document.body.style.overflow = 'clip';
    render(EnergyAnalyticsDetail, { result: result() });
    const open = screen.getByRole('button', { name: 'Open energy analytics details' });
    open.focus();
    await fireEvent.click(open);
    const dialog = screen.getByRole('dialog');
    const close = screen.getByRole('button', { name: 'Close energy analytics details' });
    await waitFor(() => expect(document.activeElement).toBe(close));
    expect(document.body.style.overflow).toBe('hidden');
    await fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(document.activeElement).toBe(open);
    expect(document.body.style.overflow).toBe('clip');
  });

  it('renders an unavailable compact state without opening fabricated details', () => {
    render(EnergyAnalyticsDetail, {
      result: parseEnergyAnalyticsResult('UNDEF', GENERATED_AT_MS),
    });
    expect(screen.getByText('Analytics unavailable')).toBeTruthy();
    expect(screen.queryByRole('button')).toBeNull();
  });
});
