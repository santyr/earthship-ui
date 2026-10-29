import { test as base, expect } from '@playwright/test';
import { fixtureOrigins } from './fixture-server.js';

// These suites own disposable Vite servers only. Never inherit a household
// proxy target or credential from the machine running the fixtures.
process.env.OPENHAB_PROXY_TARGET = 'http://127.0.0.1:9';
delete process.env.OPENHAB_TOKEN;

export const test = base.extend({
  fixtureSafety: [async ({ browser, context }, use, testInfo) => {
    const errors = [];
    const violations = [];
    const previewAllowed = testInfo.file.endsWith('/shades-layout.spec.js');
    async function guard(target) {
      const watch = page => page.on('pageerror', error => errors.push(error.message));
      target.pages().forEach(watch);
      target.on('page', watch);
      target.on('request', request => {
        const url = new URL(request.url());
        if (!['GET', 'HEAD'].includes(request.method())
          && !(previewAllowed && request.method() === 'POST' && url.pathname === '/api/shades-preview')) {
          violations.push(`${request.method()} ${url.pathname}`);
        }
      });
      await target.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url());
        if (!fixtureOrigins.has(url.origin)) {
          violations.push(`outside fixture origin: ${url.origin}`);
          return route.abort('blockedbyclient');
        }
        if (!['GET', 'HEAD'].includes(request.method())
          && !(previewAllowed && request.method() === 'POST' && url.pathname === '/api/shades-preview')) {
          return route.abort('blockedbyclient');
        }
        if (previewAllowed && /^\/api\/shades-preview(?:\/events)?$/.test(url.pathname)) return route.continue();
        // Retained runtime advice overlays receive explicit unavailable documents;
        // these are read-only fixtures, never private cache or household data.
        if (['/api/household-advice','/api/household-advice-feedback','/api/household-advice-state','/api/household-advice-context','/api/household-shade-observations'].includes(url.pathname)) {
          return route.fulfill({ status: 200, json: { status: 'unavailable' } });
        }
        // Individual page routes take precedence. Any unstubbed report/REST
        // request gets explicit unavailability, never private cache/live data.
        if (/^\/(?:fixture-openhab\/)?rest(?:\/|$)/.test(url.pathname) || url.pathname.startsWith('/api/')) {
          return route.fulfill({ status: 503, json: { status: 'unavailable' } });
        }
        return route.continue();
      });
    }
    await guard(context);
    const original = browser.newContext;
    browser.newContext = async function(options) {
      const created = await original.call(this, { ...options, serviceWorkers: 'block' });
      await guard(created);
      return created;
    };
    try { await use(); }
    finally {
      browser.newContext = original;
      expect(errors, 'fixture page errors').toEqual([]);
      expect(violations, 'unexpected fixture network/mutation attempts').toEqual([]);
    }
  }, { auto: true }],
});
export { expect };
