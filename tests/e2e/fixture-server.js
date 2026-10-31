import { resolve } from 'node:path';

// Never inherit a household proxy or credential, including in beforeAll hooks
// and APIRequestContext calls which do not pass through browser routing.
process.env.OPENHAB_PROXY_TARGET = 'http://127.0.0.1:9';
delete process.env.OPENHAB_TOKEN;

export const fixtureOrigins = new Set();

export async function createServer(options = {}) {
  if (process.env.EARTHSHIP_FIXTURE_BUILD_DIR && options.configFile !== false && !options.plugins?.length) {
    const {createBuiltFixtureServer} = await import('./built-fixture-server.js');
    return createBuiltFixtureServer(resolve(process.env.EARTHSHIP_FIXTURE_BUILD_DIR, process.env.RELEASE_MODE || 'maintenance'), fixtureOrigins);
  }
  const {createServer: createViteServer} = await import('vite');
  const server = await createViteServer({
    ...options,
    cacheDir: resolve('.superpowers/test-cache/fixtures'),
    configLoader: 'runner',
    // The checkout can contain retained releases with their own index.html.
    // Scan only this fixture app, never the entire evidence/worktree archive.
    optimizeDeps: { ...options.optimizeDeps, entries: options.configFile === false ? [] : ['index.html'] },
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
  const sockets = new Set();
  server.httpServer.on('connection', socket => {
    sockets.add(socket);
    socket.once('close', () => sockets.delete(socket));
  });
  const close = server.close.bind(server);
  let closing;
  server.close = () => {
    if (!closing) {
      // Only connections accepted by this disposable listener are owned here.
      server.httpServer.closeIdleConnections?.();
      for (const socket of sockets) socket.destroy();
      closing = close();
    }
    return closing;
  };
  let origin;
  server.httpServer.once('listening', () => {
    origin = 'http://127.0.0.1:' + server.httpServer.address().port;
    fixtureOrigins.add(origin);
  });
  server.httpServer.once('close', () => fixtureOrigins.delete(origin));
  return server;
}
