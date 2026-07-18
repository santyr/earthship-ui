import fs from 'node:fs';
import { describe, expect, it } from 'vitest';
import {
  DIRECT_COMMAND_ITEMS,
  UNSAFE_DIRECT_COMMAND_ITEMS,
} from '../src/lib/controls/catalog.js';

describe('static control safety boundary', () => {
  it('never permits an actuator or owner-managed provider item as a direct target', () => {
    const overlap = DIRECT_COMMAND_ITEMS.filter((item) =>
      UNSAFE_DIRECT_COMMAND_ITEMS.includes(item));
    expect(overlap).toEqual([]);
  });

  it('does not embed unsafe item names in a sendCommand call', () => {
    const sources = [
      'src/screens/Controls.svelte',
      'src/lib/ui/Toggle.svelte',
    ].map((path) => fs.readFileSync(path, 'utf8')).join('\n');

    for (const item of UNSAFE_DIRECT_COMMAND_ITEMS) {
      expect(sources).not.toMatch(
        new RegExp(`sendCommand\\s*\\(\\s*['"]${item}['"]`),
      );
    }
  });
});
