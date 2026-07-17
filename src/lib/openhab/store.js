import { writable } from 'svelte/store';
import { createClient } from './client.js';
import { createSSE } from './sse.js';

export const items = writable({});
export const connection = writable('connecting');

export function applySnapshot(arr) {
  items.update((m) => { for (const it of arr) m[it.name] = it.state; return { ...m }; });
}
export function applyState(name, value) {
  items.update((m) => { m[name] = value; return { ...m }; });
}

export async function initOpenhab(config) {
  const client = createClient(config);
  applySnapshot(await client.getAllItems());
  const sse = createSSE({
    ...config,
    staleSeconds: config.staleBannerSeconds,
    onState: applyState,
    onStatus: (s) => connection.set(s),
  });
  sse.start();
  return client;
}
