"""Closed, code-bound split-airflow shadow candidates; no accepted-pointer write."""
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

import numpy as np
import scipy

from .airflow import AirflowSeed, airflow_manifest, validate_airflow_physics
from .airflow_training import AirflowFit
from .dataset import (MASS_OBSERVER_TAU_MINUTES, MODE_COUNT_KEYS,
    RADIATION_PROVENANCE_LABELS, CORE_REJECTED_COUNT_KEYS, AUXILIARY_EXCLUSION_COUNT_KEYS)
from .schema import THERMAL_ITEMS, OPTIONAL_OBSERVATION_ITEMS, SOURCE_WEIGHTS
from .dynamics import IDENTIFICATION_HORIZON_STEPS, MULTIHORIZON_OBJECTIVE_TOLERANCE

SCHEMA = 'earthship-split-airflow-shadow-artifact/v1'
MASS_INITIALIZATION = {'method': 'causal_north_wall_exponential_observer',
                       'tau_minutes': MASS_OBSERVER_TAU_MINUTES,
                       'lookback_minutes': 1440, 'step_minutes': 5}
EXTRA_FILES = ('thermal_model/airflow.py', 'thermal_model/airflow_training.py',
    'thermal_model/airflow_artifact.py', 'thermal_model/airflow_forecast.py',
    'thermal_model/operational_origin.py', 'thermal_model/action_history.py',
    'thermal_model/forecast_history.py')
KEYS = {'schema', 'status', 'created_at', 'trained_from', 'trained_through',
        'runtime', 'data_manifest', 'fit', 'initialization', 'control_enabled'}


def canonical(value):
    def encode(obj):
        if isinstance(obj, datetime):
            return utc(obj).isoformat()
        raise TypeError('unsupported split-airflow value')
    return json.dumps(value, default=encode, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.utcoffset() is None:
        raise ValueError('aware split-airflow timestamp required')
    return parsed.astimezone(timezone.utc)


def runtime_manifest(root=None):
    # Bind the existing complete dependency closure, not just the new fitter.
    from thermal_intel import RUNTIME_REVISION_PATHS
    executing = Path(__file__).resolve().parents[1]
    root = Path(root).resolve() if root is not None else executing
    if root != executing:
        raise ValueError('runtime root must match executing split-airflow modules')
    for relative in sorted(set(RUNTIME_REVISION_PATHS) | set(EXTRA_FILES)):
        name = relative[:-3].replace('/', '.')
        module = sys.modules.get(name)
        if module is not None and Path(module.__file__).resolve() != root/relative:
            raise ValueError('mixed split-airflow module roots')
    rows = [{'path': name, 'sha256': sha256((root/name).read_bytes()).hexdigest()}
            for name in sorted(set(RUNTIME_REVISION_PATHS) | set(EXTRA_FILES))]
    environment = {'python': sys.version.split()[0], 'numpy': np.__version__, 'scipy': scipy.__version__}
    payload = {'files': rows, 'environment': environment}
    return {**payload, 'sha256': sha256(canonical(payload)).hexdigest()}


def build_artifact(fit, samples, events, modes, *, created_at, runtime_root=None):
    if not isinstance(fit, AirflowFit) or not samples:
        raise ValueError('split-airflow fit and dataset required')
    manifest = airflow_manifest(samples, events, modes)
    payload = {'schema': SCHEMA, 'status': 'shadow_candidate',
        'created_at': utc(created_at).isoformat(),
        'trained_from': manifest['dataset']['start'],
        'trained_through': manifest['dataset']['end'],
        'runtime': runtime_manifest(runtime_root), 'data_manifest': manifest,
        'fit': asdict(fit), 'initialization': dict(MASS_INITIALIZATION),
        'control_enabled': False}
    return validate_artifact(payload, runtime_root=runtime_root)


def _digest(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_artifact(payload, *, runtime_root=None):
    if (not isinstance(payload, dict) or set(payload) != KEYS or payload['schema'] != SCHEMA
            or payload['status'] != 'shadow_candidate' or payload['control_enabled'] is not False
            or payload['initialization'] != MASS_INITIALIZATION):
        raise ValueError('invalid split-airflow artifact contract')
    if not utc(payload['trained_from']) < utc(payload['trained_through']) <= utc(payload['created_at']):
        raise ValueError('split-airflow artifact chronology invalid')
    if payload['runtime'] != runtime_manifest(runtime_root):
        raise ValueError('split-airflow runtime binding mismatch')
    manifest = payload['data_manifest']
    if (not isinstance(manifest, dict) or set(manifest) !=
            {'schema', 'legacy_promotion_eligible', 'dataset', 'state_counts'}
            or manifest['schema'] != 'earthship-split-airflow-dataset/v2'
            or manifest['legacy_promotion_eligible'] is not False):
        raise ValueError('invalid split-airflow data manifest')
    data = manifest['dataset']
    expected = {'start', 'end', 'sample_count', 'sample_counts_by_mode', 'rejected_counts',
        'auxiliary_exclusion_counts', 'interpolation_counts', 'hold_forward_counts',
        'radiation_provenance_counts', 'event_counts_by_source', 'items', 'canonical_rows_sha256'}
    if (not isinstance(data, dict) or set(data) != expected or data['start'] != payload['trained_from']
            or data['end'] != payload['trained_through'] or type(data['sample_count']) is not int
            or data['sample_count'] < 1 or not _digest(data['canonical_rows_sha256'])):
        raise ValueError('invalid split-airflow dataset identity')
    if data['items'] != {**THERMAL_ITEMS, **OPTIONAL_OBSERVATION_ITEMS}:
        raise ValueError('invalid split-airflow sensor identity')
    vocabularies = {
        'sample_counts_by_mode': (set(MODE_COUNT_KEYS), True),
        'radiation_provenance_counts': (set(RADIATION_PROVENANCE_LABELS), True),
        'interpolation_counts': (set(data['items']), True),
        'hold_forward_counts': (set(data['items']), True),
        'rejected_counts': (CORE_REJECTED_COUNT_KEYS, False),
        'auxiliary_exclusion_counts': (AUXILIARY_EXCLUSION_COUNT_KEYS, False),
        'event_counts_by_source': (set(SOURCE_WEIGHTS), False)}
    for name, (keys, exact) in vocabularies.items():
        counts = data[name]
        if (not isinstance(counts, dict) or not set(counts) <= keys
                or (exact and set(counts) != keys)
                or any(type(n) is not int or n < 0 for n in counts.values())):
            raise ValueError('invalid split-airflow dataset counts: ' + name)
        if name in ('sample_counts_by_mode', 'radiation_provenance_counts') and sum(counts.values()) != data['sample_count']:
            raise ValueError('inconsistent split-airflow dataset counts: ' + name)
    if not isinstance(manifest['state_counts'], dict) or set(manifest['state_counts']) != {'window_open', 'skylight_open'}:
        raise ValueError('invalid split-airflow state counts')
    for counts in manifest['state_counts'].values():
        if (not isinstance(counts, dict) or set(counts) != {'unknown', 'closed', 'open'}
                or any(type(n) is not int or n < 0 for n in counts.values())
                or sum(counts.values()) != data['sample_count']):
            raise ValueError('invalid split-airflow state counts')
    fit = payload['fit']
    if not isinstance(fit, dict) or set(fit) != {'dynamics', 'inactive_forcing_features',
            'origin_counts', 'initial_objective', 'final_objective', 'training_revision', 'training_data_sha256'}:
        raise ValueError('invalid split-airflow fit evidence')
    if fit['training_revision'] != payload['runtime']['sha256']:
        raise ValueError('split-airflow fit was not bound to this training runtime')
    if fit['training_data_sha256'] != data['canonical_rows_sha256']:
        raise ValueError('split-airflow fit was not bound to this training data')
    if (not isinstance(fit['dynamics'], dict) or set(fit['dynamics']) !=
            {'version', 'step_minutes', 'air_coefficients', 'mass_coefficients', 'glazing_observation_coefficients'}):
        raise ValueError('invalid split-airflow dynamics contract')
    model = validate_airflow_physics(AirflowSeed(**fit['dynamics']))
    inactive = fit['inactive_forcing_features']
    supported = ('solar_indoor_closed', 'solar_outdoor', 'window_exchange', 'skylight_exchange', 'joint_open_exchange')
    if (not isinstance(inactive, (tuple, list)) or len(set(inactive)) != len(inactive)
            or any(name not in supported for name in inactive)
            or any(model.air_coefficients[name] != 0 for name in inactive)
            or any(model.mass_coefficients.get(name, 0) != 0 for name in inactive)):
        raise ValueError('invalid split-airflow inactive-feature contract')
    counts = fit['origin_counts']
    if (not isinstance(counts, (tuple, list)) or len(counts) != len(IDENTIFICATION_HORIZON_STEPS)
            or any(not isinstance(row, (tuple, list)) or len(row) != 2
                   or row[0] != str(step*5) or type(row[1]) is not int or not 2 <= row[1] <= 64
                   for row, step in zip(counts, IDENTIFICATION_HORIZON_STEPS))):
        raise ValueError('invalid split-airflow origin counts')
    initial, final = fit['initial_objective'], fit['final_objective']
    if (any(type(v) not in (int, float) or not np.isfinite(v) or v < 0 for v in (initial, final))
            or final > initial + MULTIHORIZON_OBJECTIVE_TOLERANCE*max(1.0, initial)):
        raise ValueError('invalid split-airflow objective evidence')
    if len(canonical(payload)) > 1_000_000:
        raise ValueError('split-airflow artifact exceeds bound')
    return deepcopy(payload)


def artifact_digest(payload):
    return sha256(canonical(payload)).hexdigest()
