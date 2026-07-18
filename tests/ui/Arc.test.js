// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '/home/sat/earthship-ui/node_modules/svelte/src/index-client.js'
));

import Arc from '../../src/lib/ui/Arc.svelte';

afterEach(cleanup);

describe('Arc truthful unavailable state', () => {
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
