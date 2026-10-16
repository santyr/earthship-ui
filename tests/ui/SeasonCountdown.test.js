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
  it('accepts a fresh SSE generation before the periodic clock tick', async () => {
    vi.useFakeTimers();
    const now = Date.parse('2026-10-12T16:00:00Z');
    vi.setSystemTime(now);
    items.set({ Sun_TimeLeft:'2 d', Sun_NextSeason:'WINTER' });
    itemUpdateEvidence.set({ Sun_TimeLeft:{ available:true,lastKnown:now,state:'2 d' }, Sun_NextSeason:{ available:true,lastKnown:now,state:'WINTER' } });
    thingStatuses.set({ 'astro:sun:local':{ status:'ONLINE' } });
    connection.set('live');
    render(SeasonCountdown);
    expect(screen.getByText('2 days until Winter ❄️')).toBeInTheDocument();
    vi.setSystemTime(now + 5_000); // No interval callback has run.
    items.set({ Sun_TimeLeft:'1 d', Sun_NextSeason:'WINTER' });
    itemUpdateEvidence.set({ Sun_TimeLeft:{ available:true,lastKnown:now+5000,state:'1 d' }, Sun_NextSeason:{ available:true,lastKnown:now+5000,state:'WINTER' } });
    await tick();
    expect(screen.getByText('1 day until Winter ❄️')).toBeInTheDocument();
  });
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
