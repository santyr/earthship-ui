// @vitest-environment jsdom
import { cleanup, render } from '@testing-library/svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  `../../node_modules/svelte/src/index-client.js`
));

import ThermalLoop from '../../src/lib/ui/ThermalLoop.svelte';

afterEach(cleanup);

describe('ThermalLoop north-to-outdoor layout', () => {
  it('orders all four live temperatures and points outward loss toward Outdoor', () => {
    const { container } = render(ThermalLoop, {
      mass: 80,
      room: 70,
      wall: 60,
      outdoor: 50,
    });

    expect([...container.querySelectorAll('.zone-label')].map((node) => node.textContent))
      .toEqual(['North Mass', 'Room Air', 'South Wall', 'Outdoor']);

    const arrows = [...container.querySelectorAll('.loop-svg > line')];
    expect(arrows).toHaveLength(3);
    expect([arrows[0].getAttribute('x1'), arrows[0].getAttribute('x2')])
      .toEqual(['158', '218']);
    expect(arrows[0].getAttribute('marker-end')).toBe('url(#tl-head-amber)');
    expect([arrows[1].getAttribute('x1'), arrows[1].getAttribute('x2')])
      .toEqual(['368', '428']);
    expect(arrows[1].getAttribute('marker-end')).toBe('url(#tl-head-blue)');
    expect([arrows[2].getAttribute('x1'), arrows[2].getAttribute('x2')])
      .toEqual(['578', '638']);
    expect(arrows[2].getAttribute('marker-end')).toBe('url(#tl-head-blue)');
  });

  it('reverses all three arrows when room, wall, and Outdoor are progressively warmer', () => {
    const { container } = render(ThermalLoop, {
      mass: 60,
      room: 70,
      wall: 80,
      outdoor: 90,
    });
    const arrows = [...container.querySelectorAll('.loop-svg > line')];

    expect([arrows[0].getAttribute('x1'), arrows[0].getAttribute('x2')])
      .toEqual(['218', '158']);
    expect(arrows[0].getAttribute('marker-end')).toBe('url(#tl-head-blue)');
    expect([arrows[1].getAttribute('x1'), arrows[1].getAttribute('x2')])
      .toEqual(['428', '368']);
    expect(arrows[1].getAttribute('marker-end')).toBe('url(#tl-head-amber)');
    expect([arrows[2].getAttribute('x1'), arrows[2].getAttribute('x2')])
      .toEqual(['638', '578']);
    expect(arrows[2].getAttribute('marker-end')).toBe('url(#tl-head-amber)');
  });
});
