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
