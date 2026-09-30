// @vitest-environment jsdom
import { cleanup, fireEvent, render } from '@testing-library/svelte';
import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `../../node_modules/svelte/src/index-client.js`
));

import Earthship from '../../src/screens/Earthship.svelte';
import { items, connection } from '../../src/lib/openhab/store.js';
import { chartStore, closeChart } from '../../src/lib/ui/chartStore.js';
import validShadow from '../fixtures/thermal-shadow-v1-available.json';
import { localDateAt } from '../../src/lib/weather/forecastDetail.js';

beforeEach(() => {
  items.set({
    AmbientWeatherWS2902A_WH31E_193_Temperature: '66.8',
    AmbientWeatherWS2902A_IndoorSensor_Temperature: '69.1',
    Shelly_HT1_Indoor_Temperature: '71.5',
    AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature: '68.2',
  });
});

afterEach(() => {
  cleanup();
  closeChart();
  items.set({});
  vi.useRealTimers();
});

function setItems(extra = {}) {
  items.update((current) => ({ ...current, ...extra }));
}

describe('Earthship four-zone thermal contract', () => {
  it('accepts fresh receipts between minute ticks without a disappearing reading', async () => {
    vi.useFakeTimers();
    const now = Date.parse('2026-09-30T23:00:00Z');
    vi.setSystemTime(now);
    const previousConnection = get(connection);
    connection.set('live');
    try {
      const { container } = render(Earthship);
      vi.advanceTimersByTime(30_000);
      const epoch = '831b737c-ab25-48d7-9a90-889746e56410';
      setItems({ Weather_Temperature_Evidence_JSON: JSON.stringify({ version: 1, streamEpoch: epoch,
        records: { bedroom: { version: 1, streamEpoch: epoch, model: 'AmbientWeather-WH31E', sensorId: 223,
          field: 'tempinf', status: 'valid', reason: 'accepted', temperatureF: 71.4,
          receivedAt: new Date(now + 30_000).toISOString(), recordedAt: new Date(now + 30_000).toISOString(),
          validUntil: new Date(now + 150_000).toISOString() } } }) });
      await vi.advanceTimersByTimeAsync(0);
      expect(container.querySelector('.bedroom-reading').textContent).toBe('Bedroom 71.4°F');
    } finally { connection.set(previousConnection); }
  });
  it('opens the dedicated Bedroom chart without borrowing a Hallway forecast', async () => {
    const { container } = render(Earthship);
    await fireEvent.click(container.querySelector('.bedroom-reading'));
    expect(get(chartStore)).toMatchObject({ title: 'Bedroom Temperature (24h)',
      series: [{ name: 'Bedroom_Temperature', label: 'Bedroom' }], hours: 24 });
  });
  it('preserves physical loop order and adds independent Bedroom history', async () => {
    const { container } = render(Earthship);

    expect([...container.querySelectorAll('.zone-label')].map((node) => node.textContent))
      .toEqual(['North Mass', 'Room Air', 'South Wall', 'Outdoor']);
    expect([...container.querySelectorAll('.humidity-label')].map((node) => node.textContent))
      .toEqual(['North Mass', 'Room Air', 'South Wall']);

    await fireEvent.click(container.querySelector('.zone-group'));
    const chart = get(chartStore);
    expect(chart.series.map(({ label }) => label))
      .toEqual(['North Mass', 'Room Air', 'South Wall', 'Outdoor', 'Bedroom']);
    expect(chart.series.map(({ name }) => name)).toEqual([
      'AmbientWeatherWS2902A_WH31E_193_Temperature',
      'AmbientWeatherWS2902A_IndoorSensor_Temperature',
      'Shelly_HT1_Indoor_Temperature',
      'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature',
      'Bedroom_Temperature',
    ]);
  });
});

describe('Earthship thermal model integration', () => {
  it('withholds yesterday\'s advisory and tomorrow temperatures without a current receipt', () => {
    setItems({ Thermal_Advisory: 'close_up_tomorrow|Stale advice',
      Forecast_Tomorrow_High: '81', Forecast_Tomorrow_Low: '54' });
    const { container } = render(Earthship);
    expect(container.querySelector('.advisory-text')?.textContent).toBe('Forecast unavailable');
    expect(container.querySelector('.advisory-footer')?.textContent).toBe('Tomorrow forecast unavailable');
  });

  it('adds the shadow model beside existing displays without changing advisory or zone order', () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse(validShadow.generatedAt) + 10 * 60_000);
    setItems({
      Thermal_Model_JSON: JSON.stringify(validShadow),
      Thermal_Advisory: 'vent|Existing thermal advisory remains authoritative',
      Forecast_Prediction_Receipt_JSON: JSON.stringify({
        version: 1,
        predictionDay: localDateAt(Date.parse(validShadow.generatedAt) + 10 * 60_000,
          'America/Denver'),
        issuedAt: validShadow.generatedAt, pvTodayKwh: 3.3,
        curtailmentHoursToday: 0, overnightTroughSocPct: 59,
        thermalAdvisory: 'vent|Existing thermal advisory remains authoritative',
      }),
      Forecast_Tomorrow_High: '81',
      Forecast_Tomorrow_Low: '54',
    });

    const { container, getByText } = render(Earthship);

    expect(container.querySelector('.thermal-model-cell')).not.toBeNull();
    expect(getByText('SHADOW')).toBeTruthy();
    expect(getByText('Existing thermal advisory remains authoritative')).toBeTruthy();
    expect([...container.querySelectorAll('.zone-label')].map((node) => node.textContent))
      .toEqual(['North Mass', 'Room Air', 'South Wall', 'Outdoor']);
    expect(container.querySelector('.thermal-model-cell button')).toBeNull();
  });
});

describe('Earthship greywater honesty', () => {
  it('shows East independently in service and West as planned', () => {
    setItems({ SouthOutlet_Outlet2_Switch: 'OFF', East_Bed_Socket_Outlet_2_Power: 'ON' });
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-state').textContent).toBe('Idle');
    expect(container.querySelector('.gw-east-state').textContent).toBe('Running');
    expect(container.querySelector('.gw-caption').textContent).toBe('South + East in service · West planter planned');
  });

  it('does not treat unknown East status as idle', () => {
    setItems({ SouthOutlet_Outlet2_Switch: 'OFF', East_Bed_Socket_Outlet_2_Power: 'UNDEF' });
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-east-state').textContent).toBe('Unavailable');
  });
  it('renders Unavailable when the switch state is missing, matching Home semantics', () => {
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-state').textContent).toBe('Unavailable');
  });

  it.each([
    ['NULL', 'Unavailable'],
    ['UNDEF', 'Unavailable'],
    ['OFF', 'Idle'],
    ['ON', 'Running'],
  ])('renders switch state %s as %s', (state, label) => {
    setItems({ SouthOutlet_Outlet2_Switch: state });
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-state').textContent).toBe(label);
  });

  it('lights the running dot only for ON', () => {
    setItems({ SouthOutlet_Outlet2_Switch: 'ON' });
    const running = render(Earthship);
    expect(running.container.querySelector('.gw-dot.active')).not.toBeNull();
    cleanup();

    setItems({ SouthOutlet_Outlet2_Switch: 'NULL' });
    const unavailable = render(Earthship);
    expect(unavailable.container.querySelector('.gw-dot.active')).toBeNull();
  });

  it('carries fallback minutes into hours without a "1h 60m" boundary', () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse('2026-09-20T18:00:00Z'));
    setItems({ SouthOutlet_Outlet2_Switch: 'OFF', East_Bed_Socket_Outlet_2_Power: 'OFF',
      SouthOutlet_AutoStatus: 'reason=waiting_for_solar,fallbackInMin=119.6,scheduleVersion=1,evaluatedAt=2026-09-20T18:00:00Z,scheduling=blocked' });
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-reason').textContent)
      .toBe('waiting for solar · fallback in 2h 0m');
  });

  it('shows the controller-authored next pump and time without promising a start', () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse('2026-09-20T18:00:00Z'));
    setItems({ SouthOutlet_Outlet2_Switch: 'OFF', East_Bed_Socket_Outlet_2_Power: 'OFF',
      SouthOutlet_AutoStatus: 'reason=idle,scheduleVersion=1,evaluatedAt=2026-09-20T18:00:00Z,scheduling=conditional,nextPump=east,nextEligibleAt=2026-09-20T19:24:00Z' });
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-next').textContent).toBe('Earliest East · 1:24 PM');
    expect(container.querySelector('.gw-status').title).toContain('conditions must still permit');
  });

  it('withholds the next-pump estimate and old reason when controller status is stale', () => {
    vi.useFakeTimers();
    vi.setSystemTime(Date.parse('2026-09-20T18:05:00Z'));
    setItems({ SouthOutlet_Outlet2_Switch: 'OFF', East_Bed_Socket_Outlet_2_Power: 'OFF',
      SouthOutlet_AutoStatus: 'reason=idle,scheduleVersion=1,evaluatedAt=2026-09-20T18:00:00Z,scheduling=conditional,nextPump=east,nextEligibleAt=2026-09-20T19:24:00Z' });
    const { container } = render(Earthship);
    expect(container.querySelector('.gw-next').textContent).toBe('Next unavailable');
    expect(container.querySelector('.gw-reason')).toBeNull();
  });
});

describe('Earthship last-run wall clock', () => {
  it('advances the "last run" label on a quiet stream via the minute tick', async () => {
    vi.useFakeTimers();
    const { tick } = await import('../../node_modules/svelte/src/index-client.js');
    setItems({
      SouthOutlet_LastAutoRun: new Date(Date.now() - 2 * 60_000).toISOString(),
    });
    const { container } = render(Earthship);
    const footer = () => container.querySelector('.gw-footer span').textContent;
    expect(footer()).toBe('last run 2 m ago');

    // No item changes at all — only wall-clock time passes.
    vi.advanceTimersByTime(10 * 60_000);
    await tick();
    expect(footer()).toBe('last run 12 m ago');
  });
});
