import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const compass = readFileSync(new URL('../../src/lib/ui/CompassRose.svelte', import.meta.url), 'utf8');

describe('CompassRose semantic direction', () => {
  it('accepts a caller-provided accent for the needle and hub', () => {
    expect(compass).toMatch(/let\s*\{[^}]*accent\s*=\s*['"]#22c55e['"]/s);
    expect(compass).toMatch(/class="compass-needle"[^>]*fill=\{accent\}/s);
    expect(compass).toMatch(/class="compass-hub"[^>]*fill=\{accent\}/s);
  });

  it('does not imply North when direction is unavailable', () => {
    expect(compass).toMatch(/const\s+hasHeading\s*=\s*\$derived/);
    expect(compass).toMatch(/\{#if hasHeading\}[\s\S]*class="compass-needle"/);
    expect(compass).toMatch(/\{#if hasHeading\}[\s\S]*class="compass-hub"/);
  });

  it('exposes the current heading and speed to assistive technology', () => {
    expect(compass).toMatch(/const\s+compassLabel\s*=\s*\$derived/);
    expect(compass).toMatch(/<svg[^>]*role="img"[^>]*aria-label=\{compassLabel\}/s);
    expect(compass).toContain('Wind direction unavailable');
  });

  it('keeps bold cardinal labels clear of the shortened needle', () => {
    expect(compass).toMatch(
      /\.dir-label\s*\{[^}]*font-size:\s*12px;[^}]*font-weight:\s*800;/s
    );
    expect(compass).toContain('points="50,22 45,52 50,46 55,52"');
  });
});
