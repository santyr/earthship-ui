# Source-backed thermal policy preregistration

`thermal_policy_registration.register_policy(directory, policy, development_sources)`
seals `earthship-thermal-policy-registration/v1` in an owned 0700 directory.
The caller supplies the versioned numerical policy and complete original source
packets, rather than a table of manually entered baseline errors.

Each packet contains `origin_path`, the original persisted `publication`,
`horizon_hours`, the qualified native `outcome`, and the original
`recent_cycle_grid`. The registrar reads and validates each original archive,
recomputes its source-bound baseline errors, and requires an exact match with
the policy's development inputs. Development hardware epochs must match the
frozen candidate. Different development model revisions can supply baseline
errors; they do not become pooled release scores for that candidate.

The actual registration clock must follow declaration and precede both release
intervals. There is no supplied registration-date or active-mode argument.
The clock is checked again after verification and immediately before publishing
the receipt, so a holdout starting during the work refuses registration.

Complete original captures are copied into private immutable storage, with the
native outcome and comparator receipts retained in the registration file.
An atomic exclusive publication creates an owned 0600 receipt. Identical retries
preserve the original timestamp; changed content cannot overwrite it. Failed
attempts can leave source files but never a usable registration receipt.
The source index, origin count and total decoded origin bytes are bounded.

`read_registered_policy(path)` checks the private storage, exact schema and
content digest, then replays the source packets and threshold derivation. A
cached policy alone is insufficient: missing originals, changed receipts,
unsafe modes and path escapes refuse replay even if an outer digest is recomputed.

This operator-owned archive is an audit record, not a cryptographic timestamp
service or a protection against an owner who rewrites their entire history.
Before a real holdout starts, retain its receipt digest in the release review
record and a separately dated repository/CI record. Copying a policy into a new
location never establishes a new retrospective registration.

Registration does not qualify weather inputs, conditioning, coefficient
stability, predictive skill or action effects. It always records
`release_authorized: false`. Candidate artifact/runtime metadata still requires
verification by the combined qualification layer. No genuine production policy
has been registered from the legacy October 7 evidence, which remains development
only and lacks the new origin/runtime bindings. Activation remains closed.

The source-only implementation changes no installed service, fitting job,
publication or household control. Full verification runs in hosted CI; local
checks use one low-priority process limited to 25% CPU, 768 MiB RAM, zero swap,
48 tasks and low I/O weight.
