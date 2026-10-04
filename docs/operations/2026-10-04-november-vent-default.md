# November closed-vent forecast default

The operator directed: starting in November, assume no venting as the forecast
default, **until the operator changes it**. The effective boundary is
**November 1, 2026 at 00:00 America/Denver**, equivalent to **06:00Z**.
Midnight precedes that day's daylight-saving fallback. The default persists
through subsequent months and years; it has no automatic spring ending.

## Implemented behavior

The publisher attaches `_ventClosedFrom` to affected forecast inputs. The
pipeline validates and retains that timestamp at the native five-minute grid.
Baseline vent windows and airflow segments end at the boundary; later vent
forcing is zero. A horizon crossing midnight retains its earlier vent window.
Nonwinter vent candidate search retains this constrained baseline; existing
winter shade search remains available. Published window times and trajectory
markers agree with the constrained schedule.

This uses the existing vent forcing term without adding ventilation coefficients
or airflow calculations. Journal seasonal modes, shade rules, observed state,
action provenance, historical reconstruction and training labels retain their
existing meaning. The output explicitly identifies the closed-vent default as
an operator assumption. It does not represent a confirmed physical vent state.

## Replay and verification

The assumption is frozen in each affected original forcing capture. Replay uses
those captured inputs, not today's mutable publisher default. Old captures
without the field retain their original vent schedule. Forecasts wholly before
the start retain their existing inputs and output.

Fourteen regressions cover the exact Mountain boundary, repeated DST hour,
partial overnight windows, persistence into December and July of the next year,
unchanged shade forcing and winter search, invalid or inconsistent timestamps,
real publication/capture roundtrip, and replay after a later operator policy
change. They pass against both the repository and the coherent installed
runtime. The complete repository Python run reports **4,024 passed, 52 skipped,
91 subtests passed**; the separate explicitly pinned isolated NIP04 run reports
**35 passed**. The expiry-test fixtures now supply aware forecast timestamps;
their expiry clocks and no-publication assertions remain intact. Independent
review reports no blockers.

Both original October 3 and October 4 forecasts replay exactly under the
candidate source. The October 4 original output also replays exactly after
installation, SHA `f1a07fc92fcd4d744fc63d1aa1a53452bfc0c537cf410cb6eaaacc258f25205f`.
These checks establish implementation and replay compatibility, not a live
November observation or model graduation.

## Installed source and recovery

At **2026-10-04T21:21:09Z**, the durable three-file transaction installed
`thermal_intel.py`, `thermal_model/behavior.py`, and `thermal_model/pipeline.py`.
Runtime revision:
`e32fdb8b785014a43aaf6343eb70bb392a3836789ccb3d8bb0a4f749e5e34fe9`.
The accepted artifact retains its original `15267d7a...` training revision.
All 24 other runtime files and four model/report files are byte-identical.
OpenHAB remains PID 1696. No worker, publisher, training job or equipment command
was started. Schedule triggers were briefly paused only for coherent source
installation, then restored active/enabled with the original shadow deadline.
The next natural publication remains a separate continuity checkpoint.

Private source, original rollback bytes and transaction receipts:
`/home/sat/.local/state/thermal-intel/deploy-receipts/november-closed-vent-20261004/`.
The identical install/restore/reinstall sequence passed on isolated temporary
targets before production installation. Recovery uses the retained three-entry
manifest with `thermal-model-files.py`'s receipt-bound restore API; never use a
full runtime manifest to restore this scoped change.

Private postimage replay archive:
`/home/sat/backups/earthship-energy/thermal-post-november-default-20261004-e32fdb8b.tar.gz`.
Creation and independent verification agree on 165 members and 134 captures,
SHA `843d96e0ca94eaaab13c93d212733956294b5d9de5cec74d314a2a8ccfebe695`.
The qualified earlier runtime archive remains the preimage recovery point.

To change this assumption later, use the operator's new instruction to update
the publisher policy and qualify that change. Preserve old capture inputs and
historical labels. Do not infer an ending month from seasonal mode changes.
