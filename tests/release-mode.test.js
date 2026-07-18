import { afterEach, describe, expect, it, vi } from 'vitest';
import { configDefaults } from 'vitest/config';
import { CONTROL_CATALOG } from '../src/lib/controls/catalog.js';
import {
  RELEASE_MODES,
  isDirectControlAllowed,
  resolveReleaseMode,
} from '../src/lib/releaseMode.js';
import viteConfig from '../vite.config.js';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('release mode safety gate', () => {
  it('recognizes only the three audited server release modes', () => {
    expect(RELEASE_MODES).toEqual(['maintenance', 'safe-compat', 'full']);
  });

  it.each([
    undefined,
    null,
    '',
    'development',
    'dev',
    'unknown',
    'FULL',
  ])('defaults unknown configured mode %s to maintenance', (mode) => {
    expect(resolveReleaseMode(mode)).toBe('maintenance');
  });

  it.each(['maintenance', 'safe-compat', 'full'])('accepts configured server mode %s', (mode) => {
    expect(resolveReleaseMode(mode)).toBe(mode);
  });

  it.each(['safe-compat', 'full'])('honors explicit server mode %s in the Vite serve process', (mode) => {
    expect(resolveReleaseMode(mode)).toBe(mode);
  });

  it('injects explicit safe-compat into the Vite serve command', () => {
    vi.stubEnv('RELEASE_MODE', 'safe-compat');
    const config = viteConfig({ command: 'serve', mode: 'development' });

    expect(JSON.parse(config.define.__EARTHSHIP_RELEASE_MODE__)).toBe('safe-compat');
    expect(isDirectControlAllowed(CONTROL_CATALOG.circadian, 'safe-compat')).toBe(true);
    expect(isDirectControlAllowed(CONTROL_CATALOG.feedOnce, 'safe-compat')).toBe(false);
  });

  it('keeps Playwright specs out of Vitest collection while preserving Vitest defaults', () => {
    const config = viteConfig({ command: 'serve', mode: 'test' });

    expect(config.test.exclude).toEqual(
      expect.arrayContaining([...configDefaults.exclude, 'tests/e2e/**']),
    );
  });

  it('injects maintenance into the Vite serve command when mode is missing', () => {
    vi.stubEnv('RELEASE_MODE', '');
    const config = viteConfig({ command: 'serve', mode: 'development' });

    expect(JSON.parse(config.define.__EARTHSHIP_RELEASE_MODE__)).toBe('maintenance');
  });

  it.each([
    ['maintenance', []],
    ['safe-compat', ['living1', 'living2', 'living3', 'circadian']],
    ['full', ['living1', 'living2', 'living3', 'circadian']],
  ])('permits only currently implemented direct controls in %s', (mode, allowedIds) => {
    const actual = Object.entries(CONTROL_CATALOG)
      .filter(([, control]) => isDirectControlAllowed(control, mode))
      .map(([id]) => id);

    expect(actual).toEqual(allowedIds);
  });

  it('never treats a future request capability as a direct command path', () => {
    for (const id of ['dishwasher', 'shureflo', 'goatCam', 'feedOnce', 'circulation', 'override']) {
      expect(isDirectControlAllowed(CONTROL_CATALOG[id], 'full')).toBe(false);
    }
  });
});
