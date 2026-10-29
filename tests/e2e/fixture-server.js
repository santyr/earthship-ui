import { createServer as createViteServer } from 'vite';
import { resolve } from 'node:path';

// Never inherit a household proxy or credential, including in beforeAll hooks
// and APIRequestContext calls which do not pass through browser routing.
process.env.OPENHAB_PROXY_TARGET = 'http://127.0.0.1:9';
delete process.env.OPENHAB_TOKEN;

export const fixtureOrigins = new Set();

export async function createServer(options = {}) {
  const server = await createViteServer({
    ...options,
    cacheDir: resolve('.superpowers/test-cache/fixtures'),
    configLoader: 'runner',
    plugins: [{
      name: 'disposable-fixture-transport',
      enforce: 'pre',
      configureServer(server) {
        server.middlewares.use((request, response, next) => {
          const path = new URL(request.url, 'http://fixture.invalid').pathname;
          if (path === '/config.json') {
            response.setHeader('Content-Type', 'application/json');
            response.end(JSON.stringify({ openhabUrl: '', apiToken: '', staleBannerSeconds: 90 }));
            return;
          }
          // The shade preview is an in-memory simulator, with no action RPC.
          if (/^\/api\/shades-preview(?:\/events)?$/.test(path)) return next();
          if (/^\/(?:fixture-openhab\/)?rest(?:\/|$)/.test(path) || path.startsWith('/api/')) {
            response.statusCode = 503;
            response.setHeader('Content-Type', 'application/json');
            response.end(JSON.stringify({ status: 'unavailable' }));
            return;
          }
          next();
        });
      },
    }, ...(options.plugins || [])],
    server: { ...options.server, host: '127.0.0.1', port: 0, strictPort: false },
  });
  let origin;
  server.httpServer.once('listening', () => {
    origin = 'http://127.0.0.1:' + server.httpServer.address().port;
    fixtureOrigins.add(origin);
  });
  server.httpServer.once('close', () => fixtureOrigins.delete(origin));
  return server;
}
