#!/usr/bin/env python3
"""openHAB mission-critical sanity checker (deployed 2026-07-14).

Runs OUTSIDE openHAB (systemd user timer, every 10 min) so it still fires
when openHAB itself, the rule engine, or persistence is broken — the failure
modes the in-system watchdogs cannot report. Alerts via the same Nostr DM
path as hex_bms_comms_watchdog (rate-limited per key, recovery notices).

Checks:
  1. REST API reachable
  2. Critical rules in their expected state (incl. southoutlet staying
     DISABLED during the interim — alert if someone enables it early)
  3. Value sanity ranges on mission-critical items
  4. Algorithm cross-verification: BMS_Temperature recomputed from the raw
     register (x0.01 - 273 C -> F), BMS_SOC recomputed from raw x 10^sf
  5. Runtime estimator consistency (basis vs battery current; smoothed > 0
     whenever basis says an estimate is active)
  6. Freshness: BMS_SOC_LastUpdate, Schneider stamps

Alert prefix is a magnifier so DMs are distinguishable from the watchdog's.
State: ~/.local/state/openhab-sanity/state.json
"""
import json, math, os, subprocess, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

BASE = "http://127.0.0.1:8080/rest"
ENV_FILE = os.path.expanduser("~/.config/hex/openhab.env")
NOTIFY = "/etc/openhab/scripts/nostr_notify.sh"
STATE_DIR = os.path.expanduser("~/.local/state/openhab-sanity")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
RATE_S = 30 * 60

RULES_EXPECTED = {
    # uid: (status, detail) sets that are OK
    "hex_bms_soc_scale": {("IDLE", "NONE"), ("RUNNING", "NONE")},
    "hex_bms_comms_watchdog": {("IDLE", "NONE"), ("RUNNING", "NONE")},
    "hex_schneider_safety": {("IDLE", "NONE"), ("RUNNING", "NONE")},
    "hex_bms_ttd_smooth": {("IDLE", "NONE"), ("RUNNING", "NONE")},
    "hex_dcdata_native_scale_side_by_side": {("IDLE", "NONE"), ("RUNNING", "NONE")},
    "hex_mppt60_native_quantity_scaler": {("IDLE", "NONE"), ("RUNNING", "NONE")},
    "UpdateBatteryIcon": {("IDLE", "NONE"), ("RUNNING", "NONE")},
    # Re-enabled 2026-07-15 in curtailment-only mode (cycles only at
    # SoC>=99 + Float + strong sun). Full cycling returns at full-bank.
    "hex_southoutlet_cycle": {("IDLE", "NONE"), ("RUNNING", "NONE")},
}

RANGES = {
    # item: (min, max) inclusive, on the numeric part of the state
    "BMS_SOC": (0, 100),
    "BMS_SOC_190": (0, 100),
    "DCData_Voltage": (40, 65),
    "BMS_Temperature": (-40, 150),          # deg F
    "BMS_Capacity_Remaining_Ah": (0, 450),
    "ConextGateway_ACPowerValue": (0, 8000),  # W
}


def token():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line.startswith("export "):
                line = line[7:]
            if line.startswith("OPENHAB_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("OPENHAB_TOKEN not found")


def get(path, timeout=10):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + token()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def num(state):
    try:
        return float(str(state).split()[0].replace("°", ""))
    except (ValueError, IndexError):
        return None


def load_state():
    try:
        with open(STATE_FILE) as f:
            st = json.load(f)
    except (OSError, ValueError):
        st = {"last_alert": {}, "active": {}}
    for bucket in ("last_alert", "active"):
        st.setdefault(bucket, {}).pop("persist", None)
    return st


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, STATE_FILE)


def notify(msg):
    try:
        out = subprocess.run([NOTIFY, msg], capture_output=True, text=True, timeout=60)
        return "DM sent" in (out.stdout + out.stderr)
    except Exception:
        return False


DWELL_S = 8 * 60


def finite_num(value):
    value = num(value)
    return value if value is not None and math.isfinite(value) else None


def runtime_checks(st, now, snapshot, problems, unresolved):
    basis = str(snapshot.get("BMS_Runtime_Basis", {}).get("state") or "")
    active_estimate = basis in ("bms", "now", "evening")
    basis_available = basis not in ("", "NULL", "UNDEF", "None")
    ttd = finite_num(snapshot.get("BMS_TimeToDischarge_Smoothed", {}).get("state"))
    runtime_bad = active_estimate and (ttd is None or ttd <= 0)
    if runtime_bad:
        problems["algo:runtime"] = (
            f"runtime basis '{basis}' but smoothed value is {ttd} — estimator inconsistent")
    if not basis_available:
        unresolved.add("algo:runtime")

    # Old algo:basis alerts may represent invalid runtime. Preserve that active
    # key while either old meaning is still unresolved or demonstrably faulty.
    if runtime_bad:
        unresolved.add("algo:basis")

    cur = finite_num(snapshot.get("DCData_Current", {}).get("state"))
    raw_episode = snapshot.get("BMS_Runtime_Basis", {}).get("lastStateChange")
    # OpenHAB bulk DTO lastStateChange is epoch milliseconds. Do not substitute
    # receipt time or lastStateUpdate for a missing transition identity.
    episode = None
    if isinstance(raw_episode, (int, float)) and not isinstance(raw_episode, bool):
        if math.isfinite(raw_episode) and 0 < raw_episode <= now * 1000:
            episode = raw_episode
    missing = []
    if not basis_available:
        missing.append("BMS_Runtime_Basis unavailable")
    if cur is None:
        missing.append("DCData_Current unavailable or non-finite")
    if basis == "bms" and episode is None:
        missing.append("BMS_Runtime_Basis.lastStateChange unavailable or invalid")
    if missing:
        st.pop("pending_basis", None)
        problems["data:runtime"] = "; ".join(missing)
        unresolved.add("algo:basis")
        return
    if basis != "bms" or cur <= 0.5:
        st.pop("pending_basis", None)
        return

    pending = st.get("pending_basis")
    valid_pending = isinstance(pending, dict)
    if valid_pending:
        first, last = pending.get("first"), pending.get("last")
        valid_pending = (
            pending.get("episode") == episode
            and isinstance(first, (int, float)) and not isinstance(first, bool)
            and isinstance(last, (int, float)) and not isinstance(last, bool)
            and math.isfinite(first) and math.isfinite(last)
            and 0 < first <= last <= now)
    if not valid_pending:
        st["pending_basis"] = {"episode": episode, "first": now, "last": now}
        unresolved.add("algo:basis")
        return
    pending["last"] = now
    if now > pending["first"] and now - pending["first"] >= DWELL_S:
        problems["algo:basis"] = (
            f"runtime basis remains bms during repeated charging checks "
            f"({now - pending['first']:.0f} s apart; current {cur} A)")
    else:
        unresolved.add("algo:basis")


def main():
    st = load_state()
    now = time.time()
    problems = {}  # key -> message
    unresolved = set()

    # 1. REST reachable (everything else depends on it)
    try:
        get("/items/BMS_SOC/state".replace("/state", ""))  # cheap item GET
    except Exception as e:
        problems["rest"] = "openHAB REST unreachable: " + str(e)[:120]
        st.pop("pending_basis", None)
        finish(st, now, problems, set(st["active"]) - {"rest"})
        return

    # snapshot the states we need in one call
    try:
        snapshot = {i["name"]: i for i in get("/items?fields=name,state,lastStateChange")}
        items = {name: dto.get("state") for name, dto in snapshot.items()}
    except Exception as e:
        problems["rest"] = "items query failed: " + str(e)[:120]
        st.pop("pending_basis", None)
        finish(st, now, problems, set(st["active"]) - {"rest"})
        return

    # 2. rule health
    for uid, allowed in RULES_EXPECTED.items():
        try:
            s = get("/rules/" + uid)["status"]
            pair = (s.get("status", "?"), s.get("statusDetail", "?"))
            if pair not in allowed:
                problems["rule:" + uid] = f"rule {uid} in unexpected state {pair[0]}/{pair[1]}"
        except Exception as e:
            problems["rule:" + uid] = f"rule {uid} not queryable: {str(e)[:80]}"

    # 3. value ranges
    for item, (lo, hi) in RANGES.items():
        v = num(items.get(item))
        if v is None:
            problems["range:" + item] = f"{item} has no numeric state ({items.get(item)!r})"
        elif not (lo <= v <= hi):
            problems["range:" + item] = f"{item} out of range: {v} not in [{lo},{hi}]"

    temp_raw = finite_num(items.get("BMS_Temperature_Raw"))
    temp_value = finite_num(items.get("BMS_Temperature"))
    if temp_raw is None or temp_value is None or temp_raw <= 0:
        unresolved.add("algo:temp")
    soc_raw = finite_num(items.get("BMS_SOC_Raw"))
    soc_value = finite_num(items.get("BMS_SOC"))
    if soc_raw is None or soc_value is None or soc_raw == 65535:
        unresolved.add("algo:soc")

    # 4. algorithm cross-verification
    tr, tf = num(items.get("BMS_Temperature_Raw")), num(items.get("BMS_Temperature"))
    if tr is not None and tf is not None and tr > 0:
        expect = (tr * 0.01 - 273) * 9 / 5 + 32
        if abs(expect - tf) > 1.0:
            problems["algo:temp"] = (f"BMS_Temperature {tf} F disagrees with raw-derived "
                                     f"{expect:.1f} F (raw {tr:.0f}) — scale rule broken?")
    sr, sf_, sv = num(items.get("BMS_SOC_Raw")), num(items.get("BMS_SOC_ScaleFactor_Raw")), num(items.get("BMS_SOC"))
    if sr is not None and sv is not None and sr != 65535:
        sf_ = 0 if (sf_ is None or sf_ == -32768) else sf_
        expect = min(sr * (10 ** sf_), 100)
        if abs(expect - sv) > 1.0:
            problems["algo:soc"] = (f"BMS_SOC {sv}% disagrees with raw-derived {expect:.1f}% "
                                    f"(raw {sr:.0f}, sf {sf_:.0f}) — scale rule broken?")

    # 5. runtime estimator consistency
    runtime_checks(st, now, snapshot, problems, unresolved)

    # 6. freshness
    def age_min(item):
        raw = str(items.get(item) or "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return (datetime.now(timezone.utc) - dt).total_seconds() / 60
        except ValueError:
            return None
    a = age_min("BMS_SOC_LastUpdate")
    if a is None or a > 12:  # heartbeat is rate-gated to 5 min
        problems["fresh:bms"] = f"BMS_SOC_LastUpdate stale ({'unparseable' if a is None else f'{a:.0f} min'})"
    a = age_min("Schneider_DCData_LastUpdate")
    if a is None or a > 5:
        problems["fresh:schneider"] = f"Schneider_DCData_LastUpdate stale ({'unparseable' if a is None else f'{a:.0f} min'})"
    # frost sensor feed (WH31E, outdoor shade near ground since 2026-07-14):
    # RF at this placement is lossy (gaps to ~25 min observed) — alert only on
    # prolonged dropout, which blinds hex_frost_watch
    # (WH31E shade-sensor logic removed entirely 2026-07-17 per Sat)
    # forecast pipeline freshness (Open Meteo binding refreshes hourly; the
    # prediction items are re-posted daily at 06:40 by forecast-intel.timer)
    fa = age_min("Forecast_Daily_High") if False else None  # daily items lack timestamps via state; check hourly item value instead
    fv = num(items.get("Forecast_Temp"))
    if fv is None:
        problems["fresh:forecast"] = "Forecast_Temp has no value — Open Meteo feed down?"


    finish(st, now, problems, unresolved)


def finish(st, now, problems, unresolved=None):
    unresolved = set() if unresolved is None else unresolved
    for key in [k for k, v in st["active"].items()
                if v and k not in problems and k not in unresolved]:
        st["active"][key] = False
        st["last_alert"].pop(key, None)
        notify(f"✅ openHAB sanity: recovered [{key}]")
    for key, msg in problems.items():
        st["active"][key] = True
        last = st["last_alert"].get(key, 0)
        if now - last >= RATE_S:
            if notify("\U0001f50e openHAB sanity: " + msg):
                st["last_alert"][key] = now
    held = sorted(key for key in unresolved if st["active"].get(key) and key not in problems)
    save_state(st)
    details = list(problems.values())
    if held:
        details.append("active faults awaiting valid clearing evidence: " + ", ".join(held))
    line = datetime.now().isoformat(timespec="seconds") + " " + (
        "OK (all checks passed)" if not details else "PROBLEMS: " + "; ".join(details))
    with open(os.path.join(STATE_DIR, "last_run.log"), "a") as f:
        f.write(line + "\n")
    print(line)
    sys.exit(1 if details else 0)


if __name__ == "__main__":
    main()
