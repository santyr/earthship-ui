# Forecast v2 Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore genuine current forecast snapshot ingestion without corrupting historical provenance.

**Architecture:** Extend the existing pure Solar_PV forecast normalizer for versions 1 and 2. The existing scheduled capture and persistence owner remain unchanged. Battery UI v2 is a separate implementation plan under the same approved design.

**Tech Stack:** Python 3.12, pytest, PostgreSQL, existing OpenHAB/systemd integration.

## Global Constraints

- Approved spec: docs/superpowers/specs/2026-09-05-energy-analytics-completion-design.md in earthship-ui.
- Support exactly integer forecast versions 1 and 2; reject booleans, unknown versions and malformed structures.
- Retain original generatedAt as issued_at, actual target timestamps as valid_for, and existing local-day/timezone semantics.
- Values are the published corrected forecast, not raw Open-Meteo values; never relabel them as raw training targets or correct twice.
- No new counter, no database migration, and no change to cumulative rollups.
- No deployment, production database writes, OpenHAB writes, or secret access during implementation/tests.
- Worktree: /home/sat/earthship-ui/.worktrees/energy-analytics-solar (Solar_PV branch work/energy-analytics-solar). Base357b052, baseline143 tests pass.

### Task 1: Version-aware capture with provenance and failure tests

**Files:**
- Modify: analytics/src/earthship_energy/forecasts.py
- Test: analytics/tests/test_forecasts.py
- Test: analytics/tests/test_scheduled.py
- Modify: docs/architecture/cross-repo-contracts.md (document supported input versions only; preserve historical inventory)

**Interfaces:**
- Consumes: snapshots_from_openhab_detail(payload: dict) and ForecastSnapshot dataclass.
- Produces: same list[ForecastSnapshot] interface and existing persistence key; v1 payload provenance unchanged, v2 payload includes forecast_version=2 and temperatureAdjustment copied from validated metadata.

- [ ] Add synthetic v2 fixture and RED regression in test_forecasts.py:

```python
def detail_v2():
    return {
        'version': 2, 'generatedAt': '2026-09-05T06:40:29-06:00',
        'timezone': 'America/Denver',
        'temperatureAdjustment': {
            'highCorrectionF': 3.4, 'lowCorrectionF': -8.2,
            'hourlyMethod': 'hourly-blend',
            'hourBuckets': [{'hour': h, 'count': 5, 'weight': 0.5} for h in range(24)],
        },
        'days': [{'date': '2026-09-06', 'summary': {'pvKwh': 6.9},
                  'hours': [{'at': '2026-09-06T11:00:00-06:00', 'tempF': 88.2}]}],
    }

def test_v2_preserves_corrected_values_and_provenance():
    payload = detail_v2()
    rows = snapshots_from_openhab_detail(payload)
    row = next(row for row in rows if row.metric == 'temperature_f')
    assert row.value == 88.2
    assert row.issued_at.isoformat() == payload['generatedAt']
    assert row.payload == {'forecast_version': 2,
                           'temperatureAdjustment': payload['temperatureAdjustment']}
```

- [ ] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_forecasts.py` from analytics. Expect new regression to fail with the current version1 rejection.
- [ ] Add parameterized rejection tests for versions True, False, 1.0, 2.0, 3 and '2'; malformed/missing metadata; nonfinite/bool corrections; unordered or missing buckets; negative/bool count; out-of-range/bool weight. Add finite/null metric and invalid metric tests for both versions, including bool, strings, NaN and infinity. Test rejection before capture touches a recording connection, using existing scheduled capture test patterns.
- [ ] Implement the following private helpers in forecasts.py, importing deepcopy and math.isfinite:

```python
def _metric_value(value):
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError('forecast metric must be finite numeric or null')
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError('forecast metric must be finite numeric or null') from exc
    if not isfinite(result):
        raise ValueError('forecast metric must be finite numeric or null')
    return result

def _provenance(payload):
    version = payload.get('version') if isinstance(payload, dict) else None
    if type(version) is not int or version not in (1, 2):
        raise ValueError('forecast detail version must be 1 or 2')
    result = {'forecast_version': version}
    if version == 1:
        return result
    adjustment = payload.get('temperatureAdjustment')
    if not isinstance(adjustment, dict):
        raise ValueError('temperatureAdjustment is required')
    for key in ('highCorrectionF', 'lowCorrectionF'):
        if _metric_value(adjustment.get(key)) is None:
            raise ValueError('temperatureAdjustment corrections are required')
    if adjustment.get('hourlyMethod') not in ('daily-fallback', 'hourly-blend'):
        raise ValueError('temperatureAdjustment method is invalid')
    buckets = adjustment.get('hourBuckets')
    if not isinstance(buckets, list) or len(buckets) != 24:
        raise ValueError('temperatureAdjustment requires 24 buckets')
    for hour, bucket in enumerate(buckets):
        if not isinstance(bucket, dict) or type(bucket.get('hour')) is not int or bucket['hour'] != hour:
            raise ValueError('temperatureAdjustment buckets must be ordered')
        count = bucket.get('count')
        weight = _metric_value(bucket.get('weight'))
        if type(count) is not int or count < 0 or weight is None or not 0 <= weight <= 1:
            raise ValueError('temperatureAdjustment bucket count/weight invalid')
    result['temperatureAdjustment'] = deepcopy(adjustment)
    return result
```

- [ ] Replace the old version guard and constant provenance with `provenance = _provenance(payload)`. Convert recognized summary/hour values via `_metric_value` rather than float coercion. Validate recognized values before deciding whether to omit a past target. Preserve all valid timestamps and published values. Do not change forecast issue-time selection or persistence key.
- [ ] Extend v1/v2 tests for same-day pre-issue omission, DST-aware next-day midnight and aware timestamps. Retain the existing idempotent SQL test and add a repeated-capture recording test if needed to prove unchanged source/issue/target/metric keys. Ensure metadata cannot be changed by mutating the input after parsing.
- [ ] Run focused tests, then `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q` once. Expect all tests pass. Run `git diff --check`.
- [ ] Document supported v1/v2 input and corrected-value provenance in the Solar_PV cross-repo contract. Do not claim deployment or fresh history in this commit.
- [ ] Commit only the changed source/tests/docs with `fix: ingest corrected forecast detail v2 with provenance`. Write the report with RED/GREEN commands/results, full suite result, commit and any concerns.

## Controller verification and deployment checkpoint

- [ ] Review complete task diff and resolve spec/quality findings.
- [ ] Verify the parser against a fresh real v2 payload read-only and confirm dates/version/provenance without printing household payloads.
- [ ] Before production mutation, verify exact installed source/base, repository state and deployment approval. Preserve a rollback copy; deploy only reviewed changes through the owning repository workflow.
- [ ] Run the existing forecast-snapshot service once, confirm success and genuinely new issued_at records; no historical synthetic backfill.
- [ ] Run the existing analytics publisher, confirm live forecast status and age reflect current evidence. Keep the broader goal and other tasks open.
