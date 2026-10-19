"""Synthetic local BMS packets and fixed clocks, independent of weather models."""
from datetime import datetime,timedelta,timezone
import json
from uuid import UUID

NOW=datetime(2026,9,29,23,33,23,tzinfo=timezone.utc)
BASE=datetime(2026,9,22,12,tzinfo=timezone.utc)


def bms_evidence(at=NOW - timedelta(seconds=20), *, soc=100, status='valid'):
    stamp = lambda instant: int(instant.timestamp() * 1000)
    return json.dumps({
        'version': 1, 'streamEpoch': str(UUID(int=1)),
        'recordedAt': stamp(at), 'status': status,
        'reason': 'ok' if status == 'valid' else 'input_stale',
        'observedAt': stamp(at) if status == 'valid' else None,
        'scaleObservedAt': stamp(at) if status == 'valid' else None,
        'validUntil': stamp(at + timedelta(seconds=120)) if status == 'valid' else None,
        'soc': soc if status == 'valid' else None,
    })


def bms_soc_evidence(at=BASE, *, soc=85, status="valid"):
    stamp = lambda instant: int(instant.timestamp() * 1000)
    return json.dumps({
        "version": 1, "streamEpoch": str(UUID(int=1)), "recordedAt": stamp(at),
        "status": status, "reason": "ok" if status == "valid" else "input_stale",
        "observedAt": stamp(at) if status == "valid" else None,
        "scaleObservedAt": stamp(at) if status == "valid" else None,
        "validUntil": stamp(at + timedelta(seconds=120)) if status == "valid" else None,
        "soc": soc if status == "valid" else None,
    })
