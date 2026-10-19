# WeatherNext production worker preparation

Status: worker, CLI and units prepared in source; **not installed or activated**.
No private production configuration or passing release decision was generated.
The existing collector/shadow schedules and incumbent provider remain unchanged.

`openhab/scripts/weather_publish.py --config /absolute/private/config.json`
performs a read-only preflight. Adding `--publish` explicitly invokes the existing
commit-last publication runtime. Both modes require a private, externally reviewed
release decision, unchanged original gate reports, the exact executing source
manifest, authoritative OpenHAB regional configuration, reviewed installed Item
ownership and stopped incumbent writers. There is no provider fallback, fitting,
old-state import, equipment command, notification or automatic release decision.

## Configuration and release decision

The configuration uses schema `earthship-weather-production-config/v1`. Its closed
fields are `schema`, `openhab_base`, `archive`, `evidence_directory`, `shared_lock`,
`token_file`, `release_path`, `release_sha256`, `items_directory`,
`items_directory_metadata`, `item_files`, `code_revision`, and `runtime_manifest`.
Paths must be absolute and resolved. The configuration and release file must be
private, owned, regular files in the existing private configuration directory.
The token file reuses the existing `OPENHAB_TOKEN` environment-file format.
The archive is opened read-only; the existing shared lock is not recreated.

The release schema is `earthship-weather-reviewed-release/v1`. It requires the
explicit external decision `APPROVED_FOR_CUTOVER`, reviewer and nonfuture review
time, exact source revision/runtime digest, site, 336-hour horizon, Google plus
qualified-local-only weather lineage, disabled actuation, and the reviewed Item
ownership digest. Its ten gate categories preserve the approved plan: access,
provenance, prospective acquisition, temperature, solar, precipitation, downstream,
regression, rollback prerequisites and operational health. Every gate names a
retained private original report and its SHA256 alongside the reviewer's `PASS`.
Recovery rehearsal remains deferred.

**This is a reader of a human-reviewed release decision, not a scientific gate
calculator.** Matching report hashes proves unchanged originals; it does not prove
the reports establish skill, acquisition intervals or complete cutover. The release
review must independently establish those requirements from the approved plan.
No helper creates a passing report, invents evidence or reduces the existing
qualification periods. Synthetic test decisions are temporary simulation inputs,
never live admission evidence.

The runtime manifest pins 27 source/deployment files, including the worker,
provider/parser/transport, shared I/O/resource guard, launcher and prepared units.
Execution must use a deployment export with nonwritable source files; the developer
worktree's group-writable files deliberately fail the existing source-file guard.
No worktree/root permissions were changed to run tests.

## Ownership and ongoing admission

The review pins installed Item-file hashes plus the Item directory's UID, GID and
mode. This supports the actual `openhab:openhab` directory mode 2775 without
requiring a host permission change. Individual sources must be regular,
nonwritable, resolved files owned by root, the publisher or the reviewed directory
owner. Reads check inode/size/time stability and bound individual/aggregate bytes.
All eleven retained Items need one declaration of the correct type in a pinned
file; declarations split across lines are recognized, and quoted labels/comments
are excluded. Duplicate definitions refuse. REST then independently checks Item
types/noneditability and channel-link absence.

The six incumbent service/timer identities are read together through a bounded
`systemctl --user show`. Active or enabled writers refuse admission; inactive
static services, masked units and removed units are handled explicitly. This
checks the named scheduled writers, not every possible external caller. The
reviewed ownership/downstream reports must account for rules, other jobs and the
complete provider-removal inventory before release.

Before each request, after pacing, the runtime rechecks the private config/release,
token, source manifest, original gate reports, Item files and incumbent units.
Changes revoke publication. The attempt retained before the first PUT records the
config/release admission identity; the result links to that attempt. Partial
publication and withdrawals retain the existing runtime semantics. Neither a
state readback nor this admission record is a persisted JDBC delivery receipt.

## Prepared scheduling and resource policy

`deploy/weathernext-publish.service` uses the existing shared production launcher:
256 MiB minimum, 512 MiB preferred, 24 tasks and 90 seconds. The existing publication
resource preflight checks actual kernel limits, scheduling priority and host
headroom/pressure; no threshold or safeguard changed. The environment file must
supply the code root, pinned Python and `EARTHSHIP_WEATHER_PRODUCTION_CONFIG`.
The prepared timer preserves the current JSON publisher's five-minute boot delay
and two-hour cadence. Neither unit was installed, enabled or started.

## Verification

- Fifteen caller tests cover default read-only operation, explicit publication and
  retained pre-write admission, incomplete/unqualified/future/foreign-lineage
  review, changed original reports, active/enabled/masked writers, duplicate and
  changed Item sources, actual directory/file ownership conventions, mid-cycle
  release revocation, private configuration/source manifests, authoritative-site
  mismatch, safe CLI failures and the shared-launcher unit contract. The initial
  absent caller and subsequently exposed multiline, directory-metadata,
  directory-owner and masked-unit failures were observed before correction.
- All **211 WeatherNext package tests passed in 8.738 seconds** in the pinned
  environment through shared host admission, from an isolated export. All six
  changed code/test/unit files matched the verified export byte for byte.
- `systemd-analyze --user verify` accepted both prepared units without installing
  or starting them.
- The actual read-only unit adapter returned the expected refusal: incumbent
  `forecast-intel.timer`, `forecast-json.timer` and `forecast-pre-dusk.timer` remain
  active. No timer/service was stopped. Installed Item metadata inspection found
  49 regular, nonwritable sources, totaling 18,528 bytes; two belong to the
  separately reviewed OpenHAB owner rather than the publishing user.

This prepares the operational caller. Final removal/deployment closure, real
fresh Google/local fitting and variable/outcome/interval qualification, actual
reviewed configuration and coordinated cutover remain unfinished. Actuator
requests remain disabled.

## Prepared Item ownership completion

All eleven retained targets now declare `weathernext-publish.service` as their
prepared writer in `openhab/file-config/ownership.json`; the declaration is not
live ownership verification. The unsupported `Forecast_Tomorrow_PrecipProb`
definition and ownership record are removed from the prepared source. Unsupported
Google precipitation probability remains unavailable rather than retaining an
old-provider numeric value after cutover. The two retained tomorrow temperatures
and three JSON definitions preserve their names and types.

The old tomorrow file-transfer helper's batch now has two Items, and its previous
`RELEASE_READY` approval is revoked because its qualified source has changed. A
remaining adapter's third-index assumption was corrected by argument construction
only. Five focused source/migration tests passed in 0.07 seconds, including an
observed `IndexError` regression before correction. They executed no JDBC,
containers or recovery workflow. All 156 unrelated ownership records match the
preceding committed manifest exactly. Installed files, Item states and production
services were untouched; actual unsupported-Item removal belongs to the attended
cutover alongside the complete provider retirement.
