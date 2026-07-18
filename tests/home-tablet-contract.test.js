import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

const home = read('src/screens/Home.svelte');
const header = read('src/lib/ui/Header.svelte');
const compass = read('src/lib/ui/CompassRose.svelte');
const sparkline = read('src/lib/ui/Sparkline.svelte');

describe('Home tablet presentation contract', () => {
  it('uses the header ticker slot for a bounded accessible alert summary', () => {
    expect(header).not.toMatch(/BtcTicker|BTC_USD|Bitcoin/i);
    expect(header).toMatch(/class="alerts"/);
    expect(header).toMatch(/role="status"/);
    expect(header).toContain('No active alerts');
    expect(header).toMatch(/white-space:\s*nowrap/);
    expect(header).toMatch(/text-overflow:\s*ellipsis/);
  });

  it('keeps the Bitcoin summary and lazy modal activation without inline history', () => {
    expect(home).toContain('btcPriceText');
    expect(home).toContain('btcPctText');
    expect(home).toMatch(/openBitcoinChart/);
    expect(home).not.toMatch(/btcSpark|refreshBtcSpark/);
    expect(home).not.toMatch(/class="btc-spark"/);
    expect(home).toMatch(/class="cell bitcoin-cell clickable"/);
  });

  it('pins the requested distance-readable Home typography', () => {
    expect(home).toMatch(/\.big-temp\s*\{[^}]*color:\s*#fff/is);
    expect(home).toMatch(/\.indoor-temp\s*\{[^}]*font-size:\s*(?:2\.[4-9]|[3-9])rem/is);
    expect(home).toMatch(/\.indoor-temp\s*\{[^}]*color:\s*#fff/is);
    expect(home).toMatch(/\.rain-cell\s+:global\(\.value\)\s*\{[^}]*font-size:\s*2\.15rem/is);
    expect(home).toMatch(/\.rain-cell\s+:global\(\.footer\)\s*\{[^}]*white-space:\s*nowrap/is);
    expect(home).toContain("parts.push(`evt ");
    expect(home).toContain("parts.join('·')");
    expect(home).toMatch(/\.sm-row\s*\{[^}]*font-size:\s*0\.(?:8[2-9]|9)\d*rem/is);
  });

  it('lets the compass consume its measured parent instead of a fixed cap', () => {
    expect(home).not.toMatch(/max-width:\s*4\.6rem/);
    expect(compass).toContain('ResizeObserver');
    expect(compass).toMatch(/Math\.min\(width,\s*height\)/);
    expect(compass).toMatch(/class="compass-square"/);
  });

  it('resizes and clips sparkline paint to its settled card box', () => {
    expect(sparkline).toContain('ResizeObserver');
    expect(sparkline).toMatch(/chart\?\.resize\(\{\s*width,\s*height\s*\}\)/);
    expect(sparkline).toMatch(/overflow:\s*hidden/);
    expect(home).toMatch(/\.outdoor-spark\s*\{[^}]*overflow:\s*hidden/is);
    expect(home).toMatch(/\.outdoor-cell \.tile\)[^{]*\{[^}]*overflow:\s*hidden/is);
  });
});
