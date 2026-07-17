import { writable } from 'svelte/store';

// Shared click-to-chart overlay state. Any tile can call openChart(...) to
// pop the full-screen ChartModal (mounted once in App.svelte) with one or
// more overlaid history series.
//
// series: [{ name, color, label }] — `name` is the openHAB item name used
// for getHistory(); `label`/`color` are for the legend/line.
export const chartStore = writable({ open: false, title: '', series: [], hours: 24 });

export function openChart({ title = '', series = [], hours = 24 } = {}) {
  chartStore.set({ open: true, title, series, hours });
}

export function closeChart() {
  chartStore.update((s) => ({ ...s, open: false }));
}
