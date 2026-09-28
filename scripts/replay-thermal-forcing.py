#!/usr/bin/env python3
"""Read-only exact thermal v2 replay and optional assumed-closed vent diagnostic.

Counterfactual output is modeled, never a confirmed action or training label.
The script refuses to compare schedules unless the as-issued output first
replays exactly under the capture's matching runtime source and artifact.
"""

import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace


DEFAULT_RUNTIME_ROOT = Path(__file__).resolve().parents[1] / 'openhab/scripts'
_bootstrap = argparse.ArgumentParser(add_help=False)
_bootstrap.add_argument('--runtime-root', type=Path, default=DEFAULT_RUNTIME_ROOT)
_bootstrap_args, _ = _bootstrap.parse_known_args()
RUNTIME_ROOT = _bootstrap_args.runtime_root.resolve()
if (not RUNTIME_ROOT.is_dir()
        or not (RUNTIME_ROOT / 'thermal_intel.py').is_file()
        or not (RUNTIME_ROOT / 'thermal_model/forcing_capture.py').is_file()):
    raise ValueError('complete thermal replay runtime root required')
sys.path.insert(0, str(RUNTIME_ROOT))

from thermal_intel import _runtime_manifest_revision  # noqa: E402
from thermal_model.artifacts import _artifact_from_payload  # noqa: E402
from thermal_model.forcing_capture import verify_capture  # noqa: E402
import thermal_model.pipeline as pipeline  # noqa: E402


HORIZONS = (1, 6, 12, 24, 48)


def _run(capture, artifact):
    registry = SimpleNamespace(load_accepted=lambda: artifact, last_load_source=None)
    return pipeline.run_shadow(
        registry=registry,
        current=capture['current'],
        forecast=capture['forecast_rows'],
        now=datetime.fromisoformat(capture['decision_at']),
    )


def _closed_vent_schedule(model, rows, original):
    schedule = original(model, rows)
    return {**schedule,
            'vent': 'closed', 'ventFlow': 'closed', 'ventForcing': 0.0,
            'ventOpenMinute': None, 'ventCloseMinute': None,
            'ventOpenAt': None, 'ventCloseAt': None,
            'airflowSegments': (),
            'ventTimingSource': 'diagnostic_counterfactual',
            'ventTimingStatus': 'assumed_closed'}


def _horizon_deltas(issued, hypothetical, decision):
    first = {point['at']: point for point in issued['forecast']['trajectory']}
    second = {point['at']: point for point in hypothetical['forecast']['trajectory']}
    if first.keys() != second.keys():
        raise ValueError('counterfactual trajectory timestamps changed')
    rows = []
    for hours in HORIZONS:
        target = decision + timedelta(hours=hours)
        matches = [(abs((datetime.fromisoformat(at).astimezone(timezone.utc)
                         - target).total_seconds()), at)
                   for at in first]
        if not matches:
            continue
        drift, at = min(matches)
        if drift > 1800:
            continue
        issued_f = first[at]['hallwayF']
        hypothetical_f = second[at]['hallwayF']
        rows.append({'hours': hours, 'target_at': at, 'issued_f': issued_f,
                     'assumed_closed_f': hypothetical_f,
                     'delta_f': round(hypothetical_f - issued_f, 3)})
    return rows


def replay(path, *, assume_vents_closed=False):
    capture = verify_capture(path)
    if capture['schema'] != 'earthship-thermal-shadow-forcing-capture/v2':
        raise ValueError('exact replay requires a v2 capture with embedded artifact')
    artifact = _artifact_from_payload(capture['artifact'])
    revision = _runtime_manifest_revision(RUNTIME_ROOT)
    if revision != artifact.code_revision:
        raise ValueError('capture artifact does not match selected runtime source')
    issued = capture['output']
    replayed = _run(capture, artifact)
    decision = datetime.fromisoformat(capture['decision_at']).astimezone(timezone.utc)
    # The pure simulator emits whole seconds. The publication path preserves
    # the full input-bound decision timestamp; only that representation differs.
    generated = datetime.fromisoformat(replayed['generatedAt']).astimezone(timezone.utc)
    if (generated != decision.replace(microsecond=0)
            or datetime.fromisoformat(issued['generatedAt']).astimezone(timezone.utc) != decision):
        raise ValueError('replay decision timestamp does not match capture')
    replayed['generatedAt'] = issued['generatedAt']
    if replayed != issued:
        raise ValueError('as-issued thermal publication failed exact replay')
    result = {
        'scope': 'read_only_exact_thermal_replay',
        'capture': str(path),
        'capture_output_sha256': capture['sha256']['output'],
        'artifact_code_revision': artifact.code_revision,
        'runtime_root': str(RUNTIME_ROOT),
        'runtime_manifest_revision': revision,
        'runtime_source_sha256': sha256((RUNTIME_ROOT / 'thermal_intel.py').read_bytes()).hexdigest(),
        'exact_as_issued': True,
        'counterfactual_is_action_evidence': False,
    }
    if assume_vents_closed:
        original = pipeline.baseline_schedule
        try:
            pipeline.baseline_schedule = lambda model, rows: _closed_vent_schedule(
                model, rows, original)
            hypothetical = _run(capture, artifact)
        finally:
            pipeline.baseline_schedule = original
        if hypothetical['status'] != 'shadow' or hypothetical['confidence']['grade'] == 'unavailable':
            raise ValueError('closed-vent diagnostic did not produce a usable shadow forecast')
        result['assumed_closed_vent'] = {
            'interpretation': 'modeled schedule hypothesis, not observed vent state',
            'horizons': _horizon_deltas(issued, hypothetical, decision),
        }
    if _runtime_manifest_revision(RUNTIME_ROOT) != revision:
        raise ValueError('runtime source changed during replay')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--assume-vents-closed', action='store_true')
    args = parser.parse_args()
    print(json.dumps(replay(args.capture, assume_vents_closed=args.assume_vents_closed),
                     sort_keys=True))


if __name__ == '__main__':
    main()
