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
