import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { parseSSEMessage, createSSE } from '../src/lib/openhab/sse.js';

describe('parseSSEMessage', () => {
  it('extracts item name and value from statechanged event', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/statechanged',
      payload: JSON.stringify({ value: '54', oldValue: '55' }),
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toEqual({ name: 'BMS_SOC', value: '54' });
  });

  it('returns null for non-item events (e.g. thing status)', () => {
    expect(parseSSEMessage(JSON.stringify({ topic: 'openhab/things/x/status', payload: '{}' }))).toBeNull();
  });

  it('returns null for malformed json', () => {
    expect(parseSSEMessage('not json')).toBeNull();
  });

  it('returns null when payload is missing value', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/statechanged',
      payload: JSON.stringify({ oldValue: '55' }),
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toBeNull();
  });

  it('returns null when payload itself is malformed json', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/statechanged',
      payload: 'not json',
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toBeNull();
  });

  it('returns null when topic is missing entirely', () => {
    const raw = JSON.stringify({ payload: JSON.stringify({ value: '1' }) });
    expect(parseSSEMessage(raw)).toBeNull();
  });

  it('returns null for an empty string input', () => {
    expect(parseSSEMessage('')).toBeNull();
  });

  it('returns null for other item event types on a non-statechanged topic suffix', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/added',
      payload: JSON.stringify({ value: '54' }),
      type: 'ItemAddedEvent',
    });
    expect(parseSSEMessage(raw)).toBeNull();
  });

  it('coerces a numeric value to a string', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/Grid_Power/statechanged',
      payload: JSON.stringify({ value: 1234 }),
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toEqual({ name: 'Grid_Power', value: '1234' });
  });

  it('handles item names containing underscores and digits', () => {
    const raw = JSON.stringify({
      topic: 'openhab/items/Solar_Panel_2_Voltage/statechanged',
      payload: JSON.stringify({ value: '48.2' }),
      type: 'ItemStateChangedEvent',
    });
    expect(parseSSEMessage(raw)).toEqual({ name: 'Solar_Panel_2_Voltage', value: '48.2' });
  });
});

describe('createSSE connection', () => {
  class FakeES {
    constructor(url) {
      this.url = url;
      this.close = vi.fn();
      this.onopen = null;
      this.onmessage = null;
      this.onerror = null;
      FakeES.instances.push(this);
    }
  }
  FakeES.instances = [];

  beforeEach(() => {
    FakeES.instances = [];
    globalThis.EventSource = FakeES;
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete globalThis.EventSource;
  });

  function makeSSE(overrides = {}) {
    return createSSE({
      openhabUrl: 'http://openhab.local:8080',
      apiToken: 'tok',
      onState: vi.fn(),
      onStatus: vi.fn(),
      ...overrides,
    });
  }

  it('Test A (Critical): stop() cancels a pending reconnect so no leaked EventSource fires after stop', () => {
    const sse = makeSSE();
    sse.start();
    expect(FakeES.instances.length).toBe(1);
    const first = FakeES.instances[0];

    // Simulate a connection error, which schedules a reconnect via setTimeout.
    first.onerror();

    sse.stop();
    expect(first.close).toHaveBeenCalled();

    // Advance well past any possible backoff (max cap is 30s); if the
    // reconnect timer wasn't cancelled, a second EventSource would appear.
    vi.advanceTimersByTime(60000);
    expect(FakeES.instances.length).toBe(1);
  });

  it('Test B (Important #3): calling start() twice without stop() does not leave two live connections', () => {
    const sse = makeSSE();
    sse.start();
    expect(FakeES.instances.length).toBe(1);
    const first = FakeES.instances[0];

    sse.start();
    expect(FakeES.instances.length).toBe(2);
    const second = FakeES.instances[1];

    // The first instance must have been closed by the second start/connect.
    expect(first.close).toHaveBeenCalled();

    // No more than one un-closed (live) instance should remain.
    const liveCount = FakeES.instances.filter((i) => i.close.mock.calls.length === 0).length;
    expect(liveCount).toBe(1);
    expect(second.close).not.toHaveBeenCalled();
  });

  it('Test C (Important #2): first reconnect is scheduled at 1000ms, not 2000ms', () => {
    const sse = makeSSE();
    sse.start();
    const first = FakeES.instances[0];

    first.onerror();

    vi.advanceTimersByTime(999);
    expect(FakeES.instances.length).toBe(1);

    vi.advanceTimersByTime(1);
    expect(FakeES.instances.length).toBe(2);
  });

  it('Test D (Minor #4): onStatus fires "live" only on transition, not on every message', () => {
    const onStatus = vi.fn();
    const sse = makeSSE({ onStatus });
    sse.start();
    const first = FakeES.instances[0];

    first.onopen();

    const validPayload = JSON.stringify({
      topic: 'openhab/items/BMS_SOC/statechanged',
      payload: JSON.stringify({ value: '54' }),
    });
    first.onmessage({ data: validPayload });
    first.onmessage({ data: validPayload });

    const liveCalls = onStatus.mock.calls.filter((c) => c[0] === 'live');
    expect(liveCalls.length).toBe(1);
  });
});
