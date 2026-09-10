# Atomic BMS disabled installation runbook

Authority: approved atomic observation design43ccb08, Hexmem8691, source
integration487eada and reviewed descriptor d12f4c3. This runbook installs only
new observational resources. Source enablement, natural-event qualification and
reader migration are later gates. Task82 remains held.

## Verified primitives and constraints

OpenHAB5.2.1 REST Item PUT is an upsert. Use ManagedItemProvider.add after
registry/provider absence checks instead: AbstractManagedProvider.add rejects
preexisting managed entries and has no update branch. This is add-only API
semantics, not a claim of a global distributed transaction across providers.
Reserve these exact new names for this operation; stop on any conflicting
definition and never overwrite it. ManagedItemChannelLinkProvider.add provides
the corresponding no-update operation for the two new links.

The one-shot action is locally preserved at
`.worktrees/bms-soc-evidence/.superpowers/sdd/bms-resource-install-action.js`.
It resolves five scoped registry/provider services, permits only preflight,
items and links phases, and uses fixed descriptor names. It never calls an Item
state update, command, provider update/remove, persistence, notification or
network API. Its Node VM deny-by-default tests had genuine missing-source RED
followed by ten passing cases: no-write preflight, exactly three new Items,
collision rejection, partial add failure, exactly two links, refusal to link an
enabled Thing, unknown-phase refusal, missing service, existing link collision
and partial link-add failure. Service references are always released.

The phase runner reuses the reviewed triggerless diagnostic lifecycle: unique
rule UID, full submitted-DTO ownership comparison, ambiguous-create readback,
fresh correlated log receipt and verified removal of only the owned temporary
rule. It never automatically retries an action. A partial phase failure requires
inspection of its CREATED log entries and current definitions, not blind replay
or deletion of newly collected history.

## Ordered execution and verification

1. Refresh the exact target inventory. All three Items, two Things, two links and
   `hex_bms_soc_evidence` must be absent. Snapshot existing rule definitions,
   persistence, existing raw/scale Thing configurations and poller configuration.
   Verify installed transformation file and registry hashes against the reviewed
   source. Preserve snapshots privately; print only hashes.
2. Run the preflight phase. It resolves the installed providers and checks
   collisions without adding anything. Require its fresh `phase=preflight
   created=0` receipt and temporary-rule removal before proceeding.
3. Run the items phase once. Require `phase=items created=3`, removal of the
   temporary rule and exact String Item name/type/label/category/group/tag
   readback. No state has been synthesized by this phase.
4. POST each exact new Thing DTO from the manifest without the manifest-only
   `enabled` field. Require201 creation. No links exist at this point. Immediately
   PUT text/plain `false` to `/things/<newUID>/enable`; poll the same Thing until
   status detail is DISABLED. Verify bridge, read register/type/transform and
   absence of configured writeStart/writeType/writeValueType. Never change the
   existing poller or send a REFRESH command. Stop before adding any link if a
   Thing cannot be confirmed disabled.
5. POST an inert observer rule with no triggers, the exact reviewed action and
   no conditions. Require201. Disable only that new rule with POST text/plain
   `false` to its `/enable` endpoint; verify `status.statusDetail=DISABLED`
   in the rule DTO (`status.status=UNINITIALIZED`). Add the reviewed six triggers by
   updating only this newly created, ownership-verified rule and confirm that
   it remains DISABLED. This avoids any automatic execution during creation.
6. Run the links phase once. The action independently requires both new Things
   to report DISABLED, all three expected String Item definitions and both
   links to be absent. Require `phase=links created=2`, temporary-rule removal
   and exact two String-channel/default-profile link readbacks.
7. Re-read all new definitions and disabled postures. Compare the baseline
   hashes for every preexisting rule, persistence, raw/scale and poller config.
   Only the allowlisted new resources may differ. Record source/descriptor hashes,
   receipts and the completed disabled installation in the canonical tracker.

The local runner command is `python3 -B .superpowers/sdd/bms-resource-install-run.py
<phase>` from the preserved BMS worktree. Run only the explicit phase at its
ordered step; no generic deployment loop or historical replay is authorized.
The observer is not manually run, and its readers are not changed by this runbook.

## Stop and recovery

Creation collisions, mismatched hashes/definitions, missing service/receipt,
unexpected write configuration, enabled linked Things, or drift in preexisting
resources stop progression. Preserve evidence and inspect the exact created
targets. Disable only owned new sources/observer if their posture is uncertain.
Do not restore the superseded observer, rewrite global persistence, reset learning,
delete history or touch existing physical controls as rollback.

## Installation receipt, September 10

Disabled installation is verified: three exact String Items (all still NULL),
two read-only Things, two default-profile String links and the exact reviewed
observer action with six triggers. Both Things and the observer report
`statusDetail=DISABLED`. No observer manual execution or source enablement occurred.
Ten add-only helper VM tests passed immediately before installation.

Fresh correlated installer receipts:

- Items: `hex_bms_install_1dd916adc1c04488961133a0562810ca`, created=3.
- Links: `hex_bms_install_af60e8ed2e194becb6ae9b13f990eeee`, created=2.

Both temporary rules were removed and final inventory found no remaining probes.
Private baseline `/tmp/bms-disabled-install-7i8fsb8m/baseline.json` was compared
with final readback: every preexisting rule, Item definition, link, JDBC
persistence definition and existing raw/scale/poller configuration was unchanged.
This temporary baseline is not a durable backup. Observer source SHA-256:
`be102074e8ac2640e747c71e9375436fc97d5a25f436a444333aa3daba31093e`.

Execution corrections: the initial rule-disable PUT returned405, leaving the
new rule triggerless. Version-matched [RuleResource source](https://github.com/openhab/openhab-core/blob/5.2.1/bundles/org.openhab.core.automation.rest/src/main/java/org/openhab/core/automation/rest/internal/RuleResource.java)
confirmed POST. POST succeeded; the first assertion incorrectly tested the main
status rather than statusDetail. Links were added while the observer remained
disabled and triggerless and both Things were disabled, before adding the final
triggers. This deviated from the documented ordering, not the disabled-source
safety boundary. Direct readback confirmed DISABLED before the ownership-checked
trigger update and again after it. No creation or installer phase was replayed.

Do not remove these deliberately staged NULL Items/disabled resources as dead
configuration. Natural-event qualification and reader migration remain open;
installation does not establish usable source-history coverage.
