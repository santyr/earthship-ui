import { randomUUID } from 'node:crypto';
import { evaluateShadePolicy, SHADE_POLICY_ITEMS, SHADE_POLICY_REVISION_ITEM, SHADE_POLICY_SESSION_ITEM } from './policyModel.js';

const validSwitch = (value) => value === 'ON' || value === 'OFF';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const error = (code, status = 503) => Object.assign(new Error(code), { code, status });
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// The browser never selects an Item/path and never receives upstream credentials.
// This policy-only owner cannot issue a Rollershutter, load, override or STOP command.
export function createShadePolicyOwner({ upstream, authorization, fetchImpl = fetch,
  now = Date.now, sessionIdFactory = randomUUID } = {}) {
  let sessionId = sessionIdFactory();
  let generation = 0;
  let previousKey = '';
  let wasConnected = false;
  let latest;
  let confirmedAt = {};
  let serial = Promise.resolve();
  const serialize = (operation) => {
    const result = serial.then(operation);
    serial = result.catch(() => {});
    return result;
  };
  async function request(path, options = {}, allowMissing = false) {
    const response = await fetchImpl(`${String(upstream).replace(/\/$/, '')}${path}`, {
      ...options, headers: { Authorization: authorization, Accept: 'application/json', ...options.headers },
      signal: AbortSignal.timeout(5000), cache: 'no-store',
    });
    if (!response.ok) {
      if (allowMissing && (response.status === 404 || response.status === undefined)) return null;
      throw error('source_unavailable');
    }
    return options.method === 'POST' ? null : response.json();
  }
  const item = (name) => request(`/rest/items/${name}`, {}, true);
  async function persisted(name, proofTime, windowMs = 1) {
    if (!Number.isFinite(proofTime) || proofTime < 0) return null;
    // OpenHAB history is ASCENDING and defaults to only the past day. Use the
    // owner's actual persisted timestamp, including for stable older choices.
    // Disable synthetic chart boundaries/current Item state: neither is proof.
    // Some REST persistence providers round query bounds to whole seconds.
    // Expand acquisition only; exact original proof timestamps still decide.
    const begin = Math.max(0, Math.floor((proofTime - 1) / 1000) * 1000);
    const end = Math.ceil((proofTime + windowMs) / 1000) * 1000;
    const proofEnd = proofTime + windowMs;
    const query = new URLSearchParams({ serviceId: 'jdbc', page: '0', pagelength: '1000',
      starttime: new Date(begin).toISOString(), endtime: new Date(end).toISOString(),
      boundary: 'false', itemState: 'false' });
    const result = await request(`/rest/persistence/items/${name}?${query}`, {}, true);
    if (!Array.isArray(result?.data) || result.data.length >= 1000) return null;
    return result.data.filter((row) => Number.isFinite(row.time) && row.time >= proofTime
      && row.time <= proofEnd && typeof row.state === 'string')
      .reduce((latest, row) => !latest || row.time >= latest.time ? row : latest, null);
  }
  function present(input) {
    if (!input.connected) confirmedAt = {};
    if (!input.connected && wasConnected) sessionId = sessionIdFactory();
    wasConnected = input.connected;
    const key = JSON.stringify(input);
    if (key !== previousKey) { generation += 1; previousKey = key; }
    latest = evaluateShadePolicy({ ...input, sessionId, generation,
      // Commissioning and release require a future verified execution owner.
      // Environment flags or a saved ON switch cannot open these gates.
      commissioned: false, globalReleased: false });
    return structuredClone(latest);
  }
  async function reconcile() {
    const unavailable = { connected: false, sourceGeneration: null, preferences: {}, confirmed: {}, override: null, overrideAuthoritative: false };
    if (!authorization || !upstream) return present(unavailable);
    try {
      const [first, firstSession] = await Promise.all([item(SHADE_POLICY_REVISION_ITEM), item(SHADE_POLICY_SESSION_ITEM)]);
      const receipt = JSON.parse(first?.state ?? 'null');
      if (first?.type !== 'String' || receipt?.schemaVersion !== 1 || receipt.durable !== true
          || !uuid.test(receipt.generation ?? '') || !uuid.test(receipt.ownerSession ?? '')
          || firstSession?.state !== receipt.ownerSession || !Number.isFinite(receipt.at)
          || receipt.at > now() + 60_000) return present(unavailable);
      const [receiptHistory, preferenceReads, preferenceHistory, override] = await Promise.all([
        persisted(SHADE_POLICY_REVISION_ITEM, receipt.at, 60_000),
        Promise.all(Object.values(SHADE_POLICY_ITEMS).map(item)),
        Promise.all(Object.entries(SHADE_POLICY_ITEMS).map(([zone, name]) => persisted(name, receipt.persistedAt?.[zone]))),
        item('OverrideSwitch'),
      ]);
      // This final read must follow ALL source reads, never run alongside them.
      const [last, lastSession] = await Promise.all([item(SHADE_POLICY_REVISION_ITEM), item(SHADE_POLICY_SESSION_ITEM)]);
      // A receipt seen only in the registry is not a durable policy commit.
      if (first.state !== last?.state || firstSession.state !== lastSession?.state
          || receiptHistory?.state !== first.state
          || receiptHistory.time < receipt.at) return present(unavailable);
      const preferences = {}, confirmed = {};
      confirmedAt = {};
      Object.keys(SHADE_POLICY_ITEMS).forEach((zone, index) => {
        const current = preferenceReads[index], history = preferenceHistory[index];
        preferences[zone] = validSwitch(current?.state) ? current.state : null;
        confirmed[zone] = current?.type === 'Switch' && preferences[zone] !== null
          && receipt.preferences?.[zone] === current.state && history?.state === current.state
          && Number.isFinite(receipt.persistedAt?.[zone]) && history.time === receipt.persistedAt[zone];
        if (confirmed[zone]) confirmedAt[zone] = history.time;
      });
      const overrideAuthoritative = override?.type === 'Switch' && validSwitch(override?.state)
        && receipt.override === override.state;
      return present({ connected: true, sourceGeneration: receipt.generation, preferences, confirmed,
        override: overrideAuthoritative ? override.state : null, overrideAuthoritative });
    } catch { return present(unavailable); }
  }
  return {
    read: () => serialize(reconcile),
    update: (change) => serialize(async () => {
      if (!authorization || !upstream) throw error('authentication_unavailable');
      if (!change || Array.isArray(change) || Object.keys(change).sort().join(',') !== 'enabled,expectedGeneration,expectedSessionId,zone'
          || !Object.hasOwn(SHADE_POLICY_ITEMS, change.zone) || typeof change.enabled !== 'boolean'
          || !Number.isSafeInteger(change.expectedGeneration) || typeof change.expectedSessionId !== 'string') throw error('invalid_change', 400);
      const before = await reconcile();
      if (before.sessionId !== change.expectedSessionId || before.generation !== change.expectedGeneration) throw error('policy_conflict', 409);
      if (!before.connected || !before.zones[change.zone].authoritative) throw error('policy_unavailable');
      const value = change.enabled ? 'ON' : 'OFF';
      if (before.zones[change.zone].saved === value) return before;
      const started = now();
      await request(`/rest/items/${SHADE_POLICY_ITEMS[change.zone]}`, {
        method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: value,
      });
      for (let attempt = 0; attempt < 30; attempt += 1) {
        const result = await reconcile();
        if (result.connected && result.sourceGeneration !== before.sourceGeneration
            && result.zones[change.zone].authoritative && result.zones[change.zone].saved === value) {
          if (confirmedAt[change.zone] >= started) return result;
        }
        if (attempt < 29) await sleep(100);
      }
      throw error('save_unconfirmed');
    }),
  };
}

export function shadePolicyPlugin(options = {}) {
  const owner = options.owner ?? createShadePolicyOwner(options);
  return {
    name: 'shade-recommendation-policy-only',
    configureServer(server) {
      server.middlewares.use('/api/shades-policy', async (req, res) => {
        const send = (status, data) => {
          res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
          res.end(JSON.stringify(data));
        };
        const url = new URL(req.url || '/', 'http://localhost');
        if (url.pathname !== '/' || url.search) { send(400, { error: 'invalid_path' }); return; }
        if (req.method === 'GET') {
          try { send(200, await owner.read()); } catch { send(503, { error: 'policy_unavailable' }); }
          return;
        }
        if (req.method !== 'POST') { send(405, { error: 'method_not_allowed' }); return; }
        let sameOrigin = false;
        try {
          const origin = new URL(req.headers.origin);
          sameOrigin = origin.host === req.headers.host && ['http:', 'https:'].includes(origin.protocol);
        } catch { /* missing/malformed Origin is not an authenticated policy request */ }
        if (!sameOrigin || req.headers['content-type']?.split(';')[0] !== 'application/json') {
          send(403, { error: 'request_forbidden' }); return;
        }
        try {
          const body = await new Promise((resolve, reject) => {
            let raw = '', rejected = false;
            req.on('data', (chunk) => {
              if (rejected) return;
              raw += chunk;
              if (raw.length > 1024) { rejected = true; raw = ''; reject(error('body_too_large', 413)); }
            });
            req.on('error', reject);
            req.on('aborted', () => reject(error('request_aborted', 400)));
            req.on('end', () => { if (rejected) return; try { resolve(JSON.parse(raw)); } catch { reject(error('invalid_json', 400)); } });
          });
          send(200, await owner.update(body));
        } catch (failure) {
          let snapshot;
          try { snapshot = await owner.read(); } catch { /* unavailable remains unconfirmed */ }
          send(failure.status ?? 503, { error: failure.code ?? 'save_unconfirmed', snapshot });
        }
      });
    },
  };
}
