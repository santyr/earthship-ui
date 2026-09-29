import { describe, expect, it } from 'vitest';
import { bmsHealthPresentation } from '../src/lib/alerts/batteryHealth.js';

describe('Energy BMS health presentation', () => {
  it.each([
    ['OK', '1', 'ok', 'OK'],
    ['OK', '0', 'fault', 'Absent'],
    ['OK', 'UNDEF', 'unknown', 'Unknown'],
    ['STALE', '1', 'stale', 'Stale'],
    ['STALE age=120s', '1', 'stale', 'Stale'],
    ['FAULT', '1', 'fault', 'Fault'],
    ['ERROR', '1', 'fault', 'Fault'],
    ['UNDEF', '1', 'unknown', 'Unknown'],
    [undefined, undefined, 'unknown', 'Unknown'],
  ])('%s / %s is %s (%s)', (comms, device, state, label) => {
    expect(bmsHealthPresentation(comms, device)).toMatchObject({ state, label });
  });
});
