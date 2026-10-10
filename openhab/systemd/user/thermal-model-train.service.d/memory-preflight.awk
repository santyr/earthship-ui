# Exit 1 skips this scheduled job; never invoke the trainer from this guard.
BEGIN { valid = 1 }
$1 == "MemAvailable:" || $1 == "SwapTotal:" || $1 == "SwapFree:" {
    if (seen[$1]++ || NF != 3 || $2 !~ /^[0-9]+$/ || $3 != "kB") valid = 0
    value[$1] = $2 + 0
}
END {
    ready = valid && seen["MemAvailable:"] == 1 && seen["SwapTotal:"] == 1 && seen["SwapFree:"] == 1
    ready = ready && value["MemAvailable:"] >= 3145728 && value["SwapFree:"] <= value["SwapTotal:"]
    ready = ready && value["SwapTotal:"] - value["SwapFree:"] <= 131072
    exit !ready
}
