import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createClient } from '../src/lib/openhab/client.js';
const cfg = { openhabUrl: 'http://oh:8080', apiToken: 'TK' };
beforeEach(() => { global.fetch = vi.fn(); });

it('getAllItems returns parsed array with auth header', async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => [{ name: 'A', state: '5', type: 'Number' }] });
  const items = await createClient(cfg).getAllItems();
  expect(items[0].name).toBe('A');
  expect(fetch).toHaveBeenCalledWith('http://oh:8080/rest/items?fields=name,state,type',
    expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer TK' }) }));
});
it('sendCommand posts plain text body', async () => {
  fetch.mockResolvedValue({ ok: true });
  await createClient(cfg).sendCommand('Sw', 'ON');
  const [url, opts] = fetch.mock.calls[0];
  expect(url).toBe('http://oh:8080/rest/items/Sw');
  expect(opts.method).toBe('POST');
  expect(opts.body).toBe('ON');
  expect(opts.headers['Content-Type']).toBe('text/plain');
});
it('getHistory preserves raw states for strict series-aware parsing', async () => {
  fetch.mockResolvedValue({ ok: true, headers: new Headers(), json: async () => ({ data: [{ time: 1000, state: '54 %' }, { time: 2000, state: '55.5' }] }) });
  const h = await createClient(cfg).getHistory('BMS_SOC', { starttime: 'a', endtime: 'b' });
  expect(h).toEqual([{ time: 1000, state: '54 %' }, { time: 2000, state: '55.5' }]);
});
it('getHistory forwards one cancellation signal to fetch', async () => {
  fetch.mockResolvedValue({ ok: true, headers: new Headers(), json: async () => ({ data: [] }) });
  const controller = new AbortController();
  await createClient(cfg).getHistory('BMS_SOC', {
    starttime: 'a',
    endtime: 'b',
    signal: controller.signal,
  });

  expect(fetch).toHaveBeenCalledWith(
    expect.stringContaining('/rest/persistence/items/BMS_SOC?'),
    expect.objectContaining({ signal: controller.signal }),
  );
});
it('getHistory rejects a declared response larger than 5 MiB before reading it', async () => {
  const json = vi.fn();
  fetch.mockResolvedValue({
    ok: true,
    headers: new Headers({ 'content-length': String(5 * 1024 * 1024 + 1) }),
    json,
  });

  await expect(createClient(cfg).getHistory('BMS_SOC', { starttime: 'a', endtime: 'b' }))
    .rejects.toThrow(/response.*large/i);
  expect(json).not.toHaveBeenCalled();
});
it('getHistory rejects chunked bodies that cross the 5 MiB limit', async () => {
  const chunk = new Uint8Array(3 * 1024 * 1024);
  const cancel = vi.fn();
  const read = vi.fn()
    .mockResolvedValueOnce({ done: false, value: chunk })
    .mockResolvedValueOnce({ done: false, value: chunk });
  fetch.mockResolvedValue({
    ok: true,
    headers: new Headers(),
    body: { getReader: () => ({ read, cancel }) },
  });

  await expect(createClient(cfg).getHistory('BMS_SOC', { starttime: 'a', endtime: 'b' }))
    .rejects.toThrow(/response.*large/i);
  expect(cancel).toHaveBeenCalled();
});
it('getHistory rejects more than 300,000 rows', async () => {
  fetch.mockResolvedValue({
    ok: true,
    headers: new Headers(),
    json: async () => ({ data: Array.from({ length: 300_001 }, () => null) }),
  });

  await expect(createClient(cfg).getHistory('BMS_SOC', { starttime: 'a', endtime: 'b' }))
    .rejects.toThrow(/too many.*rows/i);
});
it('sendCommand throws on non-ok', async () => {
  fetch.mockResolvedValue({ ok: false, status: 500 });
  await expect(createClient(cfg).sendCommand('Sw', 'ON')).rejects.toThrow(/500/);
});
it('getItem fetches a single item with auth header', async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ name: 'BMS_SOC', state: '54' }) });
  const it = await createClient(cfg).getItem('BMS_SOC');
  expect(it.state).toBe('54');
  const [url, opts] = fetch.mock.calls[0];
  expect(url).toBe('http://oh:8080/rest/items/BMS_SOC');
  expect(opts.headers.Authorization).toBe('Bearer TK');
});
