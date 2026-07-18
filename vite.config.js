import { defineConfig } from 'vite'
import { configDefaults } from 'vitest/config'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vite.dev/config/
// Same-origin dev proxy: the browser calls relative /rest paths (config
// openhabUrl = ''), and Vite forwards them to openHAB — avoiding the CORS
// wall a direct cross-origin browser->openHAB call hits. The household server
// uses this same Vite process and proxy. SSE (/rest/events) is forwarded too.
const OPENHAB = process.env.OPENHAB_PROXY_TARGET || 'http://ogsatoth:8080'
export default defineConfig(() => ({
  plugins: [svelte()],
  define: {
    __EARTHSHIP_RELEASE_MODE__: JSON.stringify(process.env.RELEASE_MODE || 'maintenance'),
  },
  test: {
    exclude: [...configDefaults.exclude, 'tests/e2e/**'],
  },
  server: {
    proxy: {
      '/rest': { target: OPENHAB, changeOrigin: true },
    },
  },
}))
