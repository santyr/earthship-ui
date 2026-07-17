import { writable } from 'svelte/store';
import { createClient } from './client.js';
import { createSSE } from './sse.js';

export const items = writable({});
export const connection = writable('connecting');
// Flips true once initOpenhab() has created the client AND loaded the
// initial item snapshot. Components that fetch via getClientOnce() on
// mount (e.g. HistoryChart) can react to this instead of racing App.svelte's
// onMount — critical for a direct/reload load of a chart route, where child
// components mount before initOpenhab() has run.
export const clientReady = writable(false);

let _client = null;

// Returns the singleton openHAB client created by initOpenhab(), or null if
// initOpenhab() hasn't run yet. Lets any component reach the client (for
// getHistory/sendCommand) without threading it through props.
export function getClientOnce() {
  return _client;
}

export function applySnapshot(arr) {
  items.update((m) => { for (const it of arr) m[it.name] = it.state; return { ...m }; });
}
export function applyState(name, value) {
  items.update((m) => { m[name] = value; return { ...m }; });
}

export async function initOpenhab(config) {
  const client = createClient(config);
  _client = client;
  applySnapshot(await client.getAllItems());
  clientReady.set(true);
  const sse = createSSE({
    ...config,
    staleSeconds: config.staleBannerSeconds,
    onState: applyState,
    onStatus: (s) => connection.set(s),
  });
  sse.start();
  return client;
}
