# AC evidence JDBC exclusion: rehearsal and live file hot reload

September 23, 2026. The file-owned JDBC strategy now excludes
`Inverter_AC_Evidence_JSON` from automatic `everyChange` while retaining
`restoreOnStartup` for that Item. This prepares an explicit immutable writer;
it does **not** create or enable the AC evidence Item or rule, nor authorize AC
load accounting. Existing `Power_Evidence_JSON` and forecast selectors remain
unchanged in meaning. The prior installed file SHA256 was
`88e2959ea4cf2b5345c39b986d0f5c8bdee627ae27cc4c4a78014733203b8949`;
the candidate/current file SHA256 is
`39299b96ec22d1e4860ead09f7b85e23f09f89b071e256a6a0609dda575c57a9`.

The source candidate was rendered from the complete live file-owned strategy
DTO with exactly two selector additions. A networkless OpenHAB 5.2.1 run loaded
the exact candidate DTO and completed two file→managed→file provider
roundtrips. Its owned container was removed. A separate disconnected
OpenHAB 5.2.1/PostgreSQL 16 run repeated the full five-checkpoint test:
ordinary synthetic updates to the new AC Item produced no JDBC rows, while a
positive Number control persisted and the existing power exclusion held at
every checkpoint. The exact explicit-writer overload added one immutable AC
history row without changing the current Item state. After a different JVM
started, that row remained the only AC history row and restored the Item state.
The existing power writer, forecast REPLACE/future-series behavior, historical
prefixes, change-only policy, four provider-gap controls and restore checks
also passed. Both disposable containers and their database were removed. No
synthetic state was sent to production.

For the live hot reload, an exact prior-file backup was staged privately in
`/tmp/ac-jdbc-rollback.ejjMHO` and the new canonical source was installed at
`/etc/openhab/persistence/jdbc.persist` at 14:40:16 MDT. REST then returned
the exact full DTO with `editable:false`; the ownership inventory reported
zero issues. In the 14:40 MDT minute, all ten sampled original-binding AC
observation changes had matching JDBC rows. The existing immutable power
stream had 42 valid v1 rows in the checked reload window, with no same-epoch
sequence gap or epoch transition. Targeted JDBC/strategy errors: zero. This
is bounded collection evidence, not a proof that every Item had uninterrupted
persistence. No service restart, hardware command, Thing/link change or
evidence-rule activation occurred. After verification, the hash-checked
temporary backup was removed; the previous source remains recoverable from
the preceding Git commit.

The live strategy has no new AC evidence Item to restore yet. Before enabling
the rule, install the file-owned Item, verify this exclusion remains exact,
qualify real original-event provenance and fault/recovery behavior, and deploy
a strict separate Solar-PV reader with topology-period barriers. Do not use
change-only AC observation history as an authenticated evidence stream.
