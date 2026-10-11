# Household snapshot foundation

This is the first implementation stage of PR #3. Its offline assembly has
no transport, timer, request sender, planner or physical authority. A separate
read-only collector is described in `household-source-capture.md`.
Existing forecast workers, UI layouts and owner rules are unchanged.

The pure adapters consume exact original BMS SoC, native MPPT60 daily Wh
counter and native-v2 temperature query packets. Raw-source SHA256 and
expected epochs are explicit inputs. Existing source-specific validators
remain authoritative. Temperature packets are replayed from original raw
receiver rows; selected scalar temperatures cannot substitute for them.
Receipt timestamps are not relabelled as sensor measurement timestamps.
The counter adapter does not claim PV power or a qualified completed day.

`HouseholdSnapshot v1` freezes energy, thermal, weather and water domains.
The first supported observations are battery SoC, PV-day Wh, hallway air,
north-wall mass and outdoor temperature. Water inventory stays unknown.
Other domain fields and forecast-artifact adapters remain future additions.
Completeness means the declared profile's source inputs satisfy its explicit
age/skew policy. It does not qualify a forecast, authorize an action, claim
statistical independence or declare a planner ready. Original qualification
remains visible even when a later snapshot withholds an expired value.
Snapshot getters return fresh copies; identities are canonical SHA256.

The registry is a projection of `openhab/managed-resources.json` and
`openhab/file-config/ownership.json`. Explicit `householdContract` metadata
records the existing owner bindings, protected actuators and legacy ingress.
It changes none of the existing OpenHAB apply/rollback plans. Every capability
has planner authority `none`, live availability `not_assessed`, and explicitly
incomplete safety-input enumeration. Owner rules continue to enforce their
actual live checks. No common request v2 migration is implemented here.

## Offline use

The companion analytics package must already be on `PYTHONPATH`, as in the
existing forecast tooling. There are no additional dependencies.

```bash
PYTHONPATH=openhab/scripts:/home/sat/Solar_PV/analytics/src \
  python3 openhab/scripts/household_snapshot.py --input /private/inputs.json
```

The input and optional original receipt must be owned regular files with
mode 0600; symlinks are refused. Input size is at most 1 MiB, with at most six
sources. The sealed output is at most 256 KiB and goes only to stdout. Use
shell redirection into a private file if an archive is desired. Nothing is
installed automatically.

The closed input schema is:

```json
{
  "schema": "earthship-household-inputs/v1",
  "as_of": "2026-10-11T12:00:00+00:00",
  "created_at": "2026-10-11T12:00:00+00:00",
  "policy": {
    "requirements": {"battery_display": ["battery_soc"]},
    "max_age_seconds": {"battery_soc": 120},
    "max_skew_seconds": 60
  },
  "sources": [{
    "kind": "battery_soc",
    "source_role": "battery_soc",
    "source_identity": "original persisted receipt identity",
    "expected_epoch": "the original canonical source UUID",
    "expected_sha256": "SHA256 of the exact original UTF-8 raw string",
    "persisted_at": "2026-10-11T11:59:59+00:00",
    "raw": "the original evidence JSON string"
  }]
}
```

This illustrates fields, not a valid synthetic credential or source receipt.
`pv_day_wh` uses the same context. `native_temperature` uses an explicit
`air_temperature`, `mass_temperature` or `outdoor_temperature` role, null
`persisted_at`, and its original native query packet. Native packet policy,
stream and hardware epoch remain bound to original receiver evidence and the
reviewed household role’s declared model, sensor ID, range and receipt lifetime.
Missing raw evidence is null with a null digest, never a fabricated value.

For replay, use the original source checkout and companion validator bytes:

```bash
PYTHONPATH=openhab/scripts:/home/sat/Solar_PV/analytics/src \
  python3 openhab/scripts/household_snapshot.py \
  --input /private/inputs.json --expect /private/original-receipt.json
```

The command refuses changes to original raw strings, frozen clocks, temporal
policy, ownership manifests, source-validator/runtime bytes or code revision.
It rechecks input/runtime identity before emitting a result. Malformed input
errors do not echo source strings, credential-bearing fields or private paths.
Replay fixtures must retain original inputs separately; the compact receipt
contains references and derived values, not a replacement authoritative history.

Automatic production collection, accepted model-artifact references, additional
water sources, arbitration and the planner remain later stages. Pure typed shadow
intents and permanently disabled translation are defined in the contract stage.
This foundation does not graduate the provisional thermal model.
