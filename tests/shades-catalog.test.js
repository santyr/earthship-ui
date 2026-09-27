import { describe, expect, it } from 'vitest';
import { SHADE_COUNT, SHADE_SLOTS, SHADES_PER_PAGE, parseShadeReport, shadePosition, shadePresentation } from '../src/lib/shades/catalog.js';

const NOW = Date.parse('2026-09-27T23:00:00Z');
const state = (position, received = NOW / 1000) => JSON.stringify({
  schema_version: 1, source: 'motor_report', stale: false,
  reported_position: position, report_received_at: received, report: {}, cache: {},
});

describe('shade inventory and report presentation', () => {
  it('reserves exactly 26 unique numbered slots without guessed hardware mappings', () => {
    expect(SHADE_COUNT).toBe(26);
    expect(SHADES_PER_PAGE).toBe(13);
    expect(SHADE_SLOTS.map((slot) => slot.number)).toEqual(Array.from({ length: 26 }, (_, i) => i + 1));
    expect(SHADE_SLOTS.every((slot) => slot.positionItem === null && slot.availabilityItem === null && slot.stateItem === null)).toBe(true);
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
      .toEqual({ state: 'reported', label: 'Open', position: 0, observedAtMs: NOW });
    expect(shadePresentation(mapped, { Shade_Example: '100', Shade_Example_Available: 'ON', Shade_Example_Diagnostics: state(100) }, 'live', NOW))
      .toEqual({ state: 'reported', label: 'Closed', position: 100, observedAtMs: NOW });
  });
});
