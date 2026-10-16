# Historical source fixtures

`greywater-durable-recovery-4c34780e.js.txt` retains the exact previously
qualified greywater source, SHA256
`4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b`.
It was extracted from `eb4cf79^:openhab/rules/southoutlet-cycle-current.js`.
The offline tests for that release use these immutable bytes instead of the
newer canonical daylight candidate. This is a test input, not a deployable
selection, current owner definition or new qualification. Production source
paths and release/probe pins remain unchanged and reject candidate drift.
