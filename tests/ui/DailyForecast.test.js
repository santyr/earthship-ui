// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `${process.cwd()}/node_modules/svelte/src/index-client.js`
));

import DailyForecast from '../../src/lib/ui/DailyForecast.svelte';

const days = Array.from({ length: 10 }, (_, index) => ({
  date: `2026-07-${String(18 + index).padStart(2, '0')}`,
  label: index === 0 ? 'Today' : `Day ${index + 1}`,
  summary: {
    highF: 80 + index,
    lowF: 50 + index,
    precipPct: index * 5,
    weatherCode: 1,
    pvKwh: 6.4,
  },
  hours: [],
}));

afterEach(cleanup);

describe('DailyForecast', () => {
  it('renders ten native day buttons and emits the selected day', async () => {
    const onselect = vi.fn();
    const { container } = render(DailyForecast, {
      props: { days, variant: 'home', onselect },
    });

    expect(screen.getAllByRole('button')).toHaveLength(10);
    expect(container.querySelector('[data-forecast-variant="home"]')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: /Day 2/i }));
    expect(onselect).toHaveBeenCalledWith(days[1]);
  });

  it('renders the weather two-column variant and keeps legacy rows activatable', async () => {
    const onselect = vi.fn();
    const legacy = [{ ...days[0], date: null, label: 'Today' }];
    const { container } = render(DailyForecast, {
      props: { days: legacy, variant: 'weather', onselect },
    });

    expect(container.querySelector('[data-forecast-variant="weather"]')).toBeTruthy();
    await fireEvent.click(screen.getByRole('button', { name: /Today/i }));
    expect(onselect).toHaveBeenCalledWith(legacy[0]);
  });

  it('names each button with date, condition, temperatures, and precipitation', () => {
    render(DailyForecast, { props: { days: [days[0]], variant: 'home' } });

    expect(screen.getByRole('button', {
      name: /Today.*sunny.*high 80 degrees.*low 50 degrees.*precipitation 0 percent/i,
    })).toBeTruthy();
  });
});
