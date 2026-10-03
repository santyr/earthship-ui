#!/usr/bin/env python3
"""Read-only exact thermal v2 replay and optional forcing diagnostics.

Counterfactual output is modeled, never a confirmed action or training label.
The script refuses to compare schedules unless the as-issued output first
replays exactly under the selected, hash-bound runtime source and artifact.
Each optional hypothesis starts independently from the original capture; flags
do not combine into an observed-weather or multi-action counterfactual.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import re
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


def _run(capture, artifact, forcing_records=None):
    registry = SimpleNamespace(load_accepted=lambda: artifact, last_load_source=None)
    original = pipeline._simulate_schedule
    if forcing_records is not None:
        def record(dynamics, rows, schedule, initial):
            forcings = pipeline._schedule_forcings(rows, schedule)
            predictions = pipeline.simulate(dynamics, initial, forcings)
            forcing_records.append(deepcopy({'initial': initial, 'forcings': forcings,
                                            'predictions': predictions}))
            return predictions
        pipeline._simulate_schedule = record
    try:
        return pipeline.run_shadow(
            registry=registry,
            current=capture['current'],
            forecast=capture['forecast_rows'],
            now=datetime.fromisoformat(capture['decision_at']),
        )
    finally:
        pipeline._simulate_schedule = original


def _closed_vent_schedule(model, rows, original):
    schedule = original(model, rows)
    return {**schedule,
            'vent': 'closed', 'ventFlow': 'closed', 'ventForcing': 0.0,
            'ventOpenMinute': None, 'ventCloseMinute': None,
            'ventOpenAt': None, 'ventCloseAt': None,
            'airflowSegments': (),
            'ventTimingSource': 'diagnostic_counterfactual',
            'ventTimingStatus': 'assumed_closed'}


def _horizon_deltas(issued, hypothetical, decision, *, value_field='assumed_closed_f'):
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
                     value_field: hypothetical_f,
                     'delta_f': round(hypothetical_f - issued_f, 3)})
    return rows


def _solar_scaled_capture(capture, scale):
    """Copy weather inputs only; never change captured facts or current readings."""
    changed = {**capture, 'forecast_rows': deepcopy(capture['forecast_rows'])}
    for row in changed['forecast_rows']:
        value = row['radiationWm2']
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not 0 <= value <= 1600 or not 0 <= value * scale <= 1600):
            raise ValueError('hypothetical solar forcing outside physical range')
        row['radiationWm2'] = value * scale
    return changed


def _outdoor_shifted_capture(capture, offset):
    """Uniform hypothetical forecast shift; initial sensor facts stay unchanged."""
    changed = {**capture, 'forecast_rows': deepcopy(capture['forecast_rows'])}
    low, high = pipeline.TEMPERATURE_RANGE_F
    for row in changed['forecast_rows']:
        value = row['tempF']
        if (type(value) not in (int, float) or not math.isfinite(value)
                or not low <= value <= high or not low <= value + offset <= high):
            raise ValueError('hypothetical outdoor forcing outside physical range')
        row['tempF'] = value + offset
    return changed


def _schedule_changed(issued, hypothetical):
    # Effect summaries change with weather even when selected times do not.
    return any(issued.get(name) != hypothetical.get(name)
               for name in ('baseline', 'candidate'))


def replay(path, *, assume_vents_closed=False, expected_runtime_revision=None,
           solar_scale=None, outdoor_offset_f=None, selected_forcing_observer=None):
    if selected_forcing_observer is not None and not callable(selected_forcing_observer):
        raise ValueError('selected forcing observer must be callable')
    if solar_scale is not None and (
            type(solar_scale) not in (int, float) or not math.isfinite(solar_scale)
            or not 0 <= solar_scale <= 2):
        raise ValueError('solar scale must be finite and between zero and two')
    if outdoor_offset_f is not None and (
            type(outdoor_offset_f) not in (int, float) or not math.isfinite(outdoor_offset_f)
            or not -20 <= outdoor_offset_f <= 20):
        raise ValueError('outdoor offset must be finite and between -20 and 20 Fahrenheit degrees')
    if expected_runtime_revision is not None and (
            not isinstance(expected_runtime_revision, str)
            or re.fullmatch(r'[0-9a-f]{64}', expected_runtime_revision) is None):
        raise ValueError('full lowercase runtime SHA-256 required')
    capture = verify_capture(path)
    if capture['schema'] != 'earthship-thermal-shadow-forcing-capture/v2':
        raise ValueError('exact replay requires a v2 capture with embedded artifact')
    artifact = _artifact_from_payload(capture['artifact'])
    revision = _runtime_manifest_revision(RUNTIME_ROOT)
    # Training and publication can use different source revisions after a
    # runtime optimization. Such a replay requires the caller to pin the full
    # selected runtime hash; exact output equality below still proves replay.
    if expected_runtime_revision is None:
        if revision != artifact.code_revision:
            raise ValueError('capture artifact does not match selected runtime source')
    elif revision != expected_runtime_revision:
        raise ValueError('selected runtime does not match explicit revision pin')
    issued = capture['output']
    records = [] if selected_forcing_observer is not None else None
    replayed = _run(capture, artifact) if records is None else _run(capture, artifact, records)
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
        'runtime_binding': ('explicit_sha256' if expected_runtime_revision is not None
                            else 'artifact_code_revision'),
        'training_revision_matches_runtime': revision == artifact.code_revision,
        'runtime_source_sha256': sha256((RUNTIME_ROOT / 'thermal_intel.py').read_bytes()).hexdigest(),
        'diagnostic_source_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
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
    if solar_scale is not None:
        hypothetical = _run(_solar_scaled_capture(capture, solar_scale), artifact)
        if hypothetical['status'] != 'shadow' or hypothetical['confidence']['grade'] == 'unavailable':
            raise ValueError('solar diagnostic did not produce a usable shadow forecast')
        result['solar_sensitivity'] = {
            'interpretation': 'weather-input hypothesis; includes modeled schedule reselection, not measured irradiance or action evidence',
            'scale': solar_scale,
            'schedule_changed': _schedule_changed(issued['schedule'], hypothetical['schedule']),
            'horizons': _horizon_deltas(issued, hypothetical, decision,
                                       value_field='hypothetical_f'),
        }
    if outdoor_offset_f is not None:
        hypothetical = _run(_outdoor_shifted_capture(capture, outdoor_offset_f), artifact)
        if hypothetical['status'] != 'shadow' or hypothetical['confidence']['grade'] == 'unavailable':
            raise ValueError('outdoor diagnostic did not produce a usable shadow forecast')
        result['outdoor_temperature_sensitivity'] = {
            'interpretation': 'uniform forecast-input hypothesis; includes modeled schedule reselection, not observed weather, a learned correction or action evidence',
            'offset_f': outdoor_offset_f,
            'schedule_changed': _schedule_changed(issued['schedule'], hypothetical['schedule']),
            'horizons': _horizon_deltas(issued, hypothetical, decision,
                                       value_field='hypothetical_f'),
        }
    if _runtime_manifest_revision(RUNTIME_ROOT) != revision:
        raise ValueError('runtime source changed during replay')
    if selected_forcing_observer is not None:
        if not records:
            raise ValueError('exact selected forcing was not retained')
        selected = records[-1]
        forcings, predictions = selected['forcings'], selected['predictions']
        if not forcings or len(forcings) != len(predictions):
            raise ValueError('selected forcing/prediction grid is incomplete')
        trajectory = issued['forecast']['trajectory']
        if not trajectory:
            raise ValueError('published trajectory is empty')
        states = {row['at'].astimezone(timezone.utc): state
                  for row, state in zip(forcings, predictions)}
        states[forcings[0]['at'].astimezone(timezone.utc)-timedelta(minutes=5)] = selected['initial']
        for point in trajectory:
            state = states.get(datetime.fromisoformat(point['at']).astimezone(timezone.utc))
            if (state is None or round(float(state['air_f']), 3) != point['hallwayF']
                    or round(float(state['mass_f']), 3) != point['massF']):
                raise ValueError('selected forcing does not reproduce published trajectory')
        # The last native _simulate_schedule call produces the selected output,
        # not a speculative search candidate. Export only after exact output
        # equality and final runtime-pin checks; never print private grids.
        selected_forcing_observer(deepcopy({'origin': decision, **selected}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--assume-vents-closed', action='store_true')
    parser.add_argument('--solar-scale', type=float,
                        help='diagnostic forecast-radiation multiplier, 0–2; never changes captured observations')
    parser.add_argument('--outdoor-offset-f', type=float,
                        help='diagnostic uniform forecast-temperature shift, -20–20 F; not a learned correction')
    parser.add_argument('--expected-runtime-revision',
                        help='full SHA-256 pin when publisher and training sources differ; exact replay remains required')
    args = parser.parse_args()
    print(json.dumps(replay(args.capture, assume_vents_closed=args.assume_vents_closed,
                           expected_runtime_revision=args.expected_runtime_revision,
                           solar_scale=args.solar_scale,
                           outdoor_offset_f=args.outdoor_offset_f),
                     sort_keys=True))


if __name__ == '__main__':
    main()
