import { DIRECT_COMMAND_ITEMS, REQUEST_POST_ITEMS } from '../controls/catalog.js';
import { resolveReleaseMode } from '../releaseMode.js';

const DIRECT_POST_PATHS = new Set(
  DIRECT_COMMAND_ITEMS.map((item) => `/rest/items/${encodeURIComponent(item)}`),
);

// The four correlated owner request channels. POSTing here submits a JSON
// request the owner rule validates and serializes; it never actuates directly.
const REQUEST_POST_PATHS = new Set(
  REQUEST_POST_ITEMS.map((item) => `/rest/items/${encodeURIComponent(item)}`),
);

const ALLOWED_POST_PATHS = new Set([...DIRECT_POST_PATHS, ...REQUEST_POST_PATHS]);

function requestPath(rawUrl) {
  try {
    return decodeURIComponent(new URL(rawUrl, 'http://earthship-ui.local').pathname);
  } catch {
    return null;
  }
}

export function isAllowedProxyRequest(method, rawUrl, releaseMode = 'maintenance') {
  const verb = String(method || '').toUpperCase();
  const path = requestPath(rawUrl);
  if (!path?.startsWith('/rest/')) return false;
  if (verb === 'GET') return true;
  if (!['safe-compat', 'full'].includes(resolveReleaseMode(releaseMode))) {
    return false;
  }
  return verb === 'POST' && ALLOWED_POST_PATHS.has(path);
}

export function openhabProxyAuthorization(token) {
  if (typeof token !== 'string' || !token.trim()) {
    throw new TypeError('OpenHAB proxy token is required');
  }
  return `Basic ${Buffer.from(`${token}:`).toString('base64')}`;
}

export const PROXY_DIRECT_COMMAND_ITEMS = Object.freeze([...DIRECT_COMMAND_ITEMS]);
