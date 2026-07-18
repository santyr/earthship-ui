// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import fs from 'node:fs';
import { cleanup, fireEvent, render, screen } from '@testing-library/svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('svelte', async () => import(
  '/home/sat/earthship-ui/node_modules/svelte/src/index-client.js'
));

const mocks = vi.hoisted(() => ({
  sendCommand: vi.fn(),
}));

vi.mock('../../src/lib/openhab/index.js', async () => {
  const { writable } = await import('svelte/store');
  return {
    items: writable({}),
    connection: writable('live'),
    thingStatuses: writable({}),
    getClientOnce: () => ({ sendCommand: mocks.sendCommand }),
  };
});

import { items, thingStatuses, connection } from '../../src/lib/openhab/index.js';
import { CONTROL_CATALOG } from '../../src/lib/controls/catalog.js';
import Toggle from '../../src/lib/ui/Toggle.svelte';
import Controls from '../../src/screens/Controls.svelte';

function pointer(type, pointerId = 1) {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'pointerId', { value: pointerId });
  return event;
}

describe('typed controls UI', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.sendCommand.mockReset();
    mocks.sendCommand.mockResolvedValue(undefined);
    connection.set('live');
    items.set({});
    thingStatuses.set({});
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('never renders missing, NULL, UNDEF, or unknown state as OFF', () => {
    for (const value of [undefined, null, 'NULL', 'UNDEF', 'MAYBE']) {
      items.set({ LivingRoomCircadian_Enable: value });
      const view = render(Toggle, {
        props: { control: CONTROL_CATALOG.circadian },
      });

      const button = screen.getByRole('button', { name: /Circadian/i });
      expect(button).toBeDisabled();
      expect(button).toHaveTextContent('Unavailable');
      expect(button).not.toHaveTextContent(/\bOFF\b/);
      view.unmount();
    }
  });

  it('renders provider OFFLINE explicitly and enables a recovered light in safe-compat', async () => {
    const control = CONTROL_CATALOG.living1;
    items.set({ [control.stateItem]: 'OFF' });
    thingStatuses.set({
      [control.providerThingUid]: {
        status: 'OFFLINE',
        statusDetail: 'COMMUNICATION_ERROR',
        description: 'No route to host',
      },
    });
    render(Controls, { props: { releaseMode: 'safe-compat' } });

    const button = screen.getByRole('button', { name: /Living Room 1/i });
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Provider OFFLINE');
    expect(button).toHaveTextContent('No route to host');

    thingStatuses.set({
      [control.providerThingUid]: {
        status: 'ONLINE',
        statusDetail: 'NONE',
        description: '',
      },
    });

    await vi.waitFor(() => {
      expect(button).not.toBeDisabled();
      expect(button).toHaveTextContent('OFF');
    });
    expect(mocks.sendCommand).not.toHaveBeenCalled();
  });

  it('submits the virtual circadian policy once after a 600 ms hold', async () => {
    items.set({
      LivingRoomCircadian_Enable: 'OFF',
      LivingRoomCircadian_LastResult: 'ok',
    });
    render(Toggle, { props: {
      control: CONTROL_CATALOG.circadian,
      releaseMode: 'safe-compat',
    } });

    const button = screen.getByRole('button', { name: /Circadian/i });
    button.dispatchEvent(pointer('pointerdown'));
    vi.advanceTimersByTime(599);
    expect(mocks.sendCommand).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    await vi.waitFor(() => {
      expect(mocks.sendCommand).toHaveBeenCalledWith(
        'LivingRoomCircadian_Enable',
        'ON',
      );
    });
    expect(mocks.sendCommand).toHaveBeenCalledTimes(1);
    await vi.waitFor(() => {
      expect(button).toHaveTextContent('Accepted');
    });
  });

  it('renders the default development release as maintenance and cannot submit', () => {
    items.set({
      LivingRoomCircadian_Enable: 'OFF',
      LivingRoomCircadian_LastResult: 'ok',
    });
    render(Toggle, { props: { control: CONTROL_CATALOG.circadian } });

    const button = screen.getByRole('button', { name: /Circadian/i });
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Maintenance release');

    button.dispatchEvent(pointer('pointerdown'));
    vi.advanceTimersByTime(1_200);
    expect(mocks.sendCommand).not.toHaveBeenCalled();
  });

  it('cancels a hold when live state changes the pending command contract', async () => {
    items.set({
      LivingRoomCircadian_Enable: 'OFF',
      LivingRoomCircadian_LastResult: 'ok',
    });
    render(Toggle, { props: {
      control: CONTROL_CATALOG.circadian,
      releaseMode: 'safe-compat',
    } });

    const button = screen.getByRole('button', { name: /Circadian/i });
    button.dispatchEvent(pointer('pointerdown'));
    vi.advanceTimersByTime(300);
    items.set({
      LivingRoomCircadian_Enable: 'ON',
      LivingRoomCircadian_LastResult: 'ok',
    });
    await vi.waitFor(() => expect(button).toHaveAttribute('aria-pressed', 'true'));
    vi.advanceTimersByTime(400);

    expect(mocks.sendCommand).not.toHaveBeenCalled();
  });

  it('renders circadian execution health separately from desired policy', () => {
    items.set({
      LivingRoomCircadian_Enable: 'ON',
      LivingRoomCircadian_LastResult: 'skip-backoff for living room bulbs',
    });
    render(Toggle, { props: {
      control: CONTROL_CATALOG.circadian,
      releaseMode: 'safe-compat',
    } });

    const button = screen.getByRole('button', { name: /Circadian/i });
    expect(button).toHaveTextContent('ON');
    expect(button).toHaveTextContent('Degraded');
    expect(button).toHaveTextContent('skip-backoff');
    expect(button).not.toBeDisabled();
    expect(screen.getByText('Degraded')).toHaveClass('degraded');
    const source = fs.readFileSync('src/lib/ui/Toggle.svelte', 'utf8');
    expect(source).toMatch(/\.degraded\s*\{[^}]*flex-shrink:\s*0/s);
  });

  it('renders owned load ownership and Goat Cam feeder coupling as read-only', () => {
    items.set({
      Goat_Plugs_Outlet1_Switch: 'OFF',
      OverrideSwitch: 'ON',
      FeederOverride: 'ON',
    });
    render(Toggle, { props: { control: CONTROL_CATALOG.goatCam } });

    const button = screen.getByRole('button', { name: /Goat Cam/i });
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Owned by Night Load Override');
    expect(button).toHaveTextContent('Feeder policy override ON');
  });

  it('presents feeder and circulation as disabled actions with actuator status', () => {
    items.set({
      Goat_Plugs_Outlet2_Switch: 'OFF',
      SouthOutlet_Outlet2_Switch: 'OFF',
    });
    render(Controls);

    const feed = screen.getByRole('button', { name: /Feed once/i });
    const circulation = screen.getByRole('button', { name: /Request circulation/i });

    expect(feed).toBeDisabled();
    expect(feed).toHaveTextContent('Actuator OFF');
    expect(feed).toHaveTextContent('status only');
    expect(circulation).toBeDisabled();
    expect(circulation).toHaveTextContent('Pump OFF');
    expect(circulation).toHaveTextContent('status only');
    expect(screen.getByText('Living Room 3')).toBeInTheDocument();
  });

  it('does not submit any read-only control on pointer or keyboard input', async () => {
    items.set({
      Dish_Washer_Power: 'OFF',
      OverrideSwitch: 'ON',
    });
    render(Toggle, { props: { control: CONTROL_CATALOG.dishwasher } });
    const button = screen.getByRole('button', { name: /Dishwasher/i });

    await fireEvent.pointerDown(button, { pointerId: 1 });
    await fireEvent.keyDown(button, { key: 'Enter' });
    vi.advanceTimersByTime(1_200);

    expect(mocks.sendCommand).not.toHaveBeenCalled();
  });
});
