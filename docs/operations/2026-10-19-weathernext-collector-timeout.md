# WeatherNext collector read timeout

Two natural collector runs failed on October 19, at 00:36:47 and 01:37:45 MDT,
with the typed application reason ReadTimeout. Their parent services exited 1;
the later shadow inference run succeeded. Diagnosis used only structured result
fields projected in memory. No raw journal records were retained.

The transport imposed a fifteen-second read timeout inside an existing
75-second total acquisition deadline. Earth Engine sometimes needs longer before
returning response headers. Reads now use the remaining total acquisition time;
connect timeout stays at most five seconds. The exclusive process timer still
interrupts all requests and progressing response reads at the original deadline.
No SDK retry, endpoint, billing rule, byte/request cap, collection horizon or host
resource safeguard changes. Failed CLI results add only numeric elapsed time,
request count and transferred bytes, without arbitrary upstream exception text.

## Verification

- Slow-computation and missing failure-diagnostic regressions failed before the
  edit and passed afterward. Remaining-budget exhaustion still refuses a second
  request. Existing real progressing-response deadline coverage remains.
- All **214 pinned WeatherNext tests passed in 8.318 seconds**, with all fourteen
  retired worker/evidence modules blocked during discovery and execution.
- All **36 affected native tests passed in 7.99 seconds**.
- Tests used isolated export `d50e770ccdf3cf4ed8d43d8978ed94d31dba9ab4`.
- The six installed/current resource launcher files match byte-for-byte.

A bounded live diagnostic collection used the existing service identity/profile,
unchanged shared admission and the strict collection leaf: 20% CPU, 256 MiB RAM,
zero swap, 24 tasks and 90-second runtime. It collected the October 19 00:00 UTC
initialization, completed at **08:14:01.973570 UTC**, in **56.094 seconds**, using
**7 requests**, **1,271,993 bytes** and **74,572 KiB peak RSS**. Noncommercial
verification passed. All **360 hours / 12 bands / 4,320 values** were present.
Reconstruction from retained original API responses exactly matched every point
and the snapshot identity, without another cloud request.

Snapshot SHA256: `032f47a82e2f645a9bc5dbc1ee0008adad6c6c5a81a28f9ae506233dbe48b8bb`.
The original diagnostic archive and typed receipts remain private in the existing
execution directory. This diagnostic did not modify the live archive, fit a
model, publish household forecasts or authorize equipment. It establishes source
collection and integrity; it does not establish local predictive skill.

## Collector-only operational source pin

The optional repository drop-in
`deploy/weathernext-ingest.service.d/source-release.conf` reads a separate private
`~/.config/earthship-weather/collector-release.env`. That file contains only
`EARTHSHIP_WEATHER_COLLECTOR_CODE_ROOT`, naming an owned immutable tested release.
Existing runtime.env still supplies the interpreter, archive and credential
configuration. The override changes only the two source-root references in the
collector ExecStart command; every admission/collection argument is preserved.

Install the source release and private source pin before loading the drop-in.
Use a complete hash-verified read-only release, validate the effective command and
unchanged safeguards, then run only the collector for qualification. Record the
actual source/release manifest, systemd invocation, resource leaf, retained/live
archive result and timer state in a private deployment receipt. A successful
manual invocation does not imply a natural timer invocation has occurred.

Shadow inference/training continue using their existing shared runtime source
root and current UI contract. This prevents a collector fix from prematurely
activating the separately prepared v2 shadow cohort and frontend. Existing model
receipts and old source evidence are not relabelled.

The transport is also a protected native-source dependency. Its changed bytes
require the final new source closure and fresh native release fitting; existing
native model receipts are not reusable under the change. Source counts remain
81 native-base and 76 raw-shared files. No native model release is activated by
this collector-only maintenance. Full qualification, provider retirement and
attended production cutover remain unfinished. The separate operator/recovery
removal proposal remains unapplied pending its owner decision.
