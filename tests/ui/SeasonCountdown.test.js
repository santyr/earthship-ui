// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '../../node_modules/svelte/src/index-client.js'
));

import SeasonCountdown from '../../src/lib/ui/SeasonCountdown.svelte';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('SeasonCountdown', () => {
  it('advances its local-date label after midnight without a reload', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(2026, 8, 21, 23, 30));
    const view = render(SeasonCountdown);

    expect(screen.getByText('1 day to autumn equinox')).toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(1);

    vi.advanceTimersByTime(60 * 60 * 1000);
    await tick();

    expect(screen.getByText('autumn equinox today')).toBeInTheDocument();
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
