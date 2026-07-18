import { afterEach, describe, expect, it, vi } from 'vitest';
import { observeElementSize } from '../src/lib/ui/observeElementSize.js';

describe('shared debounced chart resize observer', () => {
  afterEach(() => vi.useRealTimers());

  it('coalesces resize bursts for 100ms and ignores width deltas below 8px', () => {
    vi.useFakeTimers();
    let callback;
    const disconnect = vi.fn();
    class Observer {
      constructor(cb) { callback = cb; }
      observe() {}
      disconnect() { disconnect(); }
    }
    const onSize = vi.fn();
    const stop = observeElementSize({}, onSize, { ResizeObserverImpl: Observer });

    callback([{ contentRect: { width: 400, height: 200 } }]);
    callback([{ contentRect: { width: 405, height: 200 } }]);
    vi.advanceTimersByTime(99);
    expect(onSize).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onSize).toHaveBeenCalledTimes(1);
    expect(onSize).toHaveBeenLastCalledWith({ width: 405, height: 200 });

    callback([{ contentRect: { width: 412, height: 200 } }]);
    vi.advanceTimersByTime(100);
    expect(onSize).toHaveBeenCalledTimes(1);
    callback([{ contentRect: { width: 413, height: 200 } }]);
    vi.advanceTimersByTime(100);
    expect(onSize).toHaveBeenCalledTimes(2);
    stop();
    expect(disconnect).toHaveBeenCalled();
  });
});
