// Item-staleness wiring: alertContext.staleEssentials was previously written
// by nothing, so the fully-tested telemetry-stale projector could never fire
// and a dead sensor froze silently. These tests cover the pure staleness
// computation and the store-level monitor that feeds alertContext.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { get } from 'svelte/store';
import {
  ESSENTIAL_ITEMS,
  ESSENTIAL_STALE_THRESHOLD_MS,
  STALENESS_CHECK_INTERVAL_MS,
  computeStaleEssentials,
} from '../src/lib/alerts/staleness.js';
import { applySnapshot, applyState, items } from '../src/lib/openhab/store.js';
import {
  alertContext,
  consoleAlerts,
  startStalenessMonitor,
} from '../src/lib/alerts/alertStore.js';

const OUTDOOR = 'AmbientWeatherWS2902A_WeatherDataWs2902a_Temperature';
const INDOOR = 'AmbientWeatherWS2902A_IndoorSensor_Temperature';

describe('computeStaleEssentials (pure)', () => {
  it('exposes a small curated essential-item list with defensible thresholds', () => {
    const names = ESSENTIAL_ITEMS.map((item) => item.name);
    expect(names).toContain(OUTDOOR);
    expect(names).toContain('BMS_SOC');
    expect(ESSENTIAL_STALE_THRESHOLD_MS).toBe(15 * 60_000);
    for (const item of ESSENTIAL_ITEMS) {
      expect(item.label).toBeTruthy();
      expect(item.route).toBeTruthy();
    }
  });

  it('returns no entries when every essential updated within its threshold', () => {
    const now = 1_000_000_000;
    const seen = Object.fromEntries(ESSENTIAL_ITEMS.map((item) => [item.name, now - 60_000]));
    expect(computeStaleEssentials(seen, now)).toEqual([]);
  });

  it('flags an essential item stale in the projector element shape', () => {
    const now = 1_000_000_000;
    const lastSeen = now - ESSENTIAL_STALE_THRESHOLD_MS - 1;
    const stale = computeStaleEssentials({ [OUTDOOR]: lastSeen }, now);

    expect(stale).toHaveLength(1);
    expect(stale[0]).toMatchObject({
      name: OUTDOOR,
      label: 'Outdoor temperature',
      route: 'home',
      severity: 'warning',
      transitionAt: lastSeen + ESSENTIAL_STALE_THRESHOLD_MS,
    });
    expect(stale[0].fullText).toContain('Outdoor temperature');
  });

  it('does not flag items that were never seen (no snapshot yet)', () => {
    expect(computeStaleEssentials({}, 1_000_000_000)).toEqual([]);
  });

  it('honors the longer BMS_SOC threshold so float plateaus are not false alarms', () => {
    const now = 1_000_000_000;
    const seen = { BMS_SOC: now - 20 * 60_000 };
    expect(computeStaleEssentials(seen, now)).toEqual([]);

    const longAgo = { BMS_SOC: now - 61 * 60_000 };
    const stale = computeStaleEssentials(longAgo, now);
    expect(stale.map((entry) => entry.name)).toEqual(['BMS_SOC']);
    expect(stale[0].route).toBe('energy');
  });
});

describe('staleness monitor (store-level)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    items.set({});
    alertContext.set({ staleEssentials: [], batteryAlarms: [] });
  });

  afterEach(() => {
    items.set({});
    alertContext.set({ staleEssentials: [], batteryAlarms: [] });
    vi.useRealTimers();
  });

  it('flags, projects, clears, and stops on teardown', () => {
    applySnapshot([
      { name: OUTDOOR, state: '70.1' },
      { name: INDOOR, state: '69.0' },
      { name: 'BMS_SOC', state: '62' },
    ]);
    const stop = startStalenessMonitor();

    expect(get(alertContext).staleEssentials).toEqual([]);

    // 16 minutes of silence: 15-minute essentials go stale, BMS_SOC (60 min)
    // does not.
    vi.advanceTimersByTime(16 * 60_000);
    let staleNames = get(alertContext).staleEssentials.map((entry) => entry.name);
    expect(staleNames).toContain(OUTDOOR);
    expect(staleNames).toContain(INDOOR);
    expect(staleNames).not.toContain('BMS_SOC');

    // The wired context reaches the console-alert projection.
    const projected = get(consoleAlerts);
    expect(projected.ordered.some((alert) => alert.id === `telemetry-stale:${OUTDOOR}`)).toBe(true);

    // A fresh statechanged clears the alert on the next periodic check.
    applyState(OUTDOOR, '70.4');
    applyState(INDOOR, '69.2');
    vi.advanceTimersByTime(STALENESS_CHECK_INTERVAL_MS);
    staleNames = get(alertContext).staleEssentials.map((entry) => entry.name);
    expect(staleNames).not.toContain(OUTDOOR);
    expect(staleNames).not.toContain(INDOOR);

    // Past the 60-minute threshold BMS_SOC goes stale too.
    vi.advanceTimersByTime(60 * 60_000);
    staleNames = get(alertContext).staleEssentials.map((entry) => entry.name);
    expect(staleNames).toContain('BMS_SOC');

    // Teardown: the interval stops writing.
    stop();
    applyState('BMS_SOC', '63');
    vi.advanceTimersByTime(10 * STALENESS_CHECK_INTERVAL_MS);
    expect(get(alertContext).staleEssentials.map((entry) => entry.name)).toContain('BMS_SOC');
  });
});
