import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const README_URL = new URL('../README.md', import.meta.url);
const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const ROUTES = [
  ['home', 'Home'],
  ['energy', 'Energy'],
  ['weather', 'Weather'],
  ['earthship', 'Earthship'],
  ['controls', 'Controls'],
];

function pngDimensions(buffer) {
  expect(buffer.subarray(0, 8).equals(PNG_SIGNATURE)).toBe(true);
  expect(buffer.subarray(12, 16).toString('ascii')).toBe('IHDR');
  return {
    width: buffer.readUInt32BE(16),
    height: buffer.readUInt32BE(20),
  };
}

describe('README documentation', () => {
  const readme = readFileSync(README_URL, 'utf8');

  it('describes the implemented five-screen console', () => {
    expect(readme).toContain('**Status:** implemented and running');
    expect(readme).toContain('## Screenshots');
  });

  it.each(ROUTES)('links the %s screenshot and preserves M9 dimensions', (route, title) => {
    const relativePath = `docs/screenshots/${route}.png`;
    expect(readme).toContain(`[![${title} page](${relativePath})](${relativePath})`);

    const image = readFileSync(new URL(`../${relativePath}`, import.meta.url));
    expect(pngDimensions(image)).toEqual({ width: 1340, height: 800 });
  });

  it('documents the supported service recovery workflow', () => {
    expect(readme).toContain('## Service operations');
    expect(readme).toContain('systemctl --user daemon-reload');
    expect(readme).toContain('systemctl --user restart earthship-ui.service');
    expect(readme).toContain('systemctl --user status earthship-ui.service --no-pager -l');
    expect(readme).toContain('journalctl --user -u earthship-ui.service -n 100 --no-pager');
    expect(readme).toContain('http://127.0.0.1:5190/src/App.svelte');
    expect(readme).toContain('branch switches, fast-forwards, or other tree-wide checkout changes');
  });
});
