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
it('getHistory maps time/state to numbers', async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ data: [{ time: 1000, state: '54' }, { time: 2000, state: '55.5' }] }) });
  const h = await createClient(cfg).getHistory('BMS_SOC', { starttime: 'a', endtime: 'b' });
  expect(h).toEqual([{ time: 1000, state: 54 }, { time: 2000, state: 55.5 }]);
});
it('sendCommand throws on non-ok', async () => {
  fetch.mockResolvedValue({ ok: false, status: 500 });
  await expect(createClient(cfg).sendCommand('Sw', 'ON')).rejects.toThrow(/500/);
});
