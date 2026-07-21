// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { readFileSync } from 'node:fs';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { tick } from 'svelte';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '../../node_modules/svelte/src/index-client.js'
));

import GoatFeedingsCard from '../../src/lib/ui/GoatFeedingsCard.svelte';

const source = readFileSync('src/lib/ui/GoatFeedingsCard.svelte', 'utf8');

function installFakeAudioContext() {
  const oscillator = {
    type: '',
    frequency: {
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    },
    connect: vi.fn(),
    start: vi.fn(),
    stop: vi.fn(),
  };
  const gain = {
    gain: {
      setValueAtTime: vi.fn(),
      exponentialRampToValueAtTime: vi.fn(),
    },
    connect: vi.fn(),
  };
  const context = {
    currentTime: 1,
    destination: {},
    resume: vi.fn(() => Promise.resolve()),
    close: vi.fn(() => Promise.resolve()),
    createOscillator: vi.fn(() => oscillator),
    createGain: vi.fn(() => gain),
  };
  Object.defineProperty(window, 'AudioContext', {
    configurable: true,
    value: class {
      constructor() {
        return context;
      }
    },
  });
  return { context, gain, oscillator };
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  delete window.AudioContext;
  delete window.webkitAudioContext;
});

describe('GoatFeedingsCard', () => {
  it('renders a truthful read-only feeding summary with the normal feed icon', () => {
    const { container } = render(GoatFeedingsCard, {
      props: { feedings: '2', motorState: 'OFF' },
    });

    expect(screen.getByRole('group', {
      name: 'Goat feedings: 2 feedings today',
    })).toBeInTheDocument();
    expect(container.querySelector('.goat-feed-icon')).toHaveTextContent('🐐');
    expect(container.querySelector('.goat-activation-icon')).toBeNull();
    expect(container.querySelector('button')).toBeNull();
    expect(source).not.toMatch(/sendCommand|getClientOnce/);
  });

  it('renders an honest unavailable count', () => {
    render(GoatFeedingsCard, {
      props: { feedings: 'UNDEF', motorState: 'OFF' },
    });

    expect(screen.getByText('Feedings unavailable')).toBeInTheDocument();
  });

  it('ignores initial ON and shows the goat only for a later OFF to ON', async () => {
    vi.useFakeTimers();
    const view = render(GoatFeedingsCard, {
      props: { feedings: '1', motorState: 'ON', feedbackMs: 1800 },
    });

    expect(view.container.querySelector('.goat-activation-icon')).toBeNull();
    await view.rerender({ feedings: '1', motorState: 'OFF', feedbackMs: 1800 });
    expect(view.container.querySelector('.goat-activation-icon')).toBeNull();
    await view.rerender({ feedings: '2', motorState: 'ON', feedbackMs: 1800 });
    expect(view.container.querySelector('.goat-activation-icon')).toHaveTextContent('🐐');

    vi.advanceTimersByTime(1800);
    await tick();
    expect(view.container.querySelector('.goat-activation-icon')).toBeNull();
    expect(view.container.querySelector('.goat-feed-icon')).toHaveTextContent('🐐');
  });

  it('does not attempt audio before a browser interaction', async () => {
    const { context } = installFakeAudioContext();
    const view = render(GoatFeedingsCard, {
      props: { feedings: '0', motorState: 'OFF' },
    });

    await view.rerender({ feedings: '1', motorState: 'ON' });

    expect(context.createOscillator).not.toHaveBeenCalled();
  });

  it('plays one quiet short chime after the first browser interaction', async () => {
    const { context, gain, oscillator } = installFakeAudioContext();
    const view = render(GoatFeedingsCard, {
      props: { feedings: '0', motorState: 'OFF' },
    });

    await fireEvent.pointerDown(window);
    await view.rerender({ feedings: '1', motorState: 'ON' });

    expect(context.resume).toHaveBeenCalledTimes(1);
    expect(context.createOscillator).toHaveBeenCalledTimes(1);
    expect(gain.gain.setValueAtTime).toHaveBeenCalledWith(0.025, 1);
    expect(oscillator.start).toHaveBeenCalledWith(1);
    expect(oscillator.stop).toHaveBeenCalledWith(1.25);
  });

  it('keeps visual feedback when audio setup fails and disables motion on request', async () => {
    Object.defineProperty(window, 'AudioContext', {
      configurable: true,
      value: class {
        constructor() {
          throw new Error('blocked');
        }
      },
    });
    const view = render(GoatFeedingsCard, {
      props: { feedings: '0', motorState: 'OFF' },
    });

    await fireEvent.keyDown(window, { key: 'Enter' });
    await view.rerender({ feedings: '1', motorState: 'ON' });

    expect(view.container.querySelector('.goat-activation-icon')).toHaveTextContent('🐐');
    expect(source).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
    expect(source).toMatch(/\.goat-activation-icon\s*\{\s*animation:\s*none/s);
  });

  it('clears feedback resources on teardown', async () => {
    vi.useFakeTimers();
    const { context } = installFakeAudioContext();
    const view = render(GoatFeedingsCard, {
      props: { feedings: '0', motorState: 'OFF' },
    });

    await fireEvent.pointerDown(window);
    await view.rerender({ feedings: '1', motorState: 'ON' });
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    view.unmount();

    expect(context.close).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });
});
