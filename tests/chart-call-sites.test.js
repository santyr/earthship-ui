import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';

describe('Energy chart containment', () => {
  it('lets both inline charts fill bounded flex parents instead of forcing pixel heights', async () => {
    const source = await readFile('src/screens/Energy.svelte', 'utf8');
    expect(source).not.toMatch(/<HistoryChart[^>]*\bheight=/s);
    expect(source).toMatch(/\.hero-chart\s*\{[^}]*min-height:\s*0/s);
    expect(source).toMatch(/\.pv-chart\s*\{[^}]*min-height:\s*0/s);
    expect(source).toMatch(/\.hero-chart\s*\{[^}]*overflow:\s*hidden/s);
    expect(source).toMatch(/\.pv-chart\s*\{[^}]*overflow:\s*hidden/s);
  });

  it('uses a period-neutral battery title because the picker controls the range', async () => {
    const source = await readFile('src/screens/Energy.svelte', 'utf8');
    expect(source).not.toContain("Battery — 24h + tonight's forecast");
    expect(source).toContain("Battery history + tonight's forecast");
  });
});
