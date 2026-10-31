import { describe, expect, it } from 'vitest';

describe('Playwright repository fixture isolation', () => {
  it('runs repository-managed Vite servers in one worker', async () => {
    const config = await import('../playwright.config.js')
      .then((module) => module.default)
      .catch((error) => {
        if (error?.code === 'ERR_MODULE_NOT_FOUND') return null;
        throw error;
      });

    expect(config).toMatchObject({
      fullyParallel: false,
      workers: 1,
    });
  });
});

describe('supported browser entrypoints', () => {
  it('separates fixtures and sensors and blocks service workers', async () => {
    const { default: config } = await import('../playwright.config.js');
    expect(config.use.serviceWorkers).toBe('block');
    expect(config.projects).toEqual([
      { name: 'fixtures', testIgnore: '**/sensors-layout.spec.js' },
      { name: 'sensors', testMatch: '**/sensors-layout.spec.js' },
    ]);
  });
});
