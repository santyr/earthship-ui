# Home and Energy chart recovery — October 19

Home started all history requests during mount, before asynchronous configuration/client initialization completed. Its helpers stopped after ten 300 ms retries. Delaying configuration by 4.5 seconds reproduced all four empty sparklines, zero persistence requests, and outdoor high/low equal to the current temperature. The numeric live snapshot arrived afterward, but history did not retry until the five-minute timer.

Home now starts its existing history batch when the shared client-ready store becomes true. It retains the normal refresh schedule and the existing Denver-calendar extrema calculation. The same live delayed-start probe then made nine persistence requests, populated all four plots, and showed a measured outdoor high of 71°F and low of 33°F instead of current/current.

Energy's history component waited for client readiness, but a failed initial request could leave the battery plot unavailable for its 30-minute refresh interval. Transient transport/time-out failures now retry after five seconds, with exponential backoff capped at one minute. Validation errors retain their separate handling. Successful plots stay visible during retries, and component destruction cancels the retry timer. A live Chromium probe deliberately returned HTTP503 once for both battery and PV history: both plots recovered without reloading after 5.352 seconds, with two requests per series and no page errors.

The uncommissioned Sensors tab and active page route were removed. Old ventilation-page links resolve to Earthship. Backend sensor support remains available for future hardware.

Verification: 179 focused UI tests passed, including the reproduced missing Energy retry, history rendering/preservation, daily extrema, routes and rendered navigation. The production build and live Chromium probes verify the deployed source. New end-to-end fixtures cover delayed client startup and transient history errors. The combined local Vite/browser test harness exceeded its diagnostic process allowance; its failed setup is not counted as a passing browser suite. Direct live probes ran successfully in a separately admitted Chromium. Private captures and exact patch/preimage receipts retain the reproduction and deployment evidence.

No thermal fit, resource-policy change, equipment command or OpenHAB restart accompanies these UI repairs.
