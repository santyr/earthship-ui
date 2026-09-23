# Bitcoin feed validation

Live read-only tracing found `BTC_USD_Price` linked to
`exec:command:BTC_Price:output`. That ONLINE Thing executes
`/etc/openhab/scripts/bitcoin.py` every 30 seconds, with a 15-second timeout.
Despite its suffix the file is Bash, and loads its Strike credential from
`/etc/openhab/misc/strike_api.env`. It is not the legacy CoinMarketCap helper
under `/home/sat/bin`. Do not rotate the live Strike credential as a substitute
for cleaning up the separate legacy credential.

Original live script SHA-256:
`314ad0a8ba04bce69e85e5247fa8e7a47cd8b8676ff6d3d9ef08dc8c7f83a9e4`.
An offline execution of only its parsing tail reproduced successful false
prices: text and JSON null emitted zero; -5 emitted -4. No HTTP request,
credential access, live Item write or manual rule invocation was used.

`openhab/scripts/bitcoin_price.sh` is a proposed replacement. It preserves the
existing endpoint and credential-file contract, rejects HTTP failure, limits
connect/total HTTP time to 3/10 seconds (inside the Thing's 15-second deadline),
requires exactly one BTC/USD quote, validates positive finite numeric or plain
decimal amounts, and rounds to whole dollars. It rejects amounts above the
safe integer rounding range and prices that round to zero. Numeric data is
never interpolated into executable awk code. Errors emit no stdout price.

24 offline tests passed in 0.20 seconds using a dummy credential file and fake
curl executable. They cover valid rounding, bad types/text/negative/zero/range,
ambiguous or missing quotes, malformed JSON and failed HTTP with a valid body.
Shell syntax and diff checks passed. This is not yet deployed.

Deployment must preserve the existing file owner/mode, retain a private exact
backup and require the pinned original hash before atomic replacement. Do not
change Thing configuration or credential contents. Verify the installed hash,
then observe a natural scheduled execution and numeric Item update. A failed
exec may leave the previous Item state visible; this parser correction alone
does not implement a feed freshness indicator or historical coverage evidence.
Those remain separate work. Keep the unchanged 24-hour arithmetic and candle
observation semantics established by the carry audit.

## September 11 deployment receipt

Commit `300fc160821afa4e34ee39d0d40d58d644251bd2` was merged and pushed to
origin/main. All 24 offline tests passed again on main. The operator supplied
the required ownership adjustment for the staged file; preflight confirmed
both original and replacement were regular files with owner/group 112:115 and
mode 0775. The original hash above and the exact backup were checked again
immediately before atomic replacement at 08:00:56 MDT, September 11.

Installed SHA-256:
`3650adbfddcd383c504dfbdfae0723fe31a7d5315adc4308f3dd5f369fb68bc4`.
Original bytes remain at
`/tmp/bitcoin-feed-release-afzV9N/original-bitcoin.py` (0600, private 0700 parent).
This is a temporary-host rollback copy, not a durable off-host backup. Rollback
must verify both hashes, preserve live owner/group/mode and use another atomic
replacement; do not copy the backup's private file permissions onto the live
executable.

No OpenHAB restart, credential edit, Thing/link/configuration change, manual
feed execution or Item write was performed. Natural scheduled updates logged
79320 at 08:01:15.618 MDT and 79398 at 08:01:45.609 MDT; both triggered normal
24-hour calculations. At 08:02:05 MDT the Thing remained ONLINE and REST showed
price 79398, percent change 2.788566 and corresponding fresh update timestamps.
The installed hash was rechecked. This completes parser deployment and natural
success-path verification, not historical feed-health coverage or an induced
production failure test. Invalid-response behavior remains verified offline.

## September 20 health-contract audit

The installed Bash script still matches the tracked replacement byte-for-byte
and the deployed SHA256 above. Its Strike credential remains externalized;
the legacy CoinMarketCap helper is a separate file, not this Exec Thing's target.
Do not conflate cleanup/rotation of the legacy credential with the live feed.

The live Exec Thing exposes output, input, exit, run, lastexecution, stdout and
stderr channels, but only output is linked (to the price Item). Inspection of
the installed 5.2.1 ExecHandler confirms stdout/stderr/output are published
separately and lastexecution is posted after output. It is an execution marker,
not an atomic successful-price receipt. Simply linking its timestamp or reading
the retained exit code beside an old price is insufficient to qualify historical
price freshness. A health design needs same-execution correlation and explicit
failure/timeout barriers; unchanged valid prices must still renew success.
No channel links, script, credential, polling schedule or production state were
changed by this audit, and no provider API request was made by the agent.

Source-only receipt draft: `openhab/transform/bitcoin_output_receipt.js` validates
canonical integer output and emits local transform receipt time. Errors become
null prices without copying stderr. Unchanged prices get new receipt times.
No links or Items are installed. Installed profile/event identity, unchanged
delivery, queue/restart behavior and failure/timeout expiry still need validation
before any health consumer or historical coverage claim. Existing price links
and API polling remain unchanged; focused VM tests verify the pure transform.

## September 20 observation receipt deployment

The draft above was hot-loaded at 13:58 MDT as file-owned String Item
`BTC_Output_Receipt_JSON`, with a separate file-owned link to the existing output
channel. The original managed `BTC_USD_Price` link remains unchanged. The live
profile configuration confirms `transform:JS`, `toItemScript=bitcoin_output_receipt.js`;
no reverse command/state scripts are set. This uses the installed profile contract
and the [official script transformation syntax](https://www.openhab.org/docs/configuration/transformations.html).
No API request, manual feed run, credential change or service restart was needed.

Natural receipts at 19:58:25 and 19:58:55 UTC were independently read from JDBC
`651/item0651`; the Item and link both report `editable:false`. The existing
Bitcoin calculation and pump rules remain IDLE/NONE. No ERROR/Exception was found
in the deployment log window. Focused transform and Item-definition tests pass.

Installed transform SHA256:
`d73c9fc54c9e12cbc53f5338550391d7deee775e6cf82e4555c465782c6bcaba`.
Installed Item file SHA256:
`c1d130224a60b93fa5301e4e5f91c58ef7c0252d9652e57928f77582c752458c`.
Both match Git source bytes. Destinations are `/etc/openhab/transform/bitcoin_output_receipt.js`
and `/etc/openhab/items/bitcoin-receipt.items`; neither existed before deployment.
Existing everyChange persistence captures each timestamped receipt, approximately
2,880 small rows/day at the unchanged 30-second polling interval.

This is observational collection, not a freshness consumer or qualified historical
coverage. Local receipt time is not provider quote time or a unique execution ID.
Natural unchanged-price delivery is now verified: price 81179 was retained while
receipt timestamps advanced from 1789934425473 to 1789934455431; the second row
persisted at 20:00:55.432178 UTC on September 20. This verifies this path delivers
and persists unchanged prices, not that every execution can always be correlated.
Queue/restart behavior and failure/timeout expiry remain unqualified.
Do not use a restored receipt to renew success automatically.
Rollback: move only these two newly installed files into a private directory outside
the watched configuration tree, verify the new Item/link disappear and the original
price link remains. Retain JDBC history; no original managed resource needs recreation.

## Home receipt-status consumer

The Home Bitcoin card now consumes `BTC_Output_Receipt_JSON` without extra
network polling. A valid local receipt matching the displayed price leaves the
card unchanged; unknown/malformed/future receipts, invalid output, mismatched
price and expired receipts produce a compact warning over the chart. Existing
price/candle observation semantics and 24-hour arithmetic remain unchanged.
The title explicitly describes local receipt time, not provider quote time.

The expiry threshold is 90 seconds (three ordinary poll periods). Existing
minute clock ticks and incoming Item events reevaluate it; timeout-only display
can therefore lag the threshold by up to one minute. This is presentation, not
a precise watchdog, alarm or control gate. A restored record retains its embedded
timestamp; reload does not renew it. Historical coverage, execution correlation,
physical/provider failure behavior and full-service restart qualification remain
separate. No provider failure, restart, synthetic live Item update or DM was used.

Verification: 84 focused unit tests, five browser cases covering Lenovo1340x800
and laptop1280x720 normal/unavailable layouts plus receipt expiry/error/unchanged
recovery, and production build passed. A read-only browser against local5190 at
Lenovo resolution showed a valid recent receipt, no warning, a198px chart, no
page errors and no write requests. The layout run additionally caught and fixed
a one-pixel Greywater text overflow at1280x720 and updated obsolete fixture
labels for the existing two-pump display. Build retains existing chunk warnings.

## Legacy CoinMarketCap helper credential cleanup

September 20: checked user/system service definitions, user cron, repository
references and live OpenHAB rule/Thing definitions for legacy helper consumers.
Only the distinct live Exec script was found in OpenHAB. Root cron could not be
read, so this is not proof the legacy helper is unused; manual callers also remain
possible. No provider request or credential validity probe was made.

The embedded key was removed from `/home/sat/bin/bitcoin.py`, preserving the
credential privately at `/home/sat/.config/hex/coinmarketcap_api_key` (0600, inside
a 0700 directory). The tracked replacement is `openhab/scripts/bitcoin_legacy.py`;
it also accepts an explicit `CMC_PRO_API_KEY` environment override. Its default
key loader rejects symlinks, nonregular files, foreign ownership, permissive modes
and invalid/oversize values without echoing the key. Original argument, endpoint,
quote selection and output behavior are retained, including legacy limitations;
this is not a new feed-validation implementation.

Installed SHA256:
`2484cbde6cd3d3a6b74f578b6035a98f94dbe3c6344b54da397cff3197228b35`.
Four offline tests cover private-file loading, environment override, invalid
configuration, missing/symlink/permissive files and both original output paths
with mocked HTTP. Actual installed import/key loading passed without HTTP.
The original script was temporarily preserved privately (0600) in
`/tmp/legacy-bitcoin-externalize-re3nk67f` (0700); it contained the old embedded
key and could not be committed or copied to public storage. Restoring it would
have reintroduced an embedded credential. That temporary copy was removed below.

September23 cleanup: after verifying the active helper and tracked replacement
still have the same SHA256 and the separate private key file remains mode0600,
the exact temporary backup directory above was removed. It is no longer a
recovery source; the installed replacement and private key remain. No live
polling configuration or credential value changed.

The live Strike script hash remains
`3650adbfddcd383c504dfbdfae0723fe31a7d5315adc4308f3dd5f369fb68bc4`.
No live feed, credential, rule or polling configuration changed. CoinMarketCap
provider-side rotation/revocation and cleanup of any historical copies remain
outstanding: externalization does not invalidate an already exposed credential.

## September 23 Java upgrade outage and recovery

At 06:36 MDT the host upgraded `openjdk-21-jre-headless` from
21.0.12+8-1~24.04 to 21.0.12.1+1-1~24.04.4. Immediately afterward, the running
OpenHAB JVM logged `Failed to exec spawn helper` on the scheduled Bitcoin command.
The output receipt became `price:null` while the price Item retained its last
value. The Exec Thing was disabled at 07:08; the logs do not establish who or
what disabled it. OpenHAB restarted at 07:11, but the Thing stayed disabled.

Read-only checks found the installed Bitcoin script still matched this repo's
SHA256 above, with the existing 30-second interval and 15-second timeout. At
07:59, the existing Thing was enabled through OpenHAB REST; it went ONLINE and
natural scheduled output changed `BTC_USD_Price` from 85456 to 85760 with a
matching valid receipt. The next scheduled run at 07:59:36 updated it to 85765
with another matching receipt. No script, credential or Thing configuration was
changed. For a recurrence after a Java package upgrade, check the JVM's process
spawn errors and Thing status before attributing a retained price to the provider.

Later September23 read-only follow-up: the Thing remained ONLINE and
BTC_USD_Price continued changing. Over the preceding two hours,183 of184
persisted output receipts had a numeric price. One `price:null` receipt was
followed by a valid value on the next 30-second poll; the latest receipt age
was approximately30 seconds. This is a recovered transient sample, not a
stuck-price condition. The incidental `BTC_Price` Item is NULL; the UI's active
price source is `BTC_USD_Price` with `BTC_Output_Receipt_JSON` freshness.
