import { describe, expect, it } from 'vitest';
import { createLatestRefreshCoordinator } from '../src/lib/ui/latestRefresh.js';

describe('latest refresh coordinator', () => {
  it('aborts the previous refresh and commits only the latest completion', async () => {
    const coordinator = createLatestRefreshCoordinator();
    const committed = [];
    let firstSignal;
    let secondSignal;
    let resolveFirst;
    let resolveSecond;

    const first = coordinator.run(
      (signal) => {
        firstSignal = signal;
        return new Promise((resolve) => { resolveFirst = resolve; });
      },
      (value) => committed.push(value),
    );
    const second = coordinator.run(
      (signal) => {
        secondSignal = signal;
        return new Promise((resolve) => { resolveSecond = resolve; });
      },
      (value) => committed.push(value),
    );

    expect(firstSignal.aborted).toBe(true);
    expect(secondSignal.aborted).toBe(false);
    resolveSecond('new');
    expect(await second).toBe(true);
    resolveFirst('old');
    expect(await first).toBe(false);
    expect(committed).toEqual(['new']);
  });

  it('aborts an unfinished refresh on destroy and prevents its commit', async () => {
    const coordinator = createLatestRefreshCoordinator();
    const committed = [];
    let signal;
    let resolveLoad;
    const refresh = coordinator.run(
      (nextSignal) => {
        signal = nextSignal;
        return new Promise((resolve) => { resolveLoad = resolve; });
      },
      (value) => committed.push(value),
    );

    coordinator.destroy();
    expect(signal.aborted).toBe(true);
    resolveLoad('late');
    expect(await refresh).toBe(false);
    expect(committed).toEqual([]);
  });
});
