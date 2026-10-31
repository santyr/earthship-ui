import { defineConfig } from '@playwright/test';

// Bound native compiler pools before test modules load Vite/Tailwind.
// These limits apply only to disposable tests, within the existing job cap.
for (const name of ['RAYON_NUM_THREADS', 'ROLLDOWN_WORKER_THREADS', 'TOKIO_WORKER_THREADS', 'UV_THREADPOOL_SIZE']) {
  process.env[name] ??= '1';
}
process.env.ROLLDOWN_MAX_BLOCKING_THREADS ??= '2';

export default defineConfig({
  testDir: 'tests/e2e',
  globalSetup: './tests/e2e/build-fixtures.js',
  fullyParallel: false,
  workers: 1,
  use: {
    serviceWorkers: 'block',
    launchOptions: { args: [
      '--disable-dev-shm-usage', '--renderer-process-limit=1', '--disable-gpu',
      '--disable-software-rasterizer', '--no-zygote', '--num-raster-threads=1',
    ] },
  },
  projects: [
    { name: 'fixtures', testIgnore: '**/sensors-layout.spec.js' },
    { name: 'sensors', testMatch: '**/sensors-layout.spec.js' },
  ],
});
