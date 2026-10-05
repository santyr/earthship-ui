# Weather-health Group cold file candidate

`items/weather-health-group.items` is staged and uninstalled. Production
`gWeatherHealth` remains managed. This continues the approved file-first
migration with the existing cold Group transfer approach.

The Group is an unlinked, untagged plain `Group`, label `Weather Health`,
NULL state, no parent Groups, metadata, aggregate type/function or JDBC identity.
Its six members remain separately managed:

| Member | Original JDBC identity |
| --- | ---: |
| SkyCondition_Diagnostic | 541 |
| SkyCondition_LastEval | 540 |
| WeatherData_HealthStatus | 535 |
| WeatherData_WH31E_AgeSeconds | 532 |
| WeatherData_WH32B_AgeSeconds | 534 |
| WeatherData_WH65B_AgeSeconds | 533 |

The live inline-rule census finds no literal Group reference. That census is
a review aid, not proof that dynamic external consumers do not exist. The
member definitions, metadata, state publishers, links and histories must retain
their original identities and semantics.

A REST Group deletion removes managed member references; the previous
`gForecast` native rehearsal demonstrated this. Use the stopped registry path:
verify and back up the current registry, remove only the exact selected Group
record, install its sole file definition, restart and verify all six references.
Managed rollback removes the owned file while stopped and restores the exact
original Group record. Never edit JSONDB behind a running production registry.

`scripts/weather_health_group.py` supplies the exact stopped-copy transformer
and descriptor/membership guards. Sixteen focused tests cover unchanged
member/unrelated records, changed Group behavior, extra/missing/duplicate members,
existing-provider collisions, non-boolean operations, and a Group link rejected
before broader preflight or backup. The native file provider represents an
absent icon as category `null`, while the managed record uses an empty string;
only those two values compare equally, with every nonempty category rejected.
The initial tests fail before implementation;
the descriptor and linked-scope regressions fail before their fixes.

The native qualifier is `scripts/qualify-weather-health-group.py`; its only CLI
mode writes a private qualification report. It has no production apply path.
Two owned disconnected OpenHAB/PostgreSQL containers receive seven selected
Item records, member metadata, private API users and all six copied native
history prefixes. The fixture contains no Things, links or rules. Its generated
JDBC password is installed mode 0600; private copies remain outside Git. Native
Group/state/membership, full fixture member descriptors/providers and original
history bytes are checked through managed baseline, stopped file handoff,
full restart, original managed rollback and final file handoff. Binding-derived
member fields and whole-household recovery retain their separate scopes.

The staged file SHA-256 is
`b2eae0fe035a099fa079d0854cd866ecf9986836a2ff7a1b5d5ecfb043dd762f`.
Native qualification now passes its complete terminal run, including five
distinct stopped/restarted container processes and all original member prefixes. Production
source/provider ownership and restart qualification have not changed. No file
ownership declaration is added before an actual attended production cutover.

The fixture investigation retained its failed-run evidence. It found a missing
bootstrap JSONDB directory and an incompatible helper timeout argument. A
native permission probe then showed that cold copies owned by uid 1000 at mode
0600 cannot be read by the capability-restricted root fixture; mode 0644 copies
are readable. Only credential-free definition copies use that mode, inside a
mode-0700 host directory. Credentials remain mode 0600 and capabilities remain
dropped. Bounded cold-start authentication and read retries reuse the existing
Hex token, with status-code evidence; no credential rotation is required.

The existing approved production restart still requires host authentication.
A real cold transfer needs an authenticated stop/start, fresh private recovery
material, exact stopped preimages, member history/provider checks, unchanged
protected definitions and fresh native telemetry. Operator approval already
exists; this candidate does not bypass the host authentication policy.


## Completed native qualification

The sealed mode-0700 capsule is `/home/sat/.local/state/openhab-config-migration/weather-health-group-20261005-w6dvsfyp`. It retains 35
mode-0600 evidence files and their hash manifest, including the seven Item
records, selected metadata/private users, six recoverable CSV archives, exact
source snapshots, red/green test receipts and all five native checkpoints.
The six original history prefixes contain **1,670,545 rows** in total.
Their IDs, row counts, cutoffs and full ordered CSV digests remain unchanged
through every fixture phase and the final read-only production check. The
production Group still has no JDBC identity; all six references remain intact.

The final native check preserves every production Item/rule/Thing/link
definition, all 56 declared file-source hashes and PID 1696. The borrowed guard
is supplemented with the Item it ordinarily excludes, so this qualifier covers
all production Item definitions. No production mutation occurred. Every
allocated fixture and anonymous volume is removed by its verified ownership
label; cleanup independently confirms each container is absent.

A real cold production transfer remains pending host-authenticated stop/start
and fresh whole-household recovery checks. The candidate is uninstalled and
production ownership remains managed.

Final independent review verifies all eight public snapshots and 52 sealed
evidence files across this Group and the second thermal six-hour outcome,
with no Critical/Important findings. Both prior Minor issues are resolved.
The frozen repository suite passes **4,175 tests**, with **10 skips** and
**91 subtests**; all 16 guards pass independently. These checks qualify the
staged candidate and its isolation, while actual cold ownership stays pending.
