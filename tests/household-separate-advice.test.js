import { describe, expect, it } from 'vitest';
import { parseHouseholdObservation } from '../src/lib/household/observation.js';
import { parseQualification } from '../src/lib/household/qualification.js';
import { recommendationPreview } from '../src/lib/household/recommendations.js';
import { separateAdvice, commandProposal, retainedCommandObservation, ADVICE_AT } from './fixtures/household-separate-advice.js';
const parse = (row, nowMs = ADVICE_AT) => parseHouseholdObservation(JSON.stringify(row), { nowMs });
describe('closed human-advice-separated observation profile', () => {
  it.each([false, true])('reads the producer profile with models present=%s without command eligibility', shadow => {
    const view = parse(separateAdvice({ shadow }));
    expect(view).not.toBeNull();
    expect(view.effectiveMode).toBe(shadow ? 'shadow' : 'unavailable');
    expect(view.qualification_report.families).toEqual([]);
    for (const scope of ['loads', 'devices', 'greywater', 'feeding', 'night-policy']) {
      expect(recommendationPreview(view, scope, ADVICE_AT)).toMatchObject({ rows: [], current: false, automaticActuation: false });
    }
  });
  it('retains expired original identities and recalculates source expiry without renewing clocks', () => {
    const view = parse(separateAdvice({ shadow: true }), ADVICE_AT + 40000);
    expect(view).not.toBeNull(); expect(view.expired).toBe(true); expect(view.effectiveMode).toBe('unavailable');
    expect(view.source_quality[0].current_quality).toBe('expired');
    expect(view.valid_until).toBe('2026-10-24T12:01:00Z'); expect(view.receipt_sha256).toBe('1'.repeat(64));
  });
  it('rejects independent enum-only and qualification-only substitutions', () => {
    const enumOnly = separateAdvice(); enumOnly.qualification_report.schema = 'earthship-household-intent-qualification/v2';
    expect(parse(enumOnly)).toBeNull();
    const qualificationOnly = separateAdvice(); qualificationOnly.candidate_generation.status = 'unavailable';
    expect(parse(qualificationOnly)).toBeNull();
  });
  const damage = {
    proposal: v => v.proposals.push(commandProposal()),
    noActionProposal: v => v.proposals.push({ ...commandProposal(), type: 'NO_ACTION', parameters: {} }),
    family: v => v.qualification_report.families.push({ intent_type: 'SET_NIGHT_LOAD_DEVICE' }),
    release: v => v.qualification_report.release_authorized = true,
    authority: v => v.authority = 'household', automatic: v => v.automatic_actuation = true,
    qualificationAutomatic: v => v.qualification_report.automatic_actuation = true,
    effects: v => v.effects_qualified = true,
    receiptIdentity: v => v.qualification_report.receipt_sha256 = '5'.repeat(64),
    snapshotIdentity: v => v.qualification_report.snapshot_id = '5'.repeat(64),
    decisionIdentity: v => v.qualification_report.decision_at = '2026-10-24T12:00:11Z',
    malformedDigest: v => v.receipt_sha256 = v.qualification_report.receipt_sha256 = 'invalid',
    futureVerification: v => v.verified_at = '2026-10-24T12:00:21Z',
    reversedClock: v => v.snapshot_as_of = '2026-10-24T12:00:11Z',
    wrongMode: v => v.planner_mode = 'shadow', wrongPlanner: v => v.planner_version = 'bounded_exhaustive_v2',
    wrongSchema: v => v.schema = 'earthship-household-observation/v3',
    wrongQualificationSchema: v => v.qualification_report.schema = 'earthship-household-intent-qualification/v4',
    qualifiedReport: v => v.qualification_report.status = 'qualified',
    wrongScope: v => v.qualification_report.scope = 'release',
    missingTop: v => delete v.source_quality, missingGeneration: v => delete v.candidate_generation.reason,
    modelDigest: v => { v.model_identities = separateAdvice({ shadow: true }).model_identities; v.planner_mode = 'shadow'; v.model_identities[0].projection_sha256 = 'invalid'; },
    extraSource: v => v.source_quality[0].private = 'not public',
    duplicateSources: v => v.source_quality.push({ ...v.source_quality[0] }),
    extraTop: v => v.private = 'not public', extraGeneration: v => v.candidate_generation.private = true,
    extraQualification: v => v.qualification_report.private = true,
    missing: v => delete v.qualification_report.release_authorized,
    wrongReason: v => v.candidate_generation.reason = 'unavailable',
    inputQualification: v => v.candidate_generation.input_qualification = 'qualified',
    policyPermission: v => v.policy_comparison.physical_permission = true,
    sourceClock: v => v.source_quality[0].valid_until = '2026-10-24T12:00:30Z',
    duplicateModels: v => { v.model_identities = [separateAdvice({ shadow: true }).model_identities[0], separateAdvice({ shadow: true }).model_identities[0]]; v.planner_mode = 'shadow'; },
  };
  it.each(Object.entries(damage))('fails closed for %s', (_, mutate) => {
    const row = separateAdvice(); mutate(row); expect(parse(row)).toBeNull();
  });
  it('rejects duplicate JSON keys even when the final public value is valid', () => {
    const raw = JSON.stringify(separateAdvice()).replace('{', '{"authority":"command",');
    expect(parseHouseholdObservation(raw, { nowMs: ADVICE_AT })).toBeNull();
  });
  it('accepts empty v3 qualification only in the exact separate-advice context', () => {
    const row = separateAdvice(); expect(parseQualification(row.qualification_report, row)).not.toBeNull();
    row.proposals.push(commandProposal()); expect(parseQualification(row.qualification_report, row)).toBeNull();
    row.proposals = []; row.candidate_generation.status = 'unavailable';
    expect(parseQualification(row.qualification_report, row)).toBeNull();
  });
});

it.each(['v1', 'v2'])('preserves strict retained %s command qualification catalogs', version => {
  const row = retainedCommandObservation(version); expect(parse(row)).not.toBeNull();
  row.qualification_report.families[0].gates[0].evidence_status = 'unavailable'; expect(parse(row)).toBeNull();
  const empty = retainedCommandObservation(version); empty.qualification_report.families = []; expect(parse(empty)).toBeNull();
  const promoted = retainedCommandObservation(version); promoted.qualification_report.families[0].release_authorized = true; expect(parse(promoted)).toBeNull();
});
