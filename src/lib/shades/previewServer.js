import { SHADE_COUNT, SHADE_SLOTS, shadePreviewEnabled } from './catalog.js';

// Ephemeral UI rehearsal state. This endpoint has no openHAB or radio imports.
// Motor reports remain the sole authority once shade Items are commissioned.
export function shadePreviewPlugin() {
  const enabled = shadePreviewEnabled(SHADE_SLOTS);
  const positions = Array(SHADE_COUNT).fill(50);
  const listeners = new Set();
  let revision = 0;
  const snapshot = () => ({ revision, positions });
  const publish = () => {
    const event = `data: ${JSON.stringify(snapshot())}\n\n`;
    for (const response of listeners) response.write(event);
  };
  return {
    name: 'shade-preview-only-sync',
    configureServer(server) {
      server.middlewares.use('/api/shades-preview', (request, response) => {
        const path = new URL(request.url || '/', 'http://localhost').pathname;
        if (!enabled) {
          response.writeHead(409).end('Shade preview disabled after Item mapping');
          return;
        }
        if (request.method === 'GET' && path === '/events') {
          response.writeHead(200, {
            'Content-Type': 'text/event-stream; charset=utf-8',
            'Cache-Control': 'no-store',
            'X-Accel-Buffering': 'no',
          });
          listeners.add(response);
          response.write(`data: ${JSON.stringify(snapshot())}\n\n`);
          const heartbeat = setInterval(() => response.write(': keepalive\n\n'), 15_000);
          request.on('close', () => { clearInterval(heartbeat); listeners.delete(response); });
          return;
        }
        if (request.method !== 'POST' || path !== '/') {
          response.writeHead(405).end();
          return;
        }
        const origin = request.headers.origin;
        const host = request.headers.host;
        let sameOrigin = false;
        try {
          const parsed = new URL(origin);
          sameOrigin = parsed.host === host && ['http:', 'https:'].includes(parsed.protocol);
        } catch { /* missing or malformed Origin */ }
        if (!sameOrigin
            || request.headers['content-type']?.split(';')[0] !== 'application/json') {
          response.writeHead(403).end();
          return;
        }
        let body = '';
        let tooLarge = false;
        request.on('data', (chunk) => {
          if (tooLarge) return;
          body += chunk;
          if (body.length > 2048) {
            tooLarge = true;
            response.writeHead(413).end();
          }
        });
        request.on('end', () => {
          if (tooLarge) return;
          let change;
          try { change = JSON.parse(body); } catch { response.writeHead(400).end(); return; }
          if (!Array.isArray(change?.slots) || change.slots.length < 1 || change.slots.length > SHADE_COUNT
              || new Set(change.slots).size !== change.slots.length
              || !change.slots.every((slot) => Number.isInteger(slot) && slot >= 1 && slot <= SHADE_COUNT)
              || !Number.isInteger(change.openPercent) || change.openPercent < 0 || change.openPercent > 100) {
            response.writeHead(400).end();
            return;
          }
          for (const slot of change.slots) positions[slot - 1] = change.openPercent;
          revision += 1;
          publish();
          response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
          response.end(JSON.stringify(snapshot()));
        });
      });
    },
  };
}
