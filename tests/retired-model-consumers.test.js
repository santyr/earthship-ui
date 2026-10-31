import { expect, it } from 'vitest';
import { projectConsoleAlerts } from '../src/lib/alerts/consoleAlerts.js';
import { recommendationPreview, isAutomatedIntent } from '../src/lib/household/recommendations.js';
import { parseHouseholdObservation } from '../src/lib/household/observation.js';
import { recommendationObservation } from './fixtures/household-recommendations.js';
import { AT } from './fixtures/household-observation.js';

const now = Date.parse('2026-09-24T18:00:00-06:00');
const morning = advisory => JSON.stringify({ version: 1, predictionDay: '2026-09-24',
  issuedAt: '2026-09-24T06:40:00-06:00', pvTodayKwh: 3.3,
  curtailmentHoursToday: 1, overnightTroughSocPct: 12, thermalAdvisory: advisory });
const preDusk = JSON.stringify({ version: 1, basis: 'atomic_soc_pre_dusk_v1', predictionDay: '2026-09-24',
  issuedAt: '2026-09-24T17:59:55-06:00', sunsetAt: '2026-09-24T19:15:00-06:00',
  morningIssuedAt: '2026-09-24T06:40:00-06:00', socRecordedAt: '2026-09-24T17:59:50-06:00',
  socStreamEpoch: '123e4567-e89b-42d3-a456-426614174000', socEvidenceSha256: 'a'.repeat(64),
  socAtIssuePct: 62, overnightDropPct: 50, overnightTroughSocPct: 12 });

it.each(['close_up_tomorrow|Close up', 'vent_tonight|Vent tonight', 'unexpected|Old advice'])(
  'does not reactivate retired prediction alerts from a plausible old receipt: %s', advisory => {
    const result = projectConsoleAlerts({ connection: 'live', now, items: {
      BMS_Comms_Status: 'OK', BMS_DevicePresent: '1',
      Forecast_Prediction_Receipt_JSON: morning(advisory),
      Forecast_PreDusk_Trough_Receipt_JSON: preDusk,
    } });
    expect(result).toEqual({ alerts: [], diagnostics: [] });
  });

it('keeps current measured battery protection when obsolete forecast receipts are present', () => {
  const result = projectConsoleAlerts({ connection: 'live', now, items: {
    BMS_Comms_Status: 'OK', BMS_DevicePresent: '1',
    Forecast_Prediction_Receipt_JSON: morning('vent_tonight|Old advice'),
    BMS_SOC_Evidence_JSON: JSON.stringify({ version: 1,
      streamEpoch: '123e4567-e89b-42d3-a456-426614174000', recordedAt: now,
      status: 'valid', reason: 'ok', observedAt: now, scaleObservedAt: now,
      validUntil: now + 120000, soc: 10 }),
  } });
  expect(result.alerts.map(row => row.id)).toEqual(['battery-soc-critical']);
});

it('does not surface legacy household proposals through normal preview routes', () => {
  const view = parseHouseholdObservation(JSON.stringify(recommendationObservation()), { nowMs: AT });
  expect(view).not.toBeNull();
  for (const scope of ['loads', 'greywater', 'night-policy', 'devices', 'feeding']) {
    expect(recommendationPreview(view, scope, AT)).toEqual({ state: 'none', rows: [], current: false, automaticActuation: false });
  }
});

it.each(['RUN_GREYWATER_CYCLE', 'SET_NIGHT_LOAD_OVERRIDE', 'SET_NIGHT_LOAD_DEVICE'])(
  'keeps owner-scheduled devices out of ML automation classification: %s', type => {
    expect(isAutomatedIntent(type)).toBe(false);
  });
