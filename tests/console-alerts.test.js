import { describe, expect, it } from 'vitest';

async function loadSubject() {
  try {
    return await import('../src/lib/alerts/consoleAlerts.js');
  } catch {
    return null;
  }
}

const healthyItems = Object.freeze({
  BMS_Comms_Status: 'OK',
  BMS_DevicePresent: '1',
  BMS_SOC: '62',
  Predicted_SoC_Trough_Tomorrow: '54',
  Current_US_AQI: '42',
  Forecast_AQI: 'REFRESH',
  Thermal_Advisory: 'none',
});

describe('console alert projection', () => {
  it('exposes the typed deterministic projection API', async () => {
    const subject = await loadSubject();

    expect(subject).not.toBeNull();
    expect(subject?.projectConsoleAlerts).toBeTypeOf('function');
    expect(subject?.createAlertProjector).toBeTypeOf('function');
    expect(subject?.selectHeaderAlerts).toBeTypeOf('function');
  });

  it('uses only approved sources and fixed priority within equal severity', async () => {
    const { projectConsoleAlerts } = await loadSubject();
    const { alerts } = projectConsoleAlerts({
      connection: 'offline',
      items: {
        ...healthyItems,
        Predicted_SoC_Trough_Tomorrow: '35',
        Current_US_AQI: '119',
        Forecast_AQI: '501',
      },
      staleEssentials: [
        { name: 'outdoor-temperature', label: 'Outdoor temperature', route: 'home' },
      ],
      now: 10_000,
    });

    expect(alerts.map((alert) => alert.id)).toEqual([
      'connection-offline',
      'telemetry-stale:outdoor-temperature',
      'soc-trough',
      'aqi-unhealthy',
    ]);
    expect(alerts.find((alert) => alert.id === 'aqi-unhealthy')).toMatchObject({
      route: 'weather',
      dedupeKey: 'aqi:current-us',
      shortText: 'AQI 119',
    });
    expect(alerts.every((alert) => !alert.fullText.includes('501'))).toBe(true);
  });

  it('projects BMS communication, device, alarm, and current-SoC critical states', async () => {
    const { projectConsoleAlerts } = await loadSubject();
    const { alerts } = projectConsoleAlerts({
      connection: 'live',
      items: {
        ...healthyItems,
        BMS_Comms_Status: 'ERROR',
        BMS_DevicePresent: '0',
        BMS_SOC: '12',
      },
      batteryAlarms: [
        { id: 'cell-imbalance', text: 'Cell imbalance alarm', active: true },
      ],
      now: 20_000,
    });

    expect(alerts.map((alert) => alert.id)).toEqual([
      'battery-comms-critical',
      'battery-device-critical',
      'battery-alarm:cell-imbalance',
      'battery-soc-critical',
    ]);
    for (const alert of alerts) {
      expect(alert).toMatchObject({
        severity: 'critical',
        route: 'energy',
      });
    }
  });

  it('maps thermal codes, predicted trough thresholds, AQI, and control outcomes exactly', async () => {
    const { projectConsoleAlerts } = await loadSubject();
    const warning = projectConsoleAlerts({
      connection: 'live',
      items: {
        ...healthyItems,
        Thermal_Advisory: 'close_up_tomorrow|Close the south shades tomorrow',
        Predicted_SoC_Trough_Tomorrow: '39.6',
        Current_US_AQI: '101',
      },
      outcomes: [
        {
          controlId: 'living1',
          controlLabel: 'Living Room 1',
          phase: 'failed',
          reason: 'Provider rejected command',
          transitionAt: 90_000,
        },
        {
          controlId: 'living2',
          controlLabel: 'Living Room 2',
          phase: 'complete',
          reason: '',
          transitionAt: 90_000,
        },
      ],
      now: 100_000,
    });

    expect(warning.alerts.map((alert) => alert.id)).toEqual([
      'thermal-close',
      'soc-trough',
      'aqi-unhealthy',
      'control-outcome:living1',
    ]);
    expect(warning.alerts.find((alert) => alert.id === 'soc-trough')?.severity).toBe('warning');

    const critical = projectConsoleAlerts({
      connection: 'live',
      items: {
        ...healthyItems,
        Predicted_SoC_Trough_Tomorrow: '12',
        Thermal_Advisory: 'vent_tonight|Vent after sunset',
      },
      now: 100_000,
    });
    expect(critical.alerts.map((alert) => alert.id)).toEqual([
      'soc-trough',
      'thermal-vent',
    ]);
    expect(critical.alerts[0].severity).toBe('critical');
    expect(critical.alerts[1].severity).toBe('advisory');
  });

  it('uses the shared rounded current-AQI classification for alert thresholds', async () => {
    const { projectConsoleAlerts } = await loadSubject();

    for (const raw of ['-1', 'REFRESH', '42 AQI', '100.4']) {
      const result = projectConsoleAlerts({
        connection: 'live',
        items: { ...healthyItems, Current_US_AQI: raw },
        now: 100_000,
      });
      expect(result.alerts.find((alert) => alert.id === 'aqi-unhealthy'), raw).toBeUndefined();
    }

    const roundedIntoAlert = projectConsoleAlerts({
      connection: 'live',
      items: { ...healthyItems, Current_US_AQI: '100.5' },
      now: 100_000,
    });
    expect(roundedIntoAlert.alerts.find((alert) => alert.id === 'aqi-unhealthy')).toMatchObject({
      shortText: 'AQI 101',
      fullText: 'Modeled US AQI 101 is unhealthy.',
    });

    const beyond = projectConsoleAlerts({
      connection: 'live',
      items: { ...healthyItems, Current_US_AQI: '500.5' },
      now: 100_000,
    });
    expect(beyond.alerts.find((alert) => alert.id === 'aqi-unhealthy')).toMatchObject({
      shortText: 'AQI 501',
      fullText: 'Modeled US AQI 501 is unhealthy.',
    });
  });

  it('reports unknown non-empty thermal codes without treating NULL-like values as alerts', async () => {
    const { projectConsoleAlerts } = await loadSubject();

    const unknown = projectConsoleAlerts({
      connection: 'live',
      items: { ...healthyItems, Thermal_Advisory: 'unexpected_code|Review thermal rule' },
      now: 50_000,
    });
    expect(unknown.alerts[0]).toMatchObject({
      id: 'thermal-unknown:unexpected_code',
      severity: 'warning',
      route: 'earthship',
    });
    expect(unknown.diagnostics).toEqual([
      expect.objectContaining({ code: 'unknown-thermal-code', value: 'unexpected_code' }),
    ]);

    for (const thermal of ['', 'none', 'NULL', 'UNDEF']) {
      const result = projectConsoleAlerts({
        connection: 'live',
        items: { ...healthyItems, Thermal_Advisory: thermal },
        now: 50_000,
      });
      expect(result.alerts).toEqual([]);
    }
  });

  it('preserves activeSince across same-state freshness and resets after clear/re-entry', async () => {
    const { createAlertProjector } = await loadSubject();
    let time = 1_000;
    const projector = createAlertProjector({ now: () => time });

    const first = projector.update({
      connection: 'offline',
      items: healthyItems,
    });
    time = 2_000;
    const refreshed = projector.update({
      connection: 'offline',
      items: { ...healthyItems },
    });
    time = 3_000;
    const cleared = projector.update({
      connection: 'live',
      items: healthyItems,
    });
    time = 4_000;
    const reentered = projector.update({
      connection: 'offline',
      items: healthyItems,
    });

    expect(first.alerts[0].activeSince).toBe(1_000);
    expect(refreshed.alerts[0].activeSince).toBe(1_000);
    expect(cleared.alerts).toEqual([]);
    expect(reentered.alerts[0].activeSince).toBe(4_000);
  });

  it('deduplicates by stable key and selects winner plus stable additional count', async () => {
    const { projectConsoleAlerts, selectHeaderAlerts } = await loadSubject();
    const result = projectConsoleAlerts({
      connection: 'offline',
      items: {
        ...healthyItems,
        Current_US_AQI: '140',
      },
      batteryAlarms: [
        { id: 'alarm-a', dedupeKey: 'battery:shared', text: 'Alarm A', active: true },
        { id: 'alarm-b', dedupeKey: 'battery:shared', text: 'Alarm B', active: true },
      ],
      now: 99_000,
    });
    const selected = selectHeaderAlerts(result.alerts);

    expect(selected.winner?.id).toBe('connection-offline');
    expect(selected.additionalCount).toBe(2);
    expect(new Set(selected.ordered.map((alert) => alert.dedupeKey)).size).toBe(3);
  });

  it('expires control alerts after 15 minutes using transitionAt, not source freshness', async () => {
    const { projectConsoleAlerts } = await loadSubject();
    const transitionAt = 100_000;
    const outcome = {
      controlId: 'living1',
      controlLabel: 'Living Room 1',
      phase: 'outcome-unknown',
      reason: 'Connection dropped after send',
      transitionAt,
      sourceUpdatedAt: 999_999_999,
    };

    expect(projectConsoleAlerts({
      connection: 'live',
      items: healthyItems,
      outcomes: [outcome],
      now: transitionAt + 15 * 60_000 - 1,
    }).alerts).toHaveLength(1);
    expect(projectConsoleAlerts({
      connection: 'live',
      items: healthyItems,
      outcomes: [outcome],
      now: transitionAt + 15 * 60_000,
    }).alerts).toHaveLength(0);
  });
});
