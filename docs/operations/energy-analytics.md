# Energy analytics publication

`Solar_PV` owns the PostgreSQL reader and deterministic five-minute publisher.
OpenHAB owns one observational String Item, `Energy_Analytics_JSON`; earthship-ui
reads that Item through its existing REST/SSE connection. No component in this
path can command hardware or authorize an action.

The closed payload schema is `earthship-energy-ui/v1`. The publisher rejects
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

## Rollback

Disable the publisher timer first. If Item rollback is required, use only the
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
