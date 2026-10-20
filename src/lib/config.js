import { withReadTimeout } from './openhab/readRequest.js';

export function parseConfig(raw) {
  if (!raw || typeof raw.openhabUrl !== 'string') throw new Error('config: openhabUrl required');
  if (typeof raw.apiToken !== 'string') throw new Error('config: apiToken required');
  return {
    openhabUrl: raw.openhabUrl.replace(/\/$/, ''),
    apiToken: raw.apiToken,
    staleBannerSeconds: Number.isFinite(raw.staleBannerSeconds) ? raw.staleBannerSeconds : 90,
  };
}
export function loadConfig(options = {}) {
  return withReadTimeout(async signal => {
    const r = await fetch('/config.json', { cache: 'no-store', signal });
    if (!r.ok) throw new Error('config.json not found — copy config.example.json');
    return parseConfig(await r.json());
  }, options);
}
