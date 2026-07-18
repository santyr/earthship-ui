import { writable } from 'svelte/store';
import { snapHistoryPeriod } from '../charts/periods.js';

// Shared click-to-chart overlay state. Any tile can call openChart(...) to
// pop the full-screen ChartModal (mounted once in App.svelte) with one or
// more overlaid history series.
//
// series: [{ name, color, label }] — `name` is the openHAB item name used
// for getHistory(); `label`/`color` are for the legend/line.
let nextOpenId = 0;

export const chartStore = writable({
  open: false,
  openId: 0,
  title: '',
  series: [],
  initialHours: 24,
  // Retain `hours` while callers migrate; ChartModal reads initialHours only.
  hours: 24,
  opener: null,
});

export function openChart({ title = '', series = [], initialHours, hours = 24 } = {}) {
  const seededHours = snapHistoryPeriod(initialHours ?? hours);
  chartStore.set({
    open: true,
    openId: ++nextOpenId,
    title,
    series,
    initialHours: seededHours,
    hours: seededHours,
    opener: typeof document !== 'undefined' && document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  });
}

export function closeChart() {
  chartStore.update((s) => ({ ...s, open: false }));
}
