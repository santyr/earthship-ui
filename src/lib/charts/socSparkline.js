import { atomicSocFreshness } from '../alerts/atomicSoc.js';
import { normalizeHistory } from './historyPipeline.js';

// A change-only history may be carried to now only by a fresh atomic receipt.
// Keep the receipt as a real point so the compact curve ends at its true SoC.
export function freshSocSparkline(rows, rawReceipt, nowMs, currentSoc) {
  const unchanged = { data: rows, heldUntil: null };
  const receipt = atomicSocFreshness(rawReceipt, nowMs);
  if (!receipt || currentSoc !== receipt.soc) return unchanged;
  let history;
  try {
    history = normalizeHistory(rows, { allowedUnits: ['', '%'] });
  } catch {
    return unchanged;
  }
  const last = history.at(-1);
  if (!last || last.time > receipt.recordedAt || last.time >= nowMs) return unchanged;
  if (last.time === receipt.recordedAt) {
    return last.value === receipt.soc ? { data: rows, heldUntil: nowMs } : unchanged;
  }
  return {
    data: [...rows, { time: receipt.recordedAt, state: receipt.soc }],
    heldUntil: nowMs,
  };
}
