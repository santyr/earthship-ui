import { describe, expect, it, vi } from 'vitest';
import { loadHistorySeries } from '../src/lib/charts/historyRequest.js';

const NOW = Date.UTC(2026, 6, 18, 12);
const HOUR = 60 * 60 * 1_000;

describe('history request generation', () => {
  it('uses exact past-only history and future-only forecast bounds', async () => {
    const getHistory = vi.fn().mockResolvedValue([{ time: NOW, state: '1' }]);
    await loadHistorySeries({
      client: { getHistory },
      series: [
        { name: 'BMS_SOC' },
        { name: 'Forecast_Temp' },
      ],
      hours: 24,
      nowMs: NOW,
    });

    expect(getHistory.mock.calls[0][1]).toMatchObject({
      starttime: new Date(NOW - 24 * HOUR).toISOString(),
      endtime: new Date(NOW).toISOString(),
    });
    expect(getHistory.mock.calls[1][1]).toMatchObject({
      starttime: new Date(NOW).toISOString(),
      endtime: new Date(NOW + 18 * HOUR).toISOString(),
    });
  });

  it('distinguishes partial failure, full failure, and successful empty data', async () => {
    const partial = await loadHistorySeries({
      client: {
        getHistory: vi.fn()
          .mockResolvedValueOnce([{ time: NOW, state: '1' }])
          .mockRejectedValueOnce(new Error('offline')),
      },
      series: [{ name: 'BMS_SOC' }, { name: 'MPPT60_PV_Power' }],
      hours: 24,
      nowMs: NOW,
    });
    expect(partial.state).toBe('partial-error');
    expect(partial.pointsPerSeries).toEqual([[{ time: NOW, state: '1' }], []]);
    expect(partial.errors).toHaveLength(1);

    const failed = await loadHistorySeries({
      client: { getHistory: vi.fn().mockRejectedValue(new Error('offline')) },
      series: [{ name: 'BMS_SOC' }],
      hours: 24,
      nowMs: NOW,
    });
    expect(failed.state).toBe('error');

    const empty = await loadHistorySeries({
      client: { getHistory: vi.fn().mockResolvedValue([]) },
      series: [{ name: 'BMS_SOC' }],
      hours: 24,
      nowMs: NOW,
    });
    expect(empty.state).toBe('empty');
  });
});
