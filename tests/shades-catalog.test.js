import { describe, expect, it } from 'vitest';
import { HALLWAY_TEMPERATURE_ITEM, SHADE_COUNT, SHADE_GROUPS, SHADE_SLOTS, SHADE_VIEWS, parseShadeReport, shadeGroupPresentation, shadePosition, shadePresentation, shadePreviewEnabled } from '../src/lib/shades/catalog.js';

const NOW = Date.parse('2026-09-27T23:00:00Z');
const state = (position, received = NOW / 1000) => JSON.stringify({
  schema_version: 1, source: 'motor_report', stale: false,
  reported_position: position, report_received_at: received, report: {}, cache: {},
});

describe('shade inventory and report presentation', () => {
  it('permits preview only for the full inventory with no partial or complete Item mappings', () => {
    expect(shadePreviewEnabled(SHADE_SLOTS)).toBe(true);
    expect(shadePreviewEnabled([])).toBe(false);
    expect(shadePreviewEnabled(SHADE_SLOTS.slice(0, 26))).toBe(false);
    for (const key of ['positionItem', 'availabilityItem', 'stateItem']) {
      const partial = SHADE_SLOTS.map((slot, index) => index === 0 ? { ...slot, [key]: 'Commissioned_Item' } : slot);
      expect(shadePreviewEnabled(partial)).toBe(false);
    }
    const complete = SHADE_SLOTS.map((slot, index) => index === 0 ? {
      ...slot, positionItem: 'Position', availabilityItem: 'Available', stateItem: 'Diagnostics',
    } : slot);
    expect(shadePreviewEnabled(complete)).toBe(false);
  });

  it('reserves 27 unique numbered slots in the operator-approved rooms without guessed mappings', () => {
    expect(SHADE_COUNT).toBe(27);
    expect(SHADE_GROUPS.map((group) => [group.label, group.first, group.last])).toEqual([
      ['Kitchen', 1, 8], ['Living Room', 9, 17], ['Bathroom', 18, 22], ['Bedroom', 23, 27],
    ]);
    expect(SHADE_VIEWS.map((view) => view.rooms)).toEqual([['kitchen', 'living'], ['bathroom', 'bedroom']]);
    expect(SHADE_SLOTS.map((slot) => slot.number)).toEqual(Array.from({ length: 27 }, (_, i) => i + 1));
    expect(SHADE_GROUPS.map((group) => SHADE_SLOTS.filter((slot) => slot.room === group.id).length)).toEqual([8, 9, 5, 5]);
    expect(SHADE_SLOTS[8].label).toBe('Living Room Shade 09');
    expect(SHADE_SLOTS[26].label).toBe('Bedroom Shade 27');
    expect(SHADE_SLOTS.every((slot) => slot.positionItem === null && slot.availabilityItem === null && slot.stateItem === null)).toBe(true);
  });

  it('uses Bedroom independently, keeps the Living Room proxy and leaves Bathroom unobserved', () => {
    expect(SHADE_GROUPS.map((group) => [group.temperatureItem, group.temperatureRole])).toEqual([
      [HALLWAY_TEMPERATURE_ITEM, 'hallway_kitchen_reference'],
      [HALLWAY_TEMPERATURE_ITEM, 'hallway_proxy'],
      [null, 'unavailable'],
      ['Bedroom_Temperature', 'zone_sensor'],
    ]);
  });

  it.each([['0', 0], ['100', 100], ['48.5', 48.5], ['UNDEF', null], ['NULL', null], ['', null], ['-1', null], ['101', null], ['42 %', null], [null, null]])(
    'parses reported position %s as %s', (input, expected) => {
      expect(shadePosition(input)).toBe(expected);
    },
  );

  const mapped = { label: 'Example', positionItem: 'Shade_Example', availabilityItem: 'Shade_Example_Available', stateItem: 'Shade_Example_Diagnostics' };

  it('accepts only recent, explicit motor reports with their original reception time', () => {
    expect(parseShadeReport(state(0), NOW)).toEqual({ position: 0, observedAtMs: NOW, ageMs: 0 });
    expect(parseShadeReport(state(40, NOW / 1000 - 1801), NOW)).toBeNull();
    expect(parseShadeReport(state(40, NOW / 1000 + 61), NOW)).toBeNull();
    expect(parseShadeReport(JSON.stringify({ ...JSON.parse(state(40)), source: 'bridge_cache' }), NOW)).toBeNull();
    expect(parseShadeReport(JSON.stringify({ ...JSON.parse(state(40)), stale: true }), NOW)).toBeNull();
    expect(parseShadeReport(JSON.stringify({ ...JSON.parse(state(40)), reported_position: null }), NOW)).toBeNull();
  });

  it('never promotes an unmapped or offline slot to a reported position', () => {
    const valid = { Shade_Example: '0', Shade_Example_Available: 'ON', Shade_Example_Diagnostics: state(0) };
    expect(shadePresentation(SHADE_SLOTS[0], valid, 'live', NOW)).toMatchObject({ state: 'unmapped', position: null });
    expect(shadePresentation(mapped, { ...valid, Shade_Example_Available: 'OFF' }, 'live', NOW)).toMatchObject({ state: 'unavailable', position: null });
    expect(shadePresentation(mapped, valid, 'offline', NOW)).toMatchObject({ state: 'unavailable', position: null });
    expect(shadePresentation(mapped, { ...valid, Shade_Example: 'UNDEF' }, 'live', NOW)).toMatchObject({ state: 'unavailable', position: null });
    expect(shadePresentation(mapped, { ...valid, Shade_Example: '20' }, 'live', NOW)).toMatchObject({ state: 'unavailable', position: null });
  });

  it('uses the adapter openHAB convention only for live, available reports', () => {
    expect(shadePresentation(mapped, { Shade_Example: '0', Shade_Example_Available: 'ON', Shade_Example_Diagnostics: state(0) }, 'live', NOW))
      .toEqual({ state: 'reported', label: 'Open', position: 0, openPercent: 100, observedAtMs: NOW });
    expect(shadePresentation(mapped, { Shade_Example: '100', Shade_Example_Available: 'ON', Shade_Example_Diagnostics: state(100) }, 'live', NOW))
      .toEqual({ state: 'reported', label: 'Closed', position: 100, openPercent: 0, observedAtMs: NOW });
    expect(shadePresentation(mapped, { Shade_Example: '25', Shade_Example_Available: 'ON', Shade_Example_Diagnostics: state(25) }, 'live', NOW))
      .toEqual({ state: 'reported', label: '75% open', position: 25, openPercent: 75, observedAtMs: NOW });
  });

  it('shows a group position only when every shade has the same qualified report', () => {
    const slots = [
      { ...mapped, positionItem: 'Shade_1', availabilityItem: 'Available_1', stateItem: 'State_1' },
      { ...mapped, positionItem: 'Shade_2', availabilityItem: 'Available_2', stateItem: 'State_2' },
    ];
    const states = { Shade_1: '25', Available_1: 'ON', State_1: state(25),
      Shade_2: '25', Available_2: 'ON', State_2: state(25) };
    expect(shadeGroupPresentation(slots, states, 'live', NOW)).toEqual({
      state: 'reported', openPercent: 75, label: '75% open',
    });
    expect(shadeGroupPresentation(slots, { ...states, Shade_2: '50', State_2: state(50) }, 'live', NOW))
      .toEqual({ state: 'mixed', openPercent: null, label: 'Mixed positions' });
    expect(shadeGroupPresentation(slots, { ...states, Available_2: 'OFF' }, 'live', NOW))
      .toEqual({ state: 'unavailable', openPercent: null, label: 'Position unavailable' });
    expect(shadeGroupPresentation(slots, states, 'offline', NOW).openPercent).toBeNull();
    expect(shadeGroupPresentation([], states, 'live', NOW).openPercent).toBeNull();
  });
});
