// @vitest-environment jsdom
import { get } from 'svelte/store';
import { beforeEach, describe, expect, it } from 'vitest';
import {
  closeWeatherDetail,
  openWeatherDetail,
  weatherDetailStore,
} from '../src/lib/weather/detailStore.js';

describe('weather detail modal store', () => {
  beforeEach(() => {
    closeWeatherDetail();
    document.body.replaceChildren();
  });

  it('increments each opening identity and captures the exact opener', () => {
    const opener = document.createElement('button');
    document.body.append(opener);
    opener.focus();

    openWeatherDetail({ date: '2026-07-19', label: 'Tomorrow' });
    const first = get(weatherDetailStore);
    openWeatherDetail({ date: '2026-07-20', label: 'Monday' });
    const second = get(weatherDetailStore);

    expect(first).toMatchObject({
      open: true,
      date: '2026-07-19',
      label: 'Tomorrow',
      opener,
    });
    expect(second.openId).toBe(first.openId + 1);
    expect(second.date).toBe('2026-07-20');
  });

  it('closes without erasing the selection needed for focus restoration', () => {
    openWeatherDetail({ date: null, label: 'Today' });
    closeWeatherDetail();

    expect(get(weatherDetailStore)).toMatchObject({
      open: false,
      date: null,
      label: 'Today',
    });
  });
});
