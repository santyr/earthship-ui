import { defineConfig } from 'vite'
import { configDefaults } from 'vitest/config'
import { svelte } from '@sveltejs/vite-plugin-svelte'
import {
  isAllowedProxyRequest,
  isThingsGetPath,
  openhabProxyAuthorization,
  sanitizeThingsResponse,
} from './src/lib/openhab/proxyPolicy.js'
import { validateControlCatalog } from './src/lib/controls/catalog.js'

// https://vite.dev/config/
// Same-origin dev proxy: the browser calls relative /rest paths (config
// openhabUrl = ''), and Vite forwards them to openHAB — avoiding the CORS
// wall a direct cross-origin browser->openHAB call hits. The household server
// uses this same Vite process and proxy. SSE (/rest/events) is forwarded too.
const OPENHAB = process.env.OPENHAB_PROXY_TARGET || 'http://ogsatoth:8080'

function decodedPath(rawUrl) {
  try {
    return decodeURIComponent(new URL(rawUrl, 'http://earthship-ui.local').pathname)
  } catch {
    return null
  }
}

function openhabProxyGuard(releaseMode, upstream, authorization) {
  return {
    name: 'earthship-openhab-proxy-guard',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith('/rest')) return next()
        if (!isAllowedProxyRequest(req.method, req.url, releaseMode)) {
          res.statusCode = 403
          res.setHeader('Content-Type', 'application/json; charset=utf-8')
          res.end(JSON.stringify({ error: 'OpenHAB request blocked by household proxy policy' }))
          return
        }

        // GET /rest/things* is never proxied raw: fetch upstream server-side
        // and return only the {UID,label,statusInfo} projection so binding
        // configuration (plaintext device credentials) never reaches a client.
        const path = decodedPath(req.url)
        if (String(req.method).toUpperCase() === 'GET' && path && isThingsGetPath(path)) {
          const headers = authorization ? { Authorization: authorization } : {}
          fetch(`${upstream}${req.url}`, { headers })
            .then(async (upstreamResponse) => {
              if (!upstreamResponse.ok) throw new Error(`upstream ${upstreamResponse.status}`)
              const sanitized = sanitizeThingsResponse(await upstreamResponse.json())
              res.statusCode = 200
              res.setHeader('Content-Type', 'application/json; charset=utf-8')
              res.end(JSON.stringify(sanitized))
            })
            .catch(() => {
              res.statusCode = 502
              res.setHeader('Content-Type', 'application/json; charset=utf-8')
              res.end(JSON.stringify({ error: 'OpenHAB things fetch failed' }))
            })
          return
        }

        return next()
      })
    },
  }
}

export default defineConfig(() => {
  const releaseMode = process.env.RELEASE_MODE || 'maintenance'
  const proxyToken = process.env.OPENHAB_TOKEN?.trim()
  const proxyAuthorization = proxyToken ? openhabProxyAuthorization(proxyToken) : null
  const catalogErrors = validateControlCatalog()
  if (catalogErrors.length) {
    throw new Error(`Control catalog invalid: ${catalogErrors.join('; ')}`)
  }
  return {
    plugins: [openhabProxyGuard(releaseMode, OPENHAB, proxyAuthorization), svelte()],
    define: {
      __EARTHSHIP_RELEASE_MODE__: JSON.stringify(releaseMode),
    },
    test: {
      exclude: [...configDefaults.exclude, 'tests/e2e/**', '**/.worktrees/**'],
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
