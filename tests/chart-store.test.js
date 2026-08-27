import { get } from 'svelte/store';
import { afterEach, describe, expect, it } from 'vitest';
import {
  chartStore,
  closeChart,
  openChart,
} from '../src/lib/ui/chartStore.js';

describe('chart store', () => {
  afterEach(closeChart);

  it('gives each modal opening a new identity and normalizes its initial period', () => {
    openChart({ title: 'First', series: [], hours: 169 });
    const first = get(chartStore);
    openChart({ title: 'Second', series: [], initialHours: 4 });
    const second = get(chartStore);

    expect(first.initialHours).toBe(168);
    expect(second.initialHours).toBe(4);
    expect(second.openId).toBe(first.openId + 1);
  });

  it('defaults existing chart callers to line presentation', () => {
    openChart({ title: 'Outdoor', series: [{ name: 'Outdoor' }] });

    expect(get(chartStore).presentation).toBe('line');
  });

  it('accepts and retains the exact candlestick presentation', () => {
    openChart({
      title: 'Bitcoin',
      presentation: 'candlestick',
      series: [{ name: 'BTC_USD_Price' }],
    });

    expect(get(chartStore).presentation).toBe('candlestick');
    closeChart();
    expect(get(chartStore).presentation).toBe('candlestick');
  });

  it('normalizes unknown presentations back to line', () => {
    openChart({ title: 'Outdoor', presentation: 'area', series: [] });

    expect(get(chartStore).presentation).toBe('line');
  });
});
