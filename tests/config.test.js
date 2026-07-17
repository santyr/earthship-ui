import { describe, it, expect, vi } from 'vitest';
import { parseConfig } from '../src/lib/config.js';
describe('parseConfig', () => {
  it('accepts a valid config', () => {
    const c = parseConfig({ openhabUrl: 'http://x:8080', apiToken: 't', staleBannerSeconds: 90 });
    expect(c.openhabUrl).toBe('http://x:8080');
    expect(c.staleBannerSeconds).toBe(90);
  });
  it('defaults staleBannerSeconds to 90', () => {
    expect(parseConfig({ openhabUrl: 'http://x', apiToken: 't' }).staleBannerSeconds).toBe(90);
  });
  it('throws when openhabUrl missing', () => {
    expect(() => parseConfig({ apiToken: 't' })).toThrow(/openhabUrl/);
  });
});
