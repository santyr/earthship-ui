// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '/home/sat/earthship-ui/node_modules/svelte/src/index-client.js'
));

vi.mock('../../src/lib/openhab/index.js', async () => {
  const { writable } = await import('svelte/store');
  return {
    items: writable({}),
    connection: writable('offline'),
    num: (value) => {
      const parsed = Number.parseFloat(value);
      return Number.isFinite(parsed) ? parsed : null;
    },
  };
});

import { connection } from '../../src/lib/openhab/index.js';
import Shell from '../../src/lib/ui/Shell.svelte';

describe('bounded target shell', () => {
  beforeEach(() => connection.set('offline'));
  afterEach(cleanup);

  it('uses the header alert as the only connection text and marks the current route', () => {
    const { container } = render(Shell);

    expect(container.querySelector('.stale-banner')).toBeNull();
    expect(screen.getAllByText(/openHAB offline/i)).toHaveLength(2);
    for (const home of screen.getAllByRole('button', { name: /Home/i })) {
      expect(home).toHaveAttribute('aria-current', 'page');
    }
    expect(container.querySelector('.shell')).toHaveAttribute('data-bounded-shell');
  });
});
