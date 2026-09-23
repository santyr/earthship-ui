# Thermal confirmation CLI: narrow live v4 hardening

September 23, 2026, approximately 15:02–15:05 MDT. The production thermal
model stays on its accepted v4 runtime/model pair in shadow mode. The refused
v5 candidate, model fitting, forecasts, and OpenHAB rule state were not changed.

The only installed change was the `_journal` acknowledgement path in
`/home/sat/openhab/scripts/thermal_intel.py`, plus passing the existing `main`
decision time into that function. The source function in this repository is
AST-identical to the installed backport. It now refuses receipt timestamps
later than processing time and completed action/mode timestamps later than
the original receipt, before constructing a journal connection. After append,
it compares the full immutable action and mode records, including duplicate
retries, before printing any success receipt. Missing, changed, duplicate or
unexpected rows fail closed. No inbound Nostr collector was enabled and no
production confirmation was fabricated.

Pre-install installed-script SHA256:
`e0b79aae4887af8502697bfeb813b6c8d9868374e8deaf337957c00897388b45`.
The exact prior bytes are privately retained at
`/home/sat/.local/state/thermal-intel/runtime-backups/thermal_intel-v4-pre-journal-20260923.py`
(mode 0600). The staged change compiled, and all 28 existing confirmation
acknowledgement/future-plan tests passed against the staged *installed-v4*
module, not the source-only v5 runtime. The final installed SHA256 is
`d7f156d754ed5a5d168e2e8c2d2ed8bb1921498032345eafe4eb3cc377703014`.
An installed-CLI call with an invalid future receipt and a deliberately unused
DSN returned exit 1 with a sanitized future-receipt reason; it did not
construct a production journal connection. The shared installed journal
module hash stayed identical to repository source.

The shadow service was inactive during the atomic one-file swap; its timer
remained scheduled for 15:51 MDT. Verify the next natural shadow execution and
forcing-capture publication separately. Revert, if needed, by installing the
hash-checked private prior script over only this executable while the service
is inactive. This hardening is an ingestion prerequisite, **not** authenticated
operator transport, confirmed ventilation/shade outcomes, a model score, or
shadow graduation.
