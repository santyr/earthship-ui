import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('offline icon package boundary', () => {
  it('uses the supported offline subpackage instead of a brittle dist subpath', async () => {
    const source = await readFile('src/lib/ui/OhIcon.svelte', 'utf8');

    expect(source).toContain("from '@iconify/svelte/offline'");
    expect(source).not.toContain('@iconify/svelte/dist/OfflineIcon.svelte');
  });
});
