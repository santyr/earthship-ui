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

// The UI only ever reads four REST surfaces. GET is narrowed to exactly these
// path prefixes so a LAN client can no longer pull /rest/rules (full scripts),
// /rest/services/*/config (future cloud API keys), /rest/addons, /rest/bindings,
// or the /rest/ root index. Everything outside the allowlist is denied.
//   - /rest/items            item state snapshot + per-item reads
//   - /rest/events           the SSE stream (and sub-topics)
//   - /rest/persistence/items/  history for a named item
//   - /rest/things           provider status — BUT see the contract note below
function isAllowedGetPath(path) {
  return (
    path === '/rest/items' || path.startsWith('/rest/items/')
    || path === '/rest/events' || path.startsWith('/rest/events/')
    || path.startsWith('/rest/persistence/items/')
    || path === '/rest/things' || path.startsWith('/rest/things/')
  );
}

// CONTRACT: GET /rest/things (and /rest/things/{uid}) is reported allowed here,
// but it is NEVER proxied raw. vite.config.js's guard middleware pre-empts every
// GET /rest/things* request, fetches upstream server-side, and returns only the
// sanitizeThingsResponse() projection {UID,label,statusInfo} — configuration
// blocks (with plaintext binding credentials), properties, and channels never
// reach the client. This function stays permissive for /rest/things so the guard
// can hand the request off; the projection is enforced in the middleware and is
// unit-tested separately via sanitizeThingDto / sanitizeThingsResponse.
export function isAllowedProxyRequest(method, rawUrl, releaseMode = 'maintenance') {
  const verb = String(method || '').toUpperCase();
  const path = requestPath(rawUrl);
  if (!path?.startsWith('/rest/')) return false;
  if (verb === 'GET') return isAllowedGetPath(path);
  if (!['safe-compat', 'full'].includes(resolveReleaseMode(releaseMode))) {
    return false;
  }
  return verb === 'POST' && ALLOWED_POST_PATHS.has(path);
}

// The only three status fields the UI (store.js normalizeThingStatus + client.js)
// ever reads off a Thing. Projecting to exactly these drops anything else openHAB
// might nest inside statusInfo in a future version.
function projectStatusInfo(statusInfo) {
  if (!statusInfo || typeof statusInfo !== 'object') return undefined;
  const projected = {};
  for (const key of ['status', 'statusDetail', 'description']) {
    if (statusInfo[key] !== undefined) projected[key] = statusInfo[key];
  }
  return projected;
}

// Pure projection of a raw openHAB Thing DTO down to only {UID,label,statusInfo}.
// A raw DTO carries `configuration` (plaintext MQTT/Shelly passwords, usernames,
// device IPs), `properties`, and `channels`; NONE of those keys survive here.
export function sanitizeThingDto(thing) {
  if (!thing || typeof thing !== 'object') return null;
  const projected = {};
  if (thing.UID !== undefined) projected.UID = thing.UID;
  if (thing.label !== undefined) projected.label = thing.label;
  const statusInfo = projectStatusInfo(thing.statusInfo);
  if (statusInfo !== undefined) projected.statusInfo = statusInfo;
  return projected;
}

// Projects a /rest/things response: an array of Things (collection endpoint) or a
// single Thing DTO (/rest/things/{uid}).
export function sanitizeThingsResponse(raw) {
  if (Array.isArray(raw)) return raw.map(sanitizeThingDto).filter(Boolean);
  return sanitizeThingDto(raw);
}

// A GET /rest/things* path the guard middleware must intercept and sanitize
// rather than proxy raw.
export function isThingsGetPath(path) {
  return path === '/rest/things' || path.startsWith('/rest/things/');
}

export function openhabProxyAuthorization(token) {
  if (typeof token !== 'string' || !token.trim()) {
    throw new TypeError('OpenHAB proxy token is required');
  }
  return `Basic ${Buffer.from(`${token}:`).toString('base64')}`;
}

export const PROXY_DIRECT_COMMAND_ITEMS = Object.freeze([...DIRECT_COMMAND_ITEMS]);
