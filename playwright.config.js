import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: false,
  workers: 1,
  use: { serviceWorkers: 'block' },
  projects: [
    { name: 'fixtures', testIgnore: '**/sensors-layout.spec.js' },
    { name: 'sensors', testMatch: '**/sensors-layout.spec.js' },
  ],
});
