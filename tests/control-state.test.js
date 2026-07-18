import { describe, expect, it } from 'vitest';
import {
  CONTROL_PHASES,
  deriveControlState,
  outcomePresentation,
} from '../src/lib/controls/controlState.js';
import { CONTROL_CATALOG } from '../src/lib/controls/catalog.js';

const live = {
  connection: 'live',
  releaseMode: 'safe-compat',
  providerOnline: {},
  capabilities: {},
  items: {},
};

describe('deriveControlState', () => {
  it.each([
    ['missing', undefined],
    ['null', null],
    ['NULL', 'NULL'],
    ['UNDEF', 'UNDEF'],
    ['empty', ''],
    ['unknown', 'MAYBE'],
  ])('renders %s as unavailable, disabled, and never OFF', (_name, value) => {
    const state = deriveControlState(CONTROL_CATALOG.circadian, {
      ...live,
      items: { LivingRoomCircadian_Enable: value },
    });

    expect(state).toMatchObject({
      phase: 'unavailable',
      enabled: false,
      value: null,
      valueLabel: 'Unavailable',
    });
    expect(state.valueLabel).not.toBe('OFF');
  });

  it('defaults an otherwise healthy virtual policy to maintenance/read-only', () => {
    const state = deriveControlState(CONTROL_CATALOG.circadian, {
      connection: 'live',
      items: {
        LivingRoomCircadian_Enable: 'OFF',
        LivingRoomCircadian_LastResult: 'ok',
      },
    });

    expect(state).toMatchObject({
      enabled: false,
      value: 'OFF',
      reason: 'Maintenance release — commands unavailable',
    });
  });

  it.each(['maintenance', 'unknown', 'development'])('fails virtual policy closed in release mode %s', (releaseMode) => {
    const state = deriveControlState(CONTROL_CATALOG.circadian, {
      connection: 'live',
      releaseMode,
      items: {
        LivingRoomCircadian_Enable: 'ON',
        LivingRoomCircadian_LastResult: 'ok',
      },
    });

    expect(state).toMatchObject({
      enabled: false,
      value: 'ON',
      reason: 'Maintenance release — commands unavailable',
    });
  });

  it('fails closed while openHAB is offline even with a binary value', () => {
    const state = deriveControlState(CONTROL_CATALOG.circadian, {
      ...live,
      connection: 'offline',
      items: { LivingRoomCircadian_Enable: 'OFF' },
    });

    expect(state).toMatchObject({
      phase: 'unavailable',
      enabled: false,
      valueLabel: 'Unavailable',
      reason: 'openHAB unavailable',
    });
  });

  it('requires explicit provider health for a physical binary control', () => {
    const item = CONTROL_CATALOG.living1.stateItem;
    const unknownHealth = deriveControlState(CONTROL_CATALOG.living1, {
      ...live,
      items: { [item]: 'OFF' },
    });
    const online = deriveControlState(CONTROL_CATALOG.living1, {
      ...live,
      items: { [item]: 'OFF' },
      providerOnline: { [item]: { status: 'ONLINE' } },
    });

    expect(unknownHealth).toMatchObject({
      enabled: false,
      valueLabel: 'Unavailable',
      reason: 'Provider Thing status unavailable — read-only',
    });
    expect(online).toMatchObject({
      enabled: true,
      value: 'OFF',
      valueLabel: 'OFF',
    });
  });

  it('accepts only a structured ONLINE Thing status for a physical binary', () => {
    const item = CONTROL_CATALOG.living1.stateItem;
    const online = deriveControlState(CONTROL_CATALOG.living1, {
      ...live,
      items: { [item]: 'OFF' },
      providerOnline: {
        [item]: { status: 'ONLINE', statusDetail: 'NONE' },
      },
    });
    const offline = deriveControlState(CONTROL_CATALOG.living1, {
      ...live,
      items: { [item]: 'OFF' },
      providerOnline: {
        [item]: {
          status: 'OFFLINE',
          statusDetail: 'COMMUNICATION_ERROR',
          description: 'No route to host',
        },
      },
    });

    expect(online).toMatchObject({
      enabled: true,
      value: 'OFF',
      valueLabel: 'OFF',
    });
    expect(offline).toMatchObject({
      enabled: false,
      valueLabel: 'Unavailable',
      reason: 'Provider OFFLINE — read-only',
      detail: 'No route to host',
    });
  });

  it('keeps circadian policy operable while reporting execution health separately', () => {
    const state = deriveControlState(CONTROL_CATALOG.circadian, {
      ...live,
      items: {
        LivingRoomCircadian_Enable: 'ON',
        LivingRoomCircadian_LastResult: 'skip-backoff living room 1',
      },
    });

    expect(state).toMatchObject({
      enabled: true,
      value: 'ON',
      valueLabel: 'ON',
      healthLabel: 'Degraded',
    });
    expect(state.detail).toContain('skip-backoff');
  });

  it.each([
    ['ON', false, 'Owned by Night Load Override'],
    [undefined, false, 'Override status unavailable — read-only'],
    ['OFF', true, 'Night Load Override transition in progress'],
  ])('fails an owned load closed for override=%s transitioning=%s', (
    overrideState,
    ownerTransitioning,
    reason,
  ) => {
    const state = deriveControlState(CONTROL_CATALOG.dishwasher, {
      ...live,
      capabilities: { 'night-load-owner-v1': true },
      items: {
        Dish_Washer_Power: 'OFF',
        OverrideSwitch: overrideState,
      },
      providerOnline: { Dish_Washer_Power: { status: 'ONLINE' } },
      ownerTransitioning,
    });

    expect(state).toMatchObject({
      enabled: false,
      reason,
    });
  });

  it('keeps owned loads status-only until correlated owner resources are verified', () => {
    const state = deriveControlState(CONTROL_CATALOG.shureflo, {
      ...live,
      items: {
        ShurefloPump_Power: 'OFF',
        OverrideSwitch: 'OFF',
      },
      providerOnline: { ShurefloPump_Power: { status: 'ONLINE' } },
    });

    expect(state).toMatchObject({
      enabled: false,
      reason: 'Owner request channel unavailable — status only',
    });
  });

  it('does not enable an owned load when only a future capability flag is true', () => {
    const state = deriveControlState(CONTROL_CATALOG.shureflo, {
      ...live,
      releaseMode: 'full',
      capabilities: { 'night-load-owner-v1': true },
      items: {
        ShurefloPump_Power: 'OFF',
        OverrideSwitch: 'OFF',
      },
      providerOnline: { ShurefloPump_Power: { status: 'ONLINE' } },
    });

    expect(state.enabled).toBe(false);
    expect(state.reason).toMatch(/submission unavailable.*status only/i);
    expect(state.reason).not.toBe('Ready');
  });

  it.each([
    ['feedOnce', 'feeder'],
    ['circulation', 'circulation'],
    ['override', 'owner'],
  ])('does not label %s Ready when no correlated submission adapter exists', (id, domain) => {
    const control = CONTROL_CATALOG[id];
    const state = deriveControlState(control, {
      ...live,
      releaseMode: 'full',
      capabilities: { [control.capability]: true },
      items: { [control.stateItem]: 'OFF' },
    });

    expect(state.enabled).toBe(false);
    expect(state.reason).toMatch(new RegExp(domain, 'i'));
    expect(state.reason).toMatch(/submission unavailable.*status only/i);
    expect(state.reason).not.toBe('Ready');
  });

  it('shows Goat Cam and FeederOverride coupling', () => {
    const state = deriveControlState(CONTROL_CATALOG.goatCam, {
      ...live,
      items: {
        Goat_Plugs_Outlet1_Switch: 'OFF',
        FeederOverride: 'ON',
        OverrideSwitch: 'ON',
      },
      providerOnline: { Goat_Plugs_Outlet1_Switch: { status: 'ONLINE' } },
    });

    expect(state.detail).toBe('Feeder policy override ON');
    expect(state.reason).toBe('Owned by Night Load Override');
  });

  it.each([
    ['feedOnce', 'Feeder request channel unavailable — actuator status only'],
    ['circulation', 'Circulation request channel unavailable — actuator status only'],
    ['override', 'Owner request channel unavailable — status only'],
  ])('keeps %s read-only before correlated resources exist', (id, reason) => {
    const control = CONTROL_CATALOG[id];
    const state = deriveControlState(control, {
      ...live,
      items: { [control.stateItem]: 'OFF' },
    });

    expect(state).toMatchObject({ enabled: false, reason });
  });
});

describe('submission presentation', () => {
  it('exposes every required command phase without conflating unknown and error', () => {
    expect(CONTROL_PHASES).toEqual([
      'confirmed',
      'unavailable',
      'holding',
      'pending',
      'accepted',
      'error',
      'unknown',
    ]);
    expect(outcomePresentation('pending').label).toBe('Sending…');
    expect(outcomePresentation('accepted').label).toBe('Accepted');
    expect(outcomePresentation('error').label).toBe('Failed');
    expect(outcomePresentation('unknown').label).toBe('Outcome unknown');
  });
});
