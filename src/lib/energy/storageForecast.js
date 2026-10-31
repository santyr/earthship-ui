import { parseCalibratedEnergy } from '../household/calibratedEnergy.js';
import { parseEnergyObservation } from '../household/energyObservation.js';

// Preserve the original issue, targets and expiry. Forecast values never enter
// measured OpenHAB history or inherit the current battery reading.
export function storageForecastPresentation(raw, { fallbackRaw = null, nowMs = Date.now() } = {}) {
  const calibrated = parseCalibratedEnergy(raw, { nowMs });
  const qualified = calibrated && !calibrated.expired
    && calibrated.profiled_storage_status === 'conditional_nominal_simulation';
  const fallback = qualified ? null : parseEnergyObservation(fallbackRaw, { nowMs });
  const value = qualified ? calibrated : fallback && !fallback.expired && fallback.storage_status === 'conditional' ? fallback : null;
  if (!value) return null;
  return {
    source: qualified ? 'learned_load_calibrated_pv' : 'constant_load_raw_pv',
    basis: qualified ? 'Learned household load · calibrated PV · nominal battery capacity' : 'Current-load assumption · raw PV · nominal battery capacity',
    issuedAtMs: Date.parse(value.issued_at),
    validUntilMs: Date.parse(value.valid_until),
    points: [
      [Date.parse(value.issued_at), value.initial_soc_pct],
      ...value.trajectory.map(p => [Date.parse(p.at), qualified ? p.calibrated_soc_pct : p.nominal_soc_pct]),
    ],
  };
}

// Use the earliest occurrence of the lowest upcoming value, excluding elapsed
// targets and the issue-time starting SoC.
export function predictedLowSoc(forecast, nowMs = Date.now()) {
  if (!forecast || forecast.validUntilMs <= nowMs) return null;
  return forecast.points.reduce((low, point) => {
    if (point[0] <= nowMs) return low;
    return !low || point[1] < low[1] ? point : low;
  }, null);
}
