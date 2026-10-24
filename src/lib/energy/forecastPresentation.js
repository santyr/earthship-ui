import { parseEnergyObservation } from '../household/energyObservation.js';
import { HOUSEHOLD_TIMEZONE } from '../site.js';
/** Existing sealed read-only potential/capture view, with expiry preserved. */
export function energyForecastPresentation(raw, { nowMs = Date.now() } = {}) {
  const view = parseEnergyObservation(raw, { nowMs });
  if (!view || view.expired || view.status !== 'available') return null;
  const periods = [];
  const formatter = new Intl.DateTimeFormat('en-US', {timeZone:HOUSEHOLD_TIMEZONE,hour:'numeric',minute:'2-digit'});
  for (let i = 0; i < view.trajectory.length; i += 3) {
    const rows = view.trajectory.slice(i, i + 3);
    const start = Date.parse(rows[0].at) - 3600000;
    periods.push({ at: new Date(start).toISOString(), label: formatter.format(start).replace(' ', '').toLowerCase(),
      pv: rows.reduce((sum, row) => sum + row.potential_pv_kwh, 0) });
  }
  const max = Math.max(1, ...periods.map(p => p.pv));
  // Potential minus modeled capture is energy, not a duration. Missing storage
  // inputs must stay unknown rather than implying all potential is curtailed.
  const curtailment24hKwh = view.storage_status === 'conditional'
    ? Math.max(0, view.potential_pv_24h_kwh - view.captured_pv_24h_kwh) : null;
  const curtailmentPct = curtailment24hKwh === null ? null
    : view.potential_pv_24h_kwh > 0 ? curtailment24hKwh / view.potential_pv_24h_kwh * 100 : 0;
  return { issuedAt: view.issued_at, potentialRemainingTodayKwh: view.potential_pv_remaining_today_kwh,
    potential24hKwh: view.potential_pv_24h_kwh, captured24hKwh: view.captured_pv_24h_kwh,
    curtailment24hKwh, curtailmentPct,
    periods: periods.map(p => ({ ...p, pct: p.pv > 0 ? Math.max(2, p.pv / max * 100) : 0 })) };
}
