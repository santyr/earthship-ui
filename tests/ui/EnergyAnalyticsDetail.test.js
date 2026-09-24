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
  energyAnalyticsV4Fixture,
  energyAnalyticsCurrentV3Fixture,
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
  it('explains a daily-source health warning without hiding qualified coverage', async () => {
    const payload = energyAnalyticsCurrentV3Fixture();
    payload.health.analytics = 'degraded';
    payload.health.reasons = ['daily_source_quality_not_ok'];
    const parsed = parseEnergyAnalyticsResult(JSON.stringify(payload), Date.parse(payload.generatedAt) + 60_000);
    const { container } = render(EnergyAnalyticsDetail, { result: parsed });
    await fireEvent.click(screen.getByRole('button', { name: 'Open energy analytics details' }));
    expect(container.textContent).toContain('At least one daily source did not meet its quality policy.');
    expect(container.textContent).toContain('Latest battery coverage');
    expect(container.textContent).toContain('PV coverage');
  });

  it('separates current observed EFC from a dated earlier estimate and explains pending fields', async () => {
    const payload = energyAnalyticsCurrentV3Fixture();
    const parsed = parseEnergyAnalyticsResult(JSON.stringify(payload), Date.parse(payload.generatedAt) + 60_000);
    const { container } = render(EnergyAnalyticsDetail, { result: parsed });
    expect(screen.getByText('0.43 observed EFC')).toBeTruthy();
    expect(screen.getByText('since Sep 20 · through Sep 22')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Open energy analytics details' }));
    expect(screen.getByText('Earlier estimated EFC (Jul 19–Sep 19)')).toBeTruthy();
    expect(screen.getByText('9.81')).toBeTruthy();
    expect(container.textContent).toContain('1 insufficient-data day');
    expect(container.textContent).toContain('not added to observed EFC');
    expect(screen.getByText('Awaiting qualified AC day')).toBeTruthy();
    expect(screen.getByText('Discharge')).toBeTruthy();
    expect(screen.getByText("Today's PV forecast")).toBeTruthy();
    expect(screen.getByText('Qualified winter analysis is pending.')).toBeTruthy();
    expect(screen.queryByText('State of health')).toBeNull();
  });
  it('shows observed AC load with coverage and keeps DC/AC balance withheld', async () => {
    const { container } = render(EnergyAnalyticsDetail, { result: result(energyAnalyticsV4Fixture()) });
    await fireEvent.click(screen.getByRole('button', { name: 'Open energy analytics details' }));
    expect(screen.getByText('Observed AC load')).toBeTruthy();
    expect(screen.getByText('12.5 kWh')).toBeTruthy();
    expect(container.textContent).toContain('coverage 95.0%');
    expect(container.textContent).toContain('DC PV and AC load cannot be subtracted');
    expect(container.textContent).toContain('without bypass or generator supplementation');
  });
  it('shows a qualified AC day when the separate PV/battery series is empty', async () => {
    const payload = energyAnalyticsV4Fixture();
    payload.throughDate = null;
    payload.energy.latest = null;
    payload.status = 'degraded';
    for (const key of Object.keys(payload.battery)) payload.battery[key] = key === 'status' ? 'unavailable' : null;
    Object.assign(payload.lifecycle, { periodEfc: null, chargeKwh: null, dischargeKwh: null });
    Object.assign(payload.accounting, { daysPresent: 0, missingDays: 2, latestRevision: null,
      latestBatteryCoverage: null, latestPvCoverage: null });
    render(EnergyAnalyticsDetail, { result: result(payload) });
    expect(screen.getByText('12.5 kWh AC')).toBeTruthy();
    expect(screen.getByText('AC through Aug 19')).toBeTruthy();
    expect(screen.queryByText('No daily data')).toBeNull();
  });
  it('exposes a validated empty qualified series without inventing totals', async () => {
    const payload=energyAnalyticsV3Fixture();
    payload.status='unavailable';payload.throughDate=null;payload.energy.latest=null;
    for (const key of Object.keys(payload.battery)) payload.battery[key]=key==='status' ? 'unavailable' : null;
    Object.assign(payload.lifecycle,{periodEfc:null,chargeKwh:null,dischargeKwh:null});
    Object.assign(payload.accounting,{daysPresent:0,missingDays:2,latestRevision:null,
      latestBatteryCoverage:null,latestPvCoverage:null});
    render(EnergyAnalyticsDetail,{result:result(payload)});
    expect(screen.getByText('No daily data')).toBeTruthy();
    expect(screen.getByText('WAITING')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button',{name:'Open energy analytics details'}));
    expect(screen.getByText(/No completed daily records/)).toBeTruthy();
    expect(screen.queryByText('0.00 observed EFC')).toBeNull();
  });
  it('labels qualified window EFC, coverage and missing days without lifetime claims', async () => {
    const { container } = render(EnergyAnalyticsDetail, { result: result(energyAnalyticsV3Fixture()) });
    expect(screen.getByText('0.33 observed EFC')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: 'Open energy analytics details' }));
    expect(screen.getByText('Window observed EFC')).toBeTruthy();
    expect(screen.getByText('Daily observed EFC')).toBeTruthy();
    expect(container.textContent).toContain('1 days present; 1 missing');
    expect(container.textContent).toContain('80.0%');
    expect(container.textContent).toContain('Legacy estimates are excluded');
    expect(container.textContent).toContain('Load balance is unavailable pending qualified inverter-output receipts');
    expect(container.textContent).toContain('only while all loads remain inverter-served');
    expect(screen.queryByText('Ending estimated EFC')).toBeNull();
  });
  it('labels qualified high-SoC exposure as observed window hours', async () => {
    const payload = energyAnalyticsCurrentV3Fixture();
    payload.lifecycle.highSocHoursAbove90 = 49.6;
    payload.lifecycle.highSocHoursAbove95 = 32.5;
    const { container } = render(EnergyAnalyticsDetail, {
      result: parseEnergyAnalyticsResult(JSON.stringify(payload), Date.parse(payload.generatedAt) + 60_000),
    });
    await fireEvent.click(screen.getByRole('button', { name: 'Open energy analytics details' }));
    expect(screen.getByText('Observed above 90% SoC')).toBeTruthy();
    expect(screen.getByText('49.6 h')).toBeTruthy();
    expect(screen.getByText('Observed above 95% SoC')).toBeTruthy();
    expect(screen.getByText('32.5 h')).toBeTruthy();
    expect(container.textContent).toContain('not a lifetime total');
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
