# Energy analytics publication

`Solar_PV` owns the PostgreSQL reader and deterministic five-minute publisher.
OpenHAB owns one observational String Item, `Energy_Analytics_JSON`; earthship-ui
reads that Item through its existing REST/SSE connection. No component in this
path can command hardware or authorize an action.

The UI reader accepts the exact `earthship-energy-ui/v1` and
`earthship-energy-ui/v2` payloads. The implemented v2 publisher adds nullable
daily depth-of-discharge and estimated-EFC evidence, but v2 is not live until
the reader-first deployment is completed and the controller verifies the
publisher against persisted date, epoch, and quality evidence. The publisher rejects
payloads at or above 16 KiB and writes only
`PUT /rest/items/Energy_Analytics_JSON/state`. The browser treats payloads older
than 15 minutes, dated in the future, malformed, oversized, or on an unsupported
schema as unavailable. Missing evidence remains explicit `null` with its status
or reason; it is never displayed as a fabricated zero.

## Attended Item deployment

Use a private mode-0700 receipt directory outside Git. The configuration tool
backs up and mutates only the exact Item configuration; it has no Item-state
write operation.

```bash
node scripts/energy-analytics-config.mjs snapshot --receipt-dir "$RECEIPT"
node scripts/energy-analytics-config.mjs plan --receipt-dir "$RECEIPT"
node scripts/energy-analytics-config.mjs rehearse --receipt-dir "$RECEIPT"
node scripts/energy-analytics-config.mjs apply --receipt-dir "$RECEIPT"
node scripts/energy-analytics-config.mjs verify --receipt-dir "$RECEIPT"
node scripts/energy-analytics-config.mjs close --receipt-dir "$RECEIPT"
```

After installing and enabling `energy-ui-publish.timer` from `Solar_PV`, start
`energy-ui-publish.service` once and read back the exact Item through both
OpenHAB and the UI proxy. No OpenHAB rule, Thing, link, persistence policy,
actuator Item, or earthship-ui service restart belongs to this deployment.

For the v2 contract transition, deploy and verify the dual-version UI reader
before enabling the v2 publisher. Keep the publisher on v1 until the candidate
reader accepts a real read-only database-derived v2 payload. Then deploy the
writer and compare its output with the persisted date, bank epoch, and quality
gate before considering the transition live.

## Rollback

Roll back the publisher to v1 first, while the dual-version reader remains in
place. Disable the publisher timer before changing or restoring publisher
configuration. If Item rollback is required, use only the
closed receipt that performed the apply:

```bash
systemctl --user disable --now energy-ui-publish.timer
node scripts/energy-analytics-config.mjs rollback --receipt-dir "$RECEIPT"
node scripts/energy-analytics-config.mjs verify --receipt-dir "$RECEIPT" --expect rollback
node scripts/energy-analytics-config.mjs close --receipt-dir "$RECEIPT"
```

Retain the receipt and same-host database restore point as private evidence.
Off-host backup is intentionally deferred, so backup health remains
`Actionable`; this publication does not claim disaster recovery.
