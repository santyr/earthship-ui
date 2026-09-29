import { expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../../openhab/file-config/items/sky-condition-icon.items', import.meta.url), 'utf8');
const ownership = JSON.parse(readFileSync(new URL('../../openhab/file-config/ownership.json', import.meta.url), 'utf8'));

it('declares the exact verified file-owned SkyConditionIcon Item', () => {
  const definitions = source.split('\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('//'));
  expect(definitions).toEqual([
    'String SkyConditionIcon "Sky Condition Icon" <sun_clouds> ["Status"]',
  ]);
  const matching = ownership.resources.filter((resource) => resource.kind === 'item' && resource.id === 'SkyConditionIcon');
  expect(matching).toHaveLength(1);
  expect(matching[0]).toMatchObject({ provider: 'file', migration: 'verified',
    source: 'items/sky-condition-icon.items', destination: '/etc/openhab/items/sky-condition-icon.items',
    state_writer: 'sky-condition-calculator' });
});
