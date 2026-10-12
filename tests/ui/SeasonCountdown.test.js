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

import { items, itemUpdateEvidence, thingStatuses, connection } from '../../src/lib/openhab/store.js';

describe('SeasonCountdown', () => {
  it('shows native whole days and expires the evidence at household midnight', async () => {
    vi.useFakeTimers();
    const now = Date.parse('2026-10-13T05:59:45Z');
    vi.setSystemTime(now);
    items.set({ Sun_TimeLeft:'0 d', Sun_NextSeason:'WINTER' });
    itemUpdateEvidence.set({ Sun_TimeLeft:{ available:true,lastKnown:now,state:'0 d' }, Sun_NextSeason:{ available:true,lastKnown:now,state:'WINTER' } });
    thingStatuses.set({ 'astro:sun:local':{ status:'ONLINE' } });
    connection.set('live');
    const view = render(SeasonCountdown);
    expect(screen.getByText('less than 1 day until Winter ❄️')).toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(30_000);
    await tick();
    expect(screen.getByText('Season unavailable')).toBeInTheDocument();
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
