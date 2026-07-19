import { writable } from 'svelte/store';

let nextOpenId = 0;

export const weatherDetailStore = writable({
  open: false,
  openId: 0,
  date: null,
  label: '',
  openedAtMs: 0,
  opener: null,
});

export function openWeatherDetail({ date = null, label = 'Forecast' } = {}) {
  weatherDetailStore.set({
    open: true,
    openId: ++nextOpenId,
    date,
    label,
    openedAtMs: Date.now(),
    opener: typeof document !== 'undefined' && document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null,
  });
}

export function closeWeatherDetail() {
  weatherDetailStore.update((state) => ({ ...state, open: false }));
}
