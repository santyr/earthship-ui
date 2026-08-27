// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '../../node_modules/svelte/src/index-client.js'
));

import Arc from '../../src/lib/ui/Arc.svelte';

const arcSource = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../../src/lib/ui/Arc.svelte'),
  'utf8',
);


afterEach(cleanup);

describe('Arc truthful unavailable state', () => {
  it('keeps a 1.8rem default while accepting a caller-specific value size', () => {
    expect(arcSource).toMatch(
      /\.arc-value\s*\{[^}]*font-size:\s*var\(--arc-value-size,\s*1\.8rem\);/s
    );
  });
  it('renders unavailable as a dash with no value arc', () => {
    const { container } = render(Arc, { value: null });

    expect(screen.getByText('—')).toBeInTheDocument();
    expect(container.querySelector('[data-arc-value]')).toBeNull();
  });

  it('keeps a real numeric zero distinct from unavailable', () => {
    const { container } = render(Arc, { value: 0 });

    expect(screen.getByText('0%')).toBeInTheDocument();
    expect(container.querySelector('[data-arc-value]')).not.toBeNull();
  });
});
