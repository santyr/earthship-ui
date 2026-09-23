import { describe, expect, it } from 'vitest';
import { greywaterSchedule } from '../src/lib/ui/greywaterSchedule.js';

const now = Date.parse('2026-09-20T18:30:00Z');
const status = 'reason=cycle_active,scheduleVersion=1,evaluatedAt=2026-09-20T18:30:00Z,scheduling=conditional,nextEligibleAt=2026-09-20T19:24:00Z,nextPump=east';
const input = { south: 'ON', east: 'OFF', status, now };

describe('greywater next eligibility presentation', () => {
  it('shows the owner candidate and Denver time without recomputing policy', () => {
    expect(greywaterSchedule(input)).toMatchObject({ label: 'South running', next: 'Earliest East · 1:24 PM' });
    expect(greywaterSchedule(input).detail).toContain('can change if delayed');
  });
  it('shows East activity even when South is off', () => {
    expect(greywaterSchedule({ ...input, south: 'OFF', east: 'ON' }).label).toBe('East running');
  });
  it.each([undefined, 'NULL', 'reason=cooldown_wait,waitMin=50', status + ',scheduleVersion=1',
    status.replace('18:30:00Z', '18:27:00Z'), status.replace('18:30:00Z', '18:31:00Z'),
    status.replace('nextPump=east', 'nextPump=unknown'), status.replace('19:24:00Z', '17:24:00Z')])(
    'withholds untrusted or stale scheduling data %s', value => {
      expect(greywaterSchedule({ ...input, status: value }).next).toBe('Next unavailable');
    });
  it('shows daylight/SoC holds without inventing tomorrow or a fixed start', () => {
    const blocked = 'scheduleVersion=1,evaluatedAt=2026-09-20T18:30:00Z,scheduling=blocked,reason=';
    expect(greywaterSchedule({ ...input, status: blocked + 'after_dark' }).next).toBe('Waiting for daylight');
    expect(greywaterSchedule({ ...input, status: blocked + 'low_soc' }).next).toBe('Waiting for SoC');
  });
  it('identifies an interrupted or lost pump timer as a hold', () => {
    const blocked = 'scheduleVersion=1,evaluatedAt=2026-09-20T18:30:00Z,scheduling=blocked,reason=';
    expect(greywaterSchedule({ ...input, south: 'OFF', status: blocked + 'cycle_interrupted' }).next)
      .toBe('Cycle interrupted');
    expect(greywaterSchedule({ ...input, south: 'OFF', status: blocked + 'cycle_timer_expired' }).next)
      .toBe('Safety hold');
  });
  it('distinguishes eligibility from a scheduled command', () => {
    expect(greywaterSchedule({ ...input, status: status.replace('19:24:00Z', '18:30:00Z') }).next).toBe('East eligible now');
  });
  it('withholds next-run claims for unknown or simultaneous actuator states', () => {
    expect(greywaterSchedule({ ...input, east: 'NULL' }).next).toBe('Next unavailable');
    expect(greywaterSchedule({ ...input, east: 'ON' })).toMatchObject({ label: 'Both pumps on', next: 'Next unavailable' });
  });
});
