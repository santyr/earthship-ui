import { createServer as createHttpServer } from 'node:http';
import { readFile, realpath, stat } from 'node:fs/promises';
import { resolve, sep, extname } from 'node:path';
import { shadePreviewPlugin } from '../../src/lib/shades/previewServer.js';

const types = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png', '.woff2':'font/woff2', '.ico':'image/x-icon' };

// Full production bundle, disposable in-memory preview only. No production
// server plugins, credentials, model readers, OpenHAB or device transports.
export async function createBuiltFixtureServer(directory, origins) {
  const root = await realpath(directory);
  const sockets = new Set();
  const middleware = [];
  const server = { resolvedUrls: { local: [] }, middlewares: {
    use(mount, handler) {
      if (typeof mount === 'function') { handler = mount; mount = ''; }
      middleware.push({ mount, handler });
    },
  } };
  server.middlewares.use((request, response, next) => {
    const path = new URL(request.url, 'http://fixture.invalid').pathname;
    if (path === '/config.json') {
      response.setHeader('Content-Type','application/json');
      response.end(JSON.stringify({openhabUrl:'',apiToken:'',staleBannerSeconds:90}));
    } else if (/^\/api\/shades-preview(?:\/events)?$/.test(path)) next();
    else if (/^\/(?:fixture-openhab\/)?rest(?:\/|$)/.test(path) || path.startsWith('/api/')) {
      response.writeHead(503,{'Content-Type':'application/json'}).end('{"status":"unavailable"}');
    } else next();
  });
  server.httpServer = createHttpServer((request, response) => {
    let index = 0;
    const next = () => {
      const row = middleware[index++];
      if (!row) { serve(request,response).catch(() => response.writeHead(404).end()); return; }
      const path = new URL(request.url,'http://fixture.invalid').pathname;
      if (row.mount && path !== row.mount && !path.startsWith(row.mount+'/')) { next(); return; }
      const original = request.url;
      if (row.mount) request.url = request.url.slice(row.mount.length) || '/';
      row.handler(request,response,() => { request.url=original; next(); });
    };
    next();
  });
  shadePreviewPlugin().configureServer(server);
  async function serve(request,response) {
    if (!['GET','HEAD'].includes(request.method)) { response.writeHead(405).end(); return; }
    const path = decodeURIComponent(new URL(request.url,'http://fixture.invalid').pathname);
    const target = await realpath(resolve(root,'.'+(path==='/'?'/index.html':path)));
    if (!target.startsWith(root+sep) || !(await stat(target)).isFile()) { response.writeHead(404).end(); return; }
    response.writeHead(200,{'Content-Type':types[extname(target)]||'application/octet-stream','Cache-Control':'no-store'});
    response.end(request.method==='HEAD'?undefined:await readFile(target));
  }
  server.httpServer.on('connection',socket=>{sockets.add(socket);socket.once('close',()=>sockets.delete(socket));});
  let origin, closing;
  server.listen = () => new Promise((resolve,reject)=>{
    server.httpServer.once('error',reject);
    server.httpServer.listen(0,'127.0.0.1',()=>{
      origin='http://127.0.0.1:'+server.httpServer.address().port;
      server.resolvedUrls.local=[origin+'/'];origins.add(origin);resolve(server);
    });
  });
  server.close = () => {
    if (!closing) {
      for (const socket of sockets) socket.destroy();
      closing=new Promise((resolve,reject)=>server.httpServer.close(error=>{origins.delete(origin);error?reject(error):resolve();}));
    }
    return closing;
  };
  return server;
}
