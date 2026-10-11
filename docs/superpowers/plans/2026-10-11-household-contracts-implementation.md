# Household Control Contracts Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline and test-driven-development. One whole-branch review at completion.

**Goal:** Implement PR #3 phases 2B.3–2B.7 and pure typed intent definitions from phase 4, retaining zero live request authority.

**Spec:** `docs/superpowers/plans/2026-10-07-household-intelligence-architecture.md`.

**Architecture:** Pure immutable Python contracts alongside the merged snapshot foundation. Explicit v2 parsers return validated frozen payloads and stable reason codes. Request/result/intent contracts carry provenance; they cannot authorize equipment. No OpenHAB module, HTTP transport, installation or owner migration is introduced.

**Tech Stack:** Python standard library and pytest.

## Global Constraints

- Legacy v1 readers, owner rules and request transport remain unchanged.
- Closed schemas, bounded UTF-8, duplicate-key refusal, finite typed fields.
- Requested/expired/future payloads fail; owner maximum age remains120secondsorstricter.
- Source never weakens age, provenance, parameter or authority checks.
- Planner provenance requires intent/snapshot/version; manual nulls explicit.
- All v1 household intents are shadowOnly true, and translation is disabled.
- Tests serial locally, CPU20percent/memory256MiB/swap0/tasks24; no new solver/dependency.

## Review Focus

- Equality boundaries for requestedAt/expiresAt/owner-age.
- Unknown versions and nested parameters must never become compatible defaults.
- Result request correlation must validate all original provenance, not just ID.
- Repeated/forged source labels cannot grant different gates.
- Mutation after parsing must not change identity or introduce a sendable target.

### Task1: Common reason catalog and request/result v2

**Files:** `openhab/scripts/household/control_contracts.py`, `openhab/scripts/test_household_control_contracts.py`.
**Interfaces:** `parse_request(raw, *, now, owner_max_age_seconds=120)` validates supported explicit capability parameters and closed provenance; `parse_result(raw, *, request, now)` binds request/intent/snapshot identities and status/reason vocabulary. Immutable canonical returnpayloads. Pure legacy-result status decoder accepts complete/completed for compatibility; no existing caller migrated.

- [ ] RED tests: exact closed schema, allsources, age/expiry/future, owner cap, planner provenance, unsupportedparameters, invalidstatuses/reasons, wrongcorrelation, mutation.
- [ ] Implement no transport; GREEN focused tests and commit.

### Task2: Typed shadow intents and disabled translation

**Files:** `openhab/scripts/household/intents.py`, `openhab/scripts/test_household_intents.py`.
**Interfaces:** sealed typed intent with snapshotId, exact refs, versioned resource-effect components, expiresAt, confidence and catalogreasons. Only realowned families or NO_ACTION admitted. `intent_to_request` always refuses with planner_authority_disabled; no callback/endpoint admitted.

- [ ] RED malformed/shadowfalse/expired/effect/tamperedidentity/unsupportedfamily and disabledtranslation tests.
- [ ] Implement strict immutable shadowintent contracts; GREEN, commit and wholebranch review.

### Task3: Documentation and full objective tracking

- [ ] Keep canonical program audit with all PR3phasesandmilestone1; do not mark fullgoal complete from this purecontractstage.
- [ ] Record schema usage, source-derivedowner-age and later migration boundaries.
- [ ] HostedCI, merge stages only with exactheadchecksuccess and review; liveauthoritystilldisabled.
