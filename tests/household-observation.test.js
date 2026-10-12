import { describe, it, expect } from 'vitest';
import { observation, proposal, AT } from './fixtures/household-observation.js';
import { parseHouseholdObservation } from '../src/lib/household/observation.js';

describe('household observation', () => {
  it('keeps an empty shadow selection inspectable with unavailable policy comparison', () => {
    const view = parseHouseholdObservation(JSON.stringify(observation()), { nowMs: AT });
    expect(view.effectiveMode).toBe('shadow');
    expect(view.snapshotAgeSeconds).toBe(20);
    expect(view.proposals).toEqual([]);
    expect(view.policy_comparison.status).toBe('unavailable');
  });
  it('does not renew source or plan expiry when served later', () => {
    const source = observation();
    const view = parseHouseholdObservation(JSON.stringify(source), { nowMs: AT + 60_000 });
    expect(view.effectiveMode).toBe('unavailable');
    expect(view.expired).toBe(true);
    expect(view.source_quality[0].current_quality).toBe('expired');
    expect(view.valid_until).toBe(source.valid_until);
  });
  it.each(['schema', 'authority', 'actuation', 'effect', 'private', 'policy', 'future', 'digest', 'source', 'model', 'oversize'])(
    'refuses %s corruption', (damage) => {
      const row = observation();
      if (damage === 'schema') row.schema = 'future/v99';
      if (damage === 'authority') row.authority = 'active-request';
      if (damage === 'actuation') row.automatic_actuation = true;
      if (damage === 'effect') row.effects_qualified = true;
      if (damage === 'private') row.source_contexts = { raw: 'operator-only-data' };
      if (damage === 'policy') row.policy_comparison = { status: 'agrees', reason: null };
      if (damage === 'future') row.snapshot_as_of = '2026-10-13T03:00:15Z';
      if (damage === 'digest') row.receipt_sha256 = 'invalid';
      if (damage === 'source') row.source_quality[0].raw = 'operator-only-data';
      if (damage === 'model') row.model_identities[0].private_path = '/private/model';
      const raw = damage === 'oversize' ? 'x'.repeat(32769) : JSON.stringify(row);
      expect(parseHouseholdObservation(raw, { nowMs: AT })).toBeNull();
    });
  it('refuses an observation whose verification precedes its decision', () => {
    const row = observation(); row.verified_at = '2026-10-12T03:00:29Z';
    expect(parseHouseholdObservation(JSON.stringify(row), { nowMs: AT })).toBeNull();
  });
});

describe('proposal evidence boundaries', () => {
  it('preserves unknown effects and the hard blocker without selecting an action', () => {
    const row = observation(); row.proposals = [proposal()];
    const view = parseHouseholdObservation(JSON.stringify(row), { nowMs: AT });
    expect(view.proposals[0].expected_effects.batteryKwh).toBeNull();
    expect(view.proposals[0].hard_checks[0].status).toBe('unknown');
    expect(view.proposals[0].selected).toBe(false);
  });
  it.each(['units', 'effect', 'selection', 'private', 'duplicate', 'limit', 'calendar', 'freshness'])(
    'refuses contradictory or unsupported %s evidence', damage => {
      const row = observation(); row.proposals = [proposal()];
      if (damage === 'units') row.proposals[0].effect_units.batteryKwh = 'Wh';
      if (damage === 'effect') row.proposals[0].expected_effects.socPct = 101;
      if (damage === 'selection') row.proposals[0].selected = true;
      if (damage === 'private') row.proposals[0].hard_checks[0].script = 'operator-only-data';
      if (damage === 'duplicate') row.proposals.push(proposal());
      if (damage === 'limit') row.source_quality = Array(65).fill(row.source_quality[0]);
      if (damage === 'calendar') row.snapshot_as_of = '2026-02-30T03:00:15Z';
      if (damage === 'freshness') row.source_quality[0].valid_until = '2026-10-12T03:00:14Z';
      expect(parseHouseholdObservation(JSON.stringify(row), { nowMs: AT })).toBeNull();
    });
});

it.each(['top', 'nested', 'escaped'])('refuses %s duplicate object keys before projecting a view', damage => {
  const raw = JSON.stringify(observation());
  const changed = damage === 'top' ? raw.replace('{', '{"source_quality":[{"raw_source":"operator-only-data"}],')
    : damage === 'nested' ? raw.replace('"domain":"energy"', '"domain":{"private_path":"operator-only-data"},"domain":"energy"')
    : raw.replace('"domain":"energy"', '"dom\\u0061in":{"private_path":"operator-only-data"},"domain":"energy"');
  expect(parseHouseholdObservation(changed, { nowMs: AT })).toBeNull();
});
