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
    expect(compass).toMatch(/\{#if presentation\.hasHeading\}[\s\S]*class="compass-needle"/);
    expect(compass).toMatch(/\{#if presentation\.hasHeading\}[\s\S]*class="compass-hub"/);
  });

  it('delegates direction, calm and accessibility text to the pure adapter', () => {
    expect(compass).toContain("import { compassPresentation } from './compassPresentation.js'");
    expect(compass).toMatch(/const\s+presentation\s*=\s*\$derived\(compassPresentation\(degrees,\s*speed\)\)/);
    expect(compass).toMatch(/aria-label=\{presentation\.ariaLabel\}/);
    expect(compass).toContain('{presentation.headingText}');
  });

  it('renders a stronger but restrained instrument hierarchy', () => {
    expect(compass).toContain('class="compass-heading"');
    expect(compass).toContain('points="50,23 43.5,53 50,48 56.5,53"');
    expect(compass).toMatch(/\.dir-label\s*\{[^}]*font-size:\s*13px;[^}]*fill:\s*#d7dee6;/s);
    expect(compass).toMatch(/\.compass-speed\s*\{[^}]*font-size:\s*1\.8rem;/s);
  });
});
