import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// https://vite.dev/config/
// Same-origin dev proxy: the browser calls relative /rest paths (config
// openhabUrl = ''), and Vite forwards them to openHAB — avoiding the CORS
// wall a direct cross-origin browser->openHAB call hits. In production nginx
// does the same proxy. SSE (/rest/events) is forwarded too.
const OPENHAB = process.env.OPENHAB_PROXY_TARGET || 'http://ogsatoth:8080'
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/rest': { target: OPENHAB, changeOrigin: true },
    },
  },
})
