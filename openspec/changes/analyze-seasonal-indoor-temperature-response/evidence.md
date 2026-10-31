# Completed observational analysis — 2026-10-29

Retained evidence: `artifacts/indoor-thermal-inertia-20261029.local/`.

- `REPORT.md`: methodology, seasonal comparison, gap sensitivity, cadence interpretation and limitations.
- 36 original compressed OpenHAB JDBC persistence responses; 391,682 records, four identified Items, 274 local winter/summer days; original response and compressed-file hashes in `export_manifest.json`.
- Primary indoor air passed the 80% supported-minute criterion on 86/92 summer-2025 days, 77/90 winter-2025–26 days and 91/92 summer-2026 days using the primary 30-minute gap rule.
- Median daily waits for a first observed ≥1°F rise / fall: summer 2025 34/73 minutes; winter 2025–26 18/61 minutes; summer 2026 36/73 minutes. These are conditional observational statistics, not causal building time constants.
- Explicit 15/30/60-minute gap sensitivity, unresolved starts, actual observation precision and change-only persistence limitations are retained in CSV/JSON and report.
- Standard-library independent verification passed all 36 response/file hash pairs, 391,682 record counts, 13,779 primary-air first-change rows and 18 primary seasonal summary rows. Zero invalid or duplicate records.
- Scientific PNG/PDF inspected for readable labels and agreement with verified medians.
- Export and analysis ran inside existing bounded job profiles; no resource-limit events in their retained receipts. The numerical analysis used a 512 MiB / 24-task cap, peaking at approximately 195 MiB.
- OpenSpec strict validation passed with zero issues.

Production changes: none. The accepted five-minute suggestion cadence remains unchanged. No deployment or physical qualification is claimed or required for this read-only analysis. The relocated Bedroom sensor was not used for seasonal room comparisons.
