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
});
