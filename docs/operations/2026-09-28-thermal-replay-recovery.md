# Thermal replay-source recovery point — September 28

This is a same-host, private observational recovery point. It does not train,
promote, publish, actuate, or establish off-host disaster recovery.

The prior replay-source bundle predated the 07:49 MDT accepted artifact and
08:20 MDT forcing capture. The new `scripts/thermal-replay-bundle.py` reads
the installed runtime's exact 21-file revision list, refuses a mismatch with
`accepted.json`, captures the importable forcing-capture verifier and private
model/capture files, and writes a no-overwrite mode-0600 archive. The verifier
checks every archived member digest, inventory and accepted source revision.
Three focused tests cover private round-trip, revision mismatch and member
tampering.

The corrected private archive is
`/home/sat/backups/earthship-energy/thermal-replay-source-20260928T150544Z.tar.gz`,
SHA-256 `6c348c17815a10d45b010f94d981791de4e44b0f239a9b4528bc0e5976687ede`.
It contains 85 members including 59 forcing captures, with accepted revision
`53d96e5e9637d9c0c427afaffa35b29350243bf295ec6ed6f8a38f631d686396`
and accepted artifact SHA-256
`a9f608d638b5e450e4d0a6f53c7b887bbfdb74290f8d21b78364a313a5fcfc8a`.
Independent extraction in a private temporary tree matched the live accepted
artifact and selected installed runtime files byte-for-byte. Using only the
extracted runtime tree, all 59 archived captures passed the v4 semantic
capture verifier. The temporary tree and superseded, same-turn archive were
removed after verification; the earlier historical bundle was retained.

This establishes an up-to-date same-host replay evidence point, not a full
whole-host restore rehearsal or an off-host copy. It does not fix the model's
24-hour skill deficit, create action confirmations, or relax the shadow gate.
An automatic schedule, retention policy and off-host destination remain open.

## September 28 training-only runtime drift recovery

The subsequently installed selector-efficiency edit changed the 21-file
installed runtime revision to `30e91ec94f0ab2ae`, while the accepted model
still names `53d96e5e9637d9c0`. The original creator correctly refused to
represent those bytes as a coherent accepted-model bundle. The recovery tool
now has an explicit `--source-bundle` option: it verifies a private mode-0600
prior bundle, copies only its exact accepted code and capture verifier, then
reads current private model and forcing-capture evidence. It refuses if the
current accepted artifact no longer matches that included source revision;
there is no implicit stale-code fallback. Four focused tests pass, including
the runtime-drift recovery and mismatch refusal.

The source archive was the independently verified September 28 recovery point
above. A new no-overwrite, mode-0600 same-host bundle is
`/home/sat/backups/earthship-energy/thermal-replay-source-20260929T014041Z.tar.gz`,
SHA-256 `49794aaa48d1658217ea159a4cc3058b01ae57f138a1696430de3d0bf1e90b22`.
It contains 90 data members including 64 forcing captures, all under the
accepted `53d96e5e9637d9c0` revision. Its archive digest/inventory passed
verification, and an isolated extraction using only the bundled accepted
runtime semantically verified all 64 captures. The disposable extraction
tree was removed and absence checked. The prior archive remains intact.
This closes the post-optimization same-host replay staleness gap, not an
automatic backup schedule, retention/off-host disaster recovery, new model
accuracy or action-confirmation evidence.

## September 29 accepted-revision recovery

The September 29 accepted model names revision
`00611a5ef1e5b64347143b3dc04b423d519f7ccbd7bc237bd029b69b7ef2cd5a`.
The installed runtime instead hashes to
`483bf454f9a534a7cecab64fc18697082de511b3ae56465888e18fb2a292b054`
after the 11:12 MDT `forecast_intel.py` update, so a replay against the
installed tree correctly refuses to run. The pre-update helper was recovered
from the private exact-file rollback copy and combined in an isolated tree
with the installed thermal files; the resulting 21-file manifest exactly
matches the accepted artifact. The September 29 14:27 MDT forcing capture
replayed to the exact as-issued payload against that source. An
assumed-closed-vents diagnostic raised its modeled 12-hour hallway forecast
by 0.656°F; this is a counterfactual, not a vent observation or training label.

A new no-overwrite private recovery archive is
`/home/sat/backups/earthship-energy/thermal-replay-source-20260929T213455Z.tar.gz`.
The corrected verifier reports 100 members, including 74 forcing captures,
accepted revision `00611a5e...`, and full **archive** SHA-256
`a57b66249e3e518e7a56f4adc03ab47107f0528b58995a02145d260160b2dcd1`.
The verifier previously reported the digest of the last member because its
loop reused the archive-data variable; a regression test now checks the
reported digest against the actual archive bytes. The archive is same-host
only and does not by itself establish that all captured forecasts have skill
or authorize leaving shadow mode.

## September 30 distinct publication-runtime recovery

The current publication runtime is pinned to
`fe044985ffb79b2ee911b67ceb67061c8f0b46fb8c849a08ca93bc8df5e51e27`,
while the accepted artifact still names its earlier training revision
`00611a5ef1e5b64347143b3dc04b423d519f7ccbd7bc237bd029b69b7ef2cd5a`.
Exact as-issued replay already permits this separation through an explicit
runtime pin. The backup creator previously could preserve only training-bound
code, not declare the different current publication runtime accurately.

An opt-in `--publication-runtime-revision` now creates
`earthship-thermal-replay-evidence/v2`, binding that full caller-supplied
SHA-256 to the exact 21 included runtime files while separately preserving
the accepted artifact's original training revision. It never rewrites an
artifact or implies every archived capture uses that runtime. Default v1
creation/verification and its strict training-code match remain unchanged.
Both modes refuse source drift during snapshot; stale prior bundles cannot
be relabelled with a newer runtime pin. Member digests, exact inventory,
private no-overwrite publication and verified prior-source selection remain
required. This replay-archive v2 is unrelated to the still-gated journal v2.

The new mode was exercised on the actual quiescent household thermal state:

```sh
python3 scripts/thermal-replay-bundle.py create /home/sat/backups/earthship-energy/thermal-publication-runtime-20260930-fe044985.tar.gz --runtime-root /home/sat/openhab/scripts --publication-runtime-revision fe044985ffb79b2ee911b67ceb67061c8f0b46fb8c849a08ca93bc8df5e51e27
python3 scripts/thermal-replay-bundle.py verify /home/sat/backups/earthship-energy/thermal-publication-runtime-20260930-fe044985.tar.gz
```

The existing mode-0700 backup directory holds the mode-0600 archive with
107 data members and 81 forcing captures, SHA-256
`73b5ffa20cad4019c186c4c553c1591079b09c8dddcc42bc4942b7a27450f1aa`.
Independent extraction into one private owned temporary tree semantically
validated all 81 captures using only bundled runtime source. The latest
`20260930T103030Z-e12f318b331be0ce.json.gz` then replayed exactly under the
included publication pin; its original output SHA-256 is
`e12f318b331be0cefdd15c346675f93a55370bec230e4c5c03f09651164a8420`.
The verifier correctly reported that training and publication revisions differ.
The temporary extraction was removed; prior historical/training bundles and
the new complete archive are retained. No runtime, artifact, journal, Item,
timer, collector or control was changed.

This closes current publication-runtime preservation and the tested latest
replay recovery, not every historical replay, whole-host recovery, an automatic
backup schedule, off-host disaster recovery or advisory graduation. Off-host
copying remains deferred by the operator.

All 58 bundle/replay/publication-audit regressions passed, including malformed
pins/training identities, stale-source relabelling, manifest tampering,
concurrent runtime edits and reuse of a verified pinned prior runtime. Only
this turn's disposable synthetic test-fixture directories were cleaned up;
the retained household archive and all earlier recovery points remain intact.

## September 30 post-training source and artifact recovery

After the natural 07:35:36 MDT training completion, the accepted artifact
again matches the actual 21-file installed runtime revision `a4a68a17...`.
The existing strict v1 creator therefore produced a no-overwrite private
archive without needing a distinct publication-revision override:
`/home/sat/backups/earthship-energy/thermal-replay-source-20260930T133536Z-a4a68a17.tar.gz`.
Independent verification reports 108 data members, including 82 forcing
captures, and archive SHA-256
`e7e416aece2e49fdc964716c526e8870118514b3b7f5e891811ad74ca8ed4294`.
The archive is mode 0600 inside the existing mode-0700 same-host directory.

An isolated private extraction using only bundled source validated the new
accepted artifact, retained prior artifact, complete backtest report and all
82 captures. Restored accepted bytes exactly match production file SHA-256
`904c76e964f9b7c103918cc24e993b4fc766db5a86a0da2af6ea334fb06a4e75`,
and restored report metrics equal the accepted metrics. The latest archived
06:30 publication reproduced exactly, output SHA-256
`8a789fc48dd88b77e8bb92819bae43bb563e60bde08bcaf850b3385798e2548b`,
under the included full `a4a68a17...` pin. That publication embeds the **prior**
accepted artifact: it proves recovery of existing evidence, not publication
or accuracy of the newly trained artifact. The new artifact's first natural
publisher is still due at 08:30 MDT. The owned extraction was removed after
verification; real earlier backups and the new archive remain. No runtime,
timer, journal, control, label or notification was changed. Off-host copying
remains deferred, and whole-host recovery is not established here.
