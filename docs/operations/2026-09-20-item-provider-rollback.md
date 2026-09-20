# Observational Item provider rollback verified

An attended file-to-managed-to-file round trip succeeded for
`Energy_Analytics_JSON` on September 20. This qualifies the rollback path for
this Item, not protected controls or the whole installation.

`scripts/rehearse-energy-item-rollback.py` paused only the five-minute publisher,
waited for its service to finish and saved the current Item, rule definitions and
history prefix. The exact installed file was moved outside the watched directory;
registry absence was confirmed before creating the managed definition. Its exact
persisted state restored before publication. The managed Item was then deleted,
absence confirmed, and the original file moved back. File-provider state again
restored exactly before a real-data publication succeeded.

Readback confirms JDBC mapping 609 unchanged, original history count/fingerprint
unchanged through the captured maximum timestamp, all rule definitions unchanged,
and source bytes unchanged. Final provider is file-owned; the publisher timer is
active again. No synthetic state, hardware command, rule runnow or server restart.

Private before/intermediate/verified receipts:
`/tmp/energy-item-rollback-y1imrnj5`.
The existing first-cutover receipt remains separate and is not overwritten.

This supersedes the earlier statement that actual Item rollback had not been
exercised. Full OpenHAB restart, clean-system recovery, JDBC strategy provider
transfer and protected-control rollback remain unverified. Do not generalize this
single unlinked observational String Item's results to those broader operations.
