// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '/home/sat/earthship-ui/node_modules/svelte/src/index-client.js'
));

import StatTile from '../../src/lib/ui/StatTile.svelte';
import Tile from '../../src/lib/ui/Tile.svelte';

afterEach(cleanup);

describe('Home tile primitive APIs', () => {
  it('hides a visual title while preserving an explicit accessible group name', () => {
    const { container } = render(Tile, {
      props: { label: 'Outdoor', hideLabel: true, fill: true, clip: true, centerBody: true },
    });

    const tile = screen.getByRole('group', { name: 'Outdoor' });
    expect(tile).toHaveAttribute('data-tile-label-hidden');
    expect(tile).toHaveAttribute('data-tile-fill');
    expect(tile).toHaveAttribute('data-tile-clip');
    expect(tile).toHaveAttribute('data-tile-center-body');
    expect(container.querySelector('.tile-body.centered')).toBeInTheDocument();
    expect(container.querySelector('.tile-label')).toBeNull();
    expect(screen.queryByText('Outdoor')).toBeNull();
  });

  it('owns optional value/footer size variables on the StatTile root', () => {
    const { container } = render(StatTile, {
      props: {
        label: 'Rain',
        value: '0.42″ / 733 gal',
        footer: 'Week 1.72″ / 3,000 gal',
        iconName: 'iconify:mdi:weather-rainy',
        iconColor: '#3b82f6',
        valueSize: '1rem',
        footerSize: '0.72rem',
        stackValue: true,
        centerContent: true,
        hideLabel: true,
        fill: true,
        clip: true,
      },
    });

    expect(screen.getByRole('group', { name: 'Rain' })).toBeInTheDocument();
    const root = container.querySelector('[data-stat-tile]');
    expect(root.style.getPropertyValue('--stat-value-size')).toBe('1rem');
    expect(root.style.getPropertyValue('--stat-footer-size')).toBe('0.72rem');
    expect(container.querySelector('[data-stat-content-centered]')).toBeInTheDocument();
    expect(root).toHaveAttribute('data-tile-center-body');
    expect(container.querySelector('.stat.stacked')).toBeInTheDocument();
    expect(container.querySelector('.state-icon svg')).toBeInTheDocument();
    expect(container.querySelector('.state-icon')).toHaveStyle({ color: '#3b82f6' });
    expect(container.querySelector('.value')).toHaveTextContent('0.42″ / 733 gal');
    expect(container.querySelector('.footer')).toHaveTextContent('Week 1.72″ / 3,000 gal');
  });

  it('leaves shared StatTile defaults unchanged when no override is provided', () => {
    const { container } = render(StatTile, {
      props: { label: 'Weather rain', value: '1.2', footer: 'last 24h' },
    });
    const root = container.querySelector('[data-stat-tile]');

    expect(root.style.getPropertyValue('--stat-value-size')).toBe('');
    expect(root.style.getPropertyValue('--stat-footer-size')).toBe('');
    expect(root).not.toHaveAttribute('data-tile-center-body');
    expect(container.querySelector('.tile-label')).toHaveTextContent('Weather rain');
  });
});
