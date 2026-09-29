#!/usr/bin/env python3
"""Attended SoC-evidence release using the pinned greywater rollback adapter.

Without --apply this performs read-only preflight. A protected-rule replacement
still requires explicit operator approval and physical monitoring.
"""

import importlib.util
import json
import math
import os
from pathlib import Path
import time


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / 'scripts/deploy-greywater-timer-guard.py'
spec = importlib.util.spec_from_file_location('greywater_guard', ADAPTER)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

# Fail if either the live baseline or candidate has drifted. The imported
# adapter retains the same private backup, exact DTO readback and rollback.
guard.OLD_SHA = '312cf24ceba5c63e30c4ecd0104bbf3bcf646f1e203b8c6c9c964e58dd7b84df'
guard.NEW_SHA = 'e697e2626a5e1ab4e4d079612c4b85d16dd79178a4ff80a5208b4bb108970d18'


def main():
    if guard.oh.get('/items/BMS_Comms_Status')['state'] != 'OK':
        raise RuntimeError('BMS comms are not OK')
    raw = guard.oh.get('/items/BMS_SOC_Evidence_JSON')['state']
    if guard.oh.atomic_soc_freshness(raw, time.time()):
        raise RuntimeError('fresh source-bound BMS SoC evidence required')
    evidence_soc = json.loads(raw)['soc']
    held_soc = float(guard.oh.get('/items/BMS_SOC')['state'])
    if not math.isclose(evidence_soc, held_soc, abs_tol=0.05):
        raise RuntimeError('atomic SoC and held display SoC disagree')
    guard.main()


if __name__ == '__main__':
    os.umask(0o077)
    main()
