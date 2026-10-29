// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '../../node_modules/svelte/src/index-client.js'
));

vi.mock('../../src/lib/charts/loadEcharts.js', () => ({ getEcharts: async () => ({ init: () => ({ setOption() {}, resize() {}, dispose() {} }) }) }));
vi.mock('../../src/lib/ui/observeElementSize.js', () => ({ observeElementSize: () => () => {} }));
vi.mock('../../src/lib/energy/forecastState.js', async () => {
  const { readable } = await import('svelte/store');
  return { energyForecastRaw: readable(null), energyForecastClock: readable(Date.now()) };
});
import Home from '../../src/screens/Home.svelte';
import { clientReady, items } from '../../src/lib/openhab/store.js';
import { tick } from 'svelte';
import StatTile from '../../src/lib/ui/StatTile.svelte';
import Tile from '../../src/lib/ui/Tile.svelte';
import { iconCollectionsReady } from '../../src/lib/ui/OhIcon.svelte';

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

  it('owns optional value/footer size variables on the StatTile root', async () => {
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
    await iconCollectionsReady;
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


describe('Home energy content fitting', () => {
  let records, frames, nextFrame;
  beforeEach(() => {
    vi.useFakeTimers();
    clientReady.set(false);
    records = []; frames = new Map(); nextFrame = 0;
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback) { this.callback = callback; this.nodes = []; this.disconnect = vi.fn(); records.push(this); }
      observe(node) { this.nodes.push(node); }
    });
    vi.stubGlobal('requestAnimationFrame', vi.fn(callback => { frames.set(++nextFrame, callback); return nextFrame; }));
    vi.stubGlobal('cancelAnimationFrame', vi.fn(id => frames.delete(id)));
  });
  afterEach(() => { cleanup(); clientReady.set(false); items.set({}); vi.unstubAllGlobals(); vi.useRealTimers(); });
  const flushFrames = () => { const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn(0)); };
  function measuredHome() {
    const view = render(Home);
    const node = view.container.querySelector('.powerflow-metrics');
    const line = view.container.querySelector('.pf-energy-line');
    let available = 300, natural = 600;
    Object.defineProperty(node, 'clientWidth', { get: () => available });
    const measure = vi.spyOn(line, 'getBoundingClientRect').mockImplementation(() => ({ width: natural * (parseFloat(line.style.fontSize || '12') / 12) + 1 }));
    return { ...view, node, line, measure, observer: records.find(r => r.nodes.includes(node)), available: n => { available = n; }, natural: n => { natural = n; } };
  }
  it('coalesces resize bursts, fits measured text, and grows for shorter current values', async () => {
    const view = measuredHome();
    flushFrames();
    const fitted = parseFloat(view.line.style.fontSize);
    expect(fitted).toBeLessThan(12);
    expect(view.measure().width).toBeLessThanOrEqual(300);
    expect(600 * ((fitted + 0.1) / 12) + 1).toBeGreaterThan(300);
    view.measure.mockClear();
    requestAnimationFrame.mockClear();
    view.available(400);
    for (let i = 0; i < 8; i += 1) { view.observer.callback(); window.dispatchEvent(new Event('resize')); }
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
    flushFrames();
    expect(view.measure.mock.calls.length).toBeLessThanOrEqual(3);
    view.natural(240);
    items.set({ MPPT60_PV_Power: '3' });
    await tick();
    flushFrames();
    expect(parseFloat(view.line.style.fontSize)).toBe(12);
  });
  it('disconnects observation, cancels pending frames and ignores late teardown callbacks', () => {
    const view = measuredHome();
    const lateFrame = [...frames.values()][0];
    view.unmount();
    expect(view.observer.disconnect).toHaveBeenCalledOnce();
    expect(cancelAnimationFrame).toHaveBeenCalled();
    requestAnimationFrame.mockClear();
    lateFrame(); view.observer.callback(); window.dispatchEvent(new Event('resize'));
    expect(requestAnimationFrame).not.toHaveBeenCalled();
    expect(view.measure).not.toHaveBeenCalled();
  });
  it('fits on window resize without ResizeObserver or requestAnimationFrame', () => {
    vi.stubGlobal('ResizeObserver', undefined);
    vi.stubGlobal('requestAnimationFrame', undefined);
    const view = measuredHome();
    window.dispatchEvent(new Event('resize'));
    expect(view.measure().width).toBeLessThanOrEqual(300);
    view.unmount(); view.measure.mockClear();
    window.dispatchEvent(new Event('resize'));
    expect(view.measure).not.toHaveBeenCalled();
  });
});
