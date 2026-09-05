# Daily Battery Use Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose existing daily SoC range and estimated daily EFC alongside current battery analytics, without duplicate accounting.

**Architecture:** Solar_PV adds the two persisted values to a closed v2 payload on the existing Item. The UI accepts exact v1/v2 contracts and renders the values in the existing detail dialog. Deploy the dual-version reader before the v2 writer.

**Tech Stack:** Python/pytest/PostgreSQL producer; Svelte/Vitest/Playwright consumer.

## Global Constraints

- Approved specification: docs/superpowers/specs/2026-09-05-energy-analytics-completion-design.md.
- No new counter, no database migration, and no change to cumulative rollups.
- Keep the existing <16 KiB limit, 15-minute freshness gate, epoch identity and local through-date display.
- No production writes or deployment by implementers. Controller handles authorized deployment after review.
- Exact v2 schema: earthship-energy-ui/v2; new battery fields latestDepthOfDischargePct (nullable finite0–100) and latestEfc (nullable finite nonnegative).
- Daily range is maximum minus minimum SoC. EFC remains (charge kWh + discharge kWh)/(2 * configured nominal usable kWh).
- Missing evidence stays null, not zero. Partial battery-day quality is not trusted daily coverage; use battery-specific quality, not weather/load quality, to gate the new fields.

### Task 1: Extend the existing producer with persisted daily evidence

**Files:**
- Modify: analytics/src/earthship_energy/report_reader.py
- Modify: analytics/src/earthship_energy/ui_payload.py
- Test: analytics/tests/test_ui_payload.py
- Test: analytics/tests/test_report_reader.py and analytics/tests/test_ui_reader.py (actual reader fixtures)
- Modify: docs/architecture/cross-repo-contracts.md and docs/operations/energy-analytics-publication.md if present; otherwise update the existing publisher runbook located by rg.

**Interfaces:**
- Consumes: daily_battery.depth_of_discharge_pct, daily_efc and quality; existing fetch_daily_report_rows().
- Produces: build_energy_ui_payload() emits v2 with new battery fields; other field meanings unchanged. Python validator validates emitted v2. UI compatibility is Task2.

- [ ] Add RED mapping tests using existing payload() and DAILY fixtures:

```python
def test_daily_battery_fields_use_persisted_evidence(monkeypatch):
    monkeypatch.setitem(DAILY[-1], 'depth_of_discharge_pct', 16.0)
    monkeypatch.setitem(DAILY[-1], 'battery_quality', 'ok')
    result = payload()
    assert result['schema'] == 'earthship-energy-ui/v2'
    assert result['battery']['latestDepthOfDischargePct'] == 16.0
    assert result['battery']['latestEfc'] == DAILY[-1]['daily_efc']

@pytest.mark.parametrize('quality', ['partial', None])
def test_incomplete_battery_day_does_not_claim_daily_use(monkeypatch, quality):
    monkeypatch.setitem(DAILY[-1], 'battery_quality', quality)
    result = payload()
    assert result['battery']['latestDepthOfDischargePct'] is None
    assert result['battery']['latestEfc'] is None
    assert result['battery']['status'] != 'ok'
```

- [ ] Run focused tests; confirm missing fields/version cause RED. Add no-row, missing-field, legitimate-zero, range, nonfinite/bool, and negative-EFC tests; preserve original fixtures' old assertions updated only for version/new keys and explicit battery quality.
- [ ] Append `depth_of_discharge_pct` and `battery_quality` to report_reader.FIELDS and matching SQL SELECT tail (`b.depth_of_discharge_pct, b.quality`). Preserve all existing column positions. Update recording-cursor fixtures to provide both tail columns, proving the new transport rather than asserting only SQL text.
- [ ] In ui_payload.py change SCHEMA to v2 and add both fields to BATTERY_FIELDS. Determine daily confidence with `battery_ok = latest is not None and latest.get('battery_quality') == 'ok'`. Add:

```python
'latestDepthOfDischargePct': latest.get('depth_of_discharge_pct') if battery_ok else None,
'latestEfc': latest.get('daily_efc') if battery_ok else None,
```

Use `unavailable` when no row and `degraded` when battery quality is not ok; preserve existing values' definitions. Existing global degraded/unavailable aggregation must include this battery status.
- [ ] Extend validate_energy_ui_payload with nullable finite checks and bounds:

```python
for field, maximum in (('latestDepthOfDischargePct', 100), ('latestEfc', None)):
    value = battery[field]
    _number(value, f'battery.{field}')
    if value is not None and (value < 0 or (maximum is not None and value > maximum)):
        raise ValueError(f'battery.{field} outside range')
```

- [ ] Run focused producer/reader tests, then full analytics pytest suite and git diff --check. Document v2 and UI-first deployment/rollback order in canonical contracts. Commit scoped change and write RED/GREEN/full-suite report. Do not start publisher.

### Task 2: Dual-version UI reader and existing-dialog display

**Files:**
- Modify: src/lib/energy/analyticsResult.js
- Modify: src/lib/ui/EnergyAnalyticsDetail.svelte
- Test: tests/energy-analytics-result.test.js
- Test: tests/e2e/energy-layout.spec.js
- Modify: tests/fixtures/energyAnalytics.js (keep v1 default; add v2 factory)
- Modify: docs/operations/energy-analytics.md

**Interfaces:**
- Consumes: existing exact v1 plus Task1 exact v2 payload on Energy_Analytics_JSON.
- Produces: same parseEnergyAnalyticsResult() result; battery always has new fields, null for legacy v1. No control surface changes.

- [ ] Add v2 fixture factory from the existing fixture:

```javascript
export function energyAnalyticsV2Fixture() {
  const value = energyAnalyticsFixture();
  value.schema = 'earthship-energy-ui/v2';
  Object.assign(value.battery, {latestDepthOfDischargePct: 16, latestEfc: 0.16});
  return value;
}
```

- [ ] RED tests: validv2 yields both values; v1 yields both null; v2 missing/extra keys rejected; each new field rejects strings, booleans and negative values; DoD101 rejected; null and zero accepted; unsupported v3 rejected; freshness/size gates apply to both versions. Existing v2-without-fields rejection remains valid.
- [ ] Implement schema-aware field selection:

```javascript
const SCHEMAS = new Set(['earthship-energy-ui/v1', 'earthship-energy-ui/v2']);
const BATTERY_V2 = [...BATTERY, 'latestDepthOfDischargePct', 'latestEfc'].sort();
```

Use SCHEMAS in validatePayload; choose BATTERY_V2 only for v2. Run existing number helper then bounds checks on new values. In result normalization use:

```javascript
battery: {latestDepthOfDischargePct: null, latestEfc: null,
          ...structuredClone(payload.battery)},
```

- [ ] RED rendered-dialog test with v2 fixture: assert both labels/values are visible, existing close and modal behavior preserved. Keep a legacy fixture test proving unavailable new values rather than zero.
- [ ] Add rows after Latest daily low:

```svelte
<div><dt>Daily SoC range (DoD)</dt><dd>{metric(result.battery.latestDepthOfDischargePct, ' pp')}</dd></div>
<div><dt>Daily estimated EFC</dt><dd>{metric(result.battery.latestEfc, '', 3)}</dd></div>
```

Label cumulative EFC as estimated. Add brief detail copy: "EFC uses measured charge/discharge energy over available bank-epoch history, not the BMS lifetime cycle count. Daily SoC range does not count repeated partial cycles." Show a concise incomplete-day caveat when battery status is degraded. No new main-page card.
- [ ] Run focused unit and rendered tests, full Vitest, npm run build, and git diff --check. Update runbook to document reader-first deployment and publisher-first rollback. Commit and report complete TDD evidence.

## Controller completion

- [ ] Review each task and whole cross-repository change; resolve findings.
- [ ] Verify publisher output from a real read-only DB query parses through the candidate UI consumer, without publishing.
- [ ] Verify deployment authorization and exact backups, deploy dual reader then writer, run existing publisher and compare live output to persisted date/epoch/quality.
- [ ] Check tablet detail layout textually/with DOM geometry, no screenshots requested; verify existing controls unchanged.
- [ ] Update canonical contracts/tracker/task evidence. Do not close forecast learning or other future-data tasks through this slice.
