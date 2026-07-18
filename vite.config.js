import { defineConfig } from 'vite'
import { configDefaults } from 'vitest/config'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import {
  isAllowedProxyRequest,
  openhabProxyAuthorization,
} from './src/lib/openhab/proxyPolicy.js'

// https://vite.dev/config/
// Same-origin dev proxy: the browser calls relative /rest paths (config
// openhabUrl = ''), and Vite forwards them to openHAB — avoiding the CORS
// wall a direct cross-origin browser->openHAB call hits. The household server
// uses this same Vite process and proxy. SSE (/rest/events) is forwarded too.
const OPENHAB = process.env.OPENHAB_PROXY_TARGET || 'http://ogsatoth:8080'

function openhabProxyGuard(releaseMode) {
  return {
    name: 'earthship-openhab-proxy-guard',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith('/rest')) return next()
        if (isAllowedProxyRequest(req.method, req.url, releaseMode)) return next()

        res.statusCode = 403
        res.setHeader('Content-Type', 'application/json; charset=utf-8')
        res.end(JSON.stringify({ error: 'OpenHAB request blocked by household proxy policy' }))
      })
    },
  }
}

export default defineConfig(() => {
  const releaseMode = process.env.RELEASE_MODE || 'maintenance'
  const proxyToken = process.env.OPENHAB_TOKEN?.trim()
  const proxyAuthorization = proxyToken ? openhabProxyAuthorization(proxyToken) : null
  return {
    plugins: [openhabProxyGuard(releaseMode), svelte()],
    define: {
      __EARTHSHIP_RELEASE_MODE__: JSON.stringify(releaseMode),
    },
    test: {
      exclude: [...configDefaults.exclude, 'tests/e2e/**'],
    },
    server: {
      proxy: {
        '/rest': {
          target: OPENHAB,
          changeOrigin: true,
          configure(proxy) {
            proxy.on('proxyReq', (proxyReq) => {
              if (!proxyAuthorization) return
              proxyReq.setHeader('Authorization', proxyAuthorization)
            })
          },
        },
      },
    },
  }
})
