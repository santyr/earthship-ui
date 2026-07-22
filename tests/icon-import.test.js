import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('offline icon package boundary', () => {
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
