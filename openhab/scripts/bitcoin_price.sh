#!/usr/bin/env bash
# Strike BTC/USD feed. Install at the existing exec path only after review.
# Keep stdout numeric-only on success; failed requests never emit a price.
source /etc/openhab/misc/strike_api.env || { echo "Error: strike_api.env missing" >&2; exit 1; }
api_key="$STRIKE_API_KEY"
[[ -n "$api_key" ]] || { echo "Error: STRIKE_API_KEY empty" >&2; exit 1; }

response=$(curl --silent --fail --connect-timeout 3 --max-time 10 \
  -H "Authorization: Bearer $api_key" \
  -H "Accept: application/json" \
  "https://api.strike.me/v1/rates/ticker") || {
  echo "Error: BTC rate request failed" >&2
  exit 1
}

price=$(jq -er '
  if type != "array" then error("shape") else . end
  | [.[] | select(type == "object")
      | select(.sourceCurrency == "BTC" and .targetCurrency == "USD")]
  | if length != 1 then error("count") else .[0].amount end
  | if type == "number" then .
    elif type == "string" then
      if test("^[0-9]+(\\.[0-9]+)?$") then tonumber else error("decimal") end
    else error("type") end
  | if (isnan or isinfinite or . <= 0 or . > 9007199254740990)
    then error("range") else (. + 0.5 | floor) end
  | if . > 0 then . else error("rounded zero") end
' <<< "$response" 2>/dev/null) || {
  echo "Error: invalid BTC rate response" >&2
  exit 1
}
printf '%s\n' "$price"
