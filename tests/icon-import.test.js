import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';
import { wmoIcon } from '../src/lib/ui/wmo.js';

async function commonIcons() {
  const collections = await Promise.all(['mdi', 'bi'].map(async (prefix) =>
    JSON.parse(await readFile(`src/lib/ui/icons/${prefix}-common.json`, 'utf8'))));
  return new Set(collections.flatMap((collection) =>
    Object.keys(collection.icons).map((name) => `${collection.prefix}:${name}`)));
}

describe('offline icon package boundary', () => {
  it('renders every declared sky-rule and Astro-map icon without loading a full collection', async () => {
    const known = await commonIcons();
    const sources = await Promise.all([
      'openhab/file-config/automation/js/sky-condition-calculator.js',
      'openhab/transform/astro.map',
    ].map((path) => readFile(path, 'utf8')));
    const names = sources.flatMap((source) => [...source.matchAll(/iconify:((?:mdi|bi):[a-z0-9-]+)/g)].map((match) => match[1]));
    expect(names.length).toBeGreaterThan(20);
    expect([...new Set(names)].filter((name) => !known.has(name))).toEqual([]);
  });

  it('keeps day/night forecast conditions and all eight moon phases in the small local subset', async () => {
    const known = await commonIcons();
    const names = new Set();
    for (let day = 1; day <= 32; day += 1) {
      const at = Date.UTC(2026, 0, day);
      for (let code = 0; code <= 100; code += 1) {
        names.add(wmoIcon(code, { isDay: true, at }));
        names.add(wmoIcon(code, { isDay: false, at }));
      }
    }
    expect([...names].filter((name) => name.startsWith('mdi:moon-'))).toHaveLength(8);
    expect([...names].filter((name) => !known.has(name))).toEqual([]);
  });

  it('uses the supported offline subpackage instead of a brittle dist subpath', async () => {
    const source = await readFile('src/lib/ui/OhIcon.svelte', 'utf8');

    expect(source).toContain("from '@iconify/svelte/offline'");
    expect(source).not.toContain('@iconify/svelte/dist/OfflineIcon.svelte');
  });

  it('loads the 4MB icon JSONs as split async chunks, never in the main chunk', async () => {
    const source = await readFile('src/lib/ui/OhIcon.svelte', 'utf8');

    // Static imports would drag ~4.1MB of icon JSON into the entry chunk.
    expect(source).not.toMatch(/^\s*import\s+\w+\s+from\s+'@iconify-json/m);
    expect(source).toContain("import('@iconify-json/mdi/icons.json')");
    expect(source).toContain("import('@iconify-json/bi/icons.json')");
    // Tests (and anything needing determinism) can await the load.
    expect(source).toContain('export const iconCollectionsReady');
  });
});
