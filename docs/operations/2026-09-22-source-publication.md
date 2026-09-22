# September 22: source publication and test follow-through

The operator reconnected the GitHub app with access to `santyr` and explicitly
requested publication to `main`. This resolves the earlier GitHub HTTP 403
blocker. The September 21 package receipt remains a historical record, not the
current publication status.

## Published changes

- `adc78f7c9b730a7e60c4cef4e54541e8403d2b26`: published the prepared thermal
  confirmation ingress, isolated JDBC collection-boundary checks, 137 offline
  regressions and runbooks. Added an explicit Python 3.12 test environment and
  declared the previously missing test dependencies.
- `3273712126c2ae71b1a6b20998870a6b16ffd28b`: added nine actual PostgreSQL
  integration cases for the new ingress and declared Requests, which the first
  repaired CI run exposed as another missing dependency.

The Python dependencies are for CI/testing, not a household runtime upgrade.
The original `0fa49f2` CI run failed during collection because NumPy, psycopg2
and Flask were absent. The next run exposed Requests. Tests were not disabled or
weakened to conceal these failures.

## Evidence

The original package's 137 offline tests were rerun locally and passed. The
first published CI run also passed those tests, all 1,627 UI tests, and the
production bundle build before reporting the additional missing Requests import.

As of 2026-09-22 13:33 UTC, CI run `35733736102`, job `106765530444`, for
`3273712` has passed UI tests, the build, dependency installation and the
completion regression step. The full OpenHAB Python suite is still running;
the operational-tooling step is pending. Do not count the nine new PostgreSQL
cases or the complete workflow as passed until the actual job result is read.
The prior run `35733459579` failed on the now-corrected missing Requests import.

The new database tests use the existing disposable PostgreSQL 16 fixture and
real `ActionJournal`, `ActionEvent`, SQL constraints and restricted-role access.
They exercise exact receipts, duplicate/re-wrapped messages after SQLite restart,
a committed transaction followed by failed readback, append-only correction
links, atomic rollback of an invalid final record, absence of journal writes
for non-confirmations, and rejection of evidence rewrites. The Nostr decoder
remains an explicit test double in this suite: database evidence is not crypto,
bunker, relay or end-to-end household qualification.

## Unchanged production boundary

No household service was restarted or enabled, no production database was
written, no Items or controls were changed, and no model was promoted. Source
publication is not deployment. Do not deploy the incompatible thermal v5
runtime alone without its separately qualified artifact/runtime release.

The extended JDBC provider rehearsal still requires actual isolated OpenHAB
execution on the qualified host, including forecast and independent-power
restoration. The Nostr path still requires the pinned binary/keyer, encrypted
sender/receiver/acknowledgement wiring, and genuine operator evidence. Thermal
graduation, natural scoring/report checks and seasonal gates remain open in
[outstanding-work.md](outstanding-work.md) and
[thermal-model-graduation.md](thermal-model-graduation.md).

The npm install also reports six dependency vulnerabilities (four moderate,
two high); no lockfile or dependency remediation was performed in this change.
Bundle-size and old action-runtime deprecation warnings remain separately from
functional test results. Do not describe this checkpoint as a security audit or
overall project completion.
