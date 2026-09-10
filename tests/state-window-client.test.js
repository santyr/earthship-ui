import { afterEach, expect, it, vi } from 'vitest';
import { createClient, MAX_HISTORY_RESPONSE_BYTES } from '../src/lib/openhab/client.js';

const starttime = '2026-09-04T06:01:00Z';
const endtime = '2026-09-04T06:03:00Z';
const start = Date.parse(starttime);
const end = Date.parse(endtime);
const client = () => createClient({ openhabUrl: '', apiToken: '' });

afterEach(() => vi.unstubAllGlobals());

it('keeps the start state, clips the native end boundary, and preserves raw fields', async () => {
  const rows = [
    { time: start, state: '65.48', unit: '°C' },
    { time: start + 105525, state: 'invalid' },
    { time: end, state: '65.48' },
    { time: end + 1, state: '100' },
    { time: start - 1, state: '100' },
    { time: null, state: '100' },
  ];
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: rows })));
  vi.stubGlobal('fetch', fetcher);

  await expect(client().getHistory('Outdoor', { starttime, endtime, includeStartState: true }))
    .resolves.toEqual(rows.slice(0, 2));
  const url = new URL(fetcher.mock.calls[0][0], 'http://fixture');
  expect(url.searchParams.get('boundary')).toBe('true');
  expect(url.searchParams.has('itemState')).toBe(false);
});

it('returns an empty range without fetching', async () => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  await expect(client().getHistory('Outdoor', {
    starttime,
    endtime: starttime,
    includeStartState: true,
  })).resolves.toEqual([]);
  expect(fetcher).not.toHaveBeenCalled();
});

it.each([
  [undefined, endtime],
  ['', endtime],
  ['invalid', endtime],
  ['2026-09-04T06:01:00', endtime],
  [starttime, '2026-09-04T06:03:00'],
  [endtime, starttime],
  [starttime, null],
])('rejects malformed, reversed, or unqualified range %s %s before I/O', async (a, b) => {
  const fetcher = vi.fn();
  vi.stubGlobal('fetch', fetcher);
  await expect(client().getHistory('Outdoor', {
    starttime: a,
    endtime: b,
    includeStartState: true,
  })).rejects.toMatchObject({ code: 'invalid-history-window' });
  expect(fetcher).not.toHaveBeenCalled();
});

it('leaves the default history path unchanged', async () => {
  const rows = [{ time: start - 1, state: '65.48' }, { time: end, state: '65.3' }];
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: rows })));
  vi.stubGlobal('fetch', fetcher);
  await expect(client().getHistory('Outdoor', { starttime, endtime })).resolves.toEqual(rows);
  const url = new URL(fetcher.mock.calls[0][0], 'http://fixture');
  expect(url.searchParams.has('boundary')).toBe(false);
});

it('retains HTTP, malformed-body, and byte-limit errors', async () => {
  const fetcher = vi.fn()
    .mockResolvedValueOnce(new Response('nope', { status: 503 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: {} })))
    .mockResolvedValueOnce(new Response('{}', {
      headers: { 'content-length': String(MAX_HISTORY_RESPONSE_BYTES + 1) },
    }));
  vi.stubGlobal('fetch', fetcher);

  await expect(client().getHistory('Outdoor', { starttime, endtime, includeStartState: true }))
    .rejects.toThrow(/503/);
  await expect(client().getHistory('Outdoor', { starttime, endtime, includeStartState: true }))
    .rejects.toMatchObject({ code: 'invalid-history-response' });
  await expect(client().getHistory('Outdoor', { starttime, endtime, includeStartState: true }))
    .rejects.toMatchObject({ code: 'history-response-too-large' });
});

it('forwards the abort signal and propagates AbortError', async () => {
  const controller = new AbortController();
  const abort = new DOMException('aborted', 'AbortError');
  const fetcher = vi.fn().mockRejectedValue(abort);
  vi.stubGlobal('fetch', fetcher);
  await expect(client().getHistory('Outdoor', {
    starttime,
    endtime,
    includeStartState: true,
    signal: controller.signal,
  })).rejects.toBe(abort);
  expect(fetcher).toHaveBeenCalledWith(
    expect.stringContaining('/rest/persistence/items/Outdoor?'),
    expect.objectContaining({ signal: controller.signal }),
  );
});
