"""Distinct, source-replayed installed-shade development candidate bundles.

Numerical/source consistency does not prove optimizer execution, baseline skill,
calibration or as-issued qualification. These records grant no release authority.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import time
from uuid import uuid4

from .actions import DENVER
from .dynamics import (NORMALIZED_CONDITION_NUMBER_LIMIT, BLOCK_REFIT_GROUPS,
    BLOCK_REFIT_MIN_INDEPENDENT_DAYS, BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION,
    MAX_ORIGINS_PER_HORIZON, MULTIHORIZON_MAXITER,
    MULTIHORIZON_OBJECTIVE_TOLERANCE)
from .forcing_capture import _canonical, _private_directory
from .graduation_policy import _utc, _sha
from .installed_shade_dynamics import InstalledShadeDynamics, PARAMETER_NAMES
from .installed_shade_fit import (DevelopmentFit, HORIZONS,
    _prepare_batches, _objective, _conditioning, _assess_stability,
    _nonoverlap_count, _check_deadline)
from .installed_shade_inputs import build_development_inputs, select_development_endpoints
from .origin_capture import _object
from .runtime_bundle import _write_private, _sync_directory, _owned_bytes
from .rollback import _rename_new
from .temperature_history import _sensor_bindings
from .training_inputs import write_training_inputs_v2, read_training_inputs_v2

SCHEMA = 'earthship-installed-shade-candidate/v1'
EVIDENCE_SCHEMA = 'earthship-installed-shade-fit-evidence/v1'
MAX_BYTES = 200000
PAYLOAD_FIELDS = {'schema', 'domain', 'status', 'dynamics', 'source_snapshot_sha256',
    'sensor_epochs', 'trained_from', 'trained_through', 'created_at',
    'code_revision', 'runtime_revision', 'release_authorized', 'as_issued_evidence'}
ARTIFACT_FIELDS = PAYLOAD_FIELDS | {'fit_evidence_sha256', 'artifact_sha256'}
EVIDENCE_FIELDS = {'schema', 'candidate_payload_sha256', 'limits', 'initial_coefficients',
    'optimizer', 'conditioning', 'support', 'stability', 'block_conditioning',
    'fit_gates_passed', 'release_authorized', 'fit_evidence_sha256'}


def _digest(value): return sha256(_canonical(value)).hexdigest()

def _payload(artifact): return {key: value for key, value in artifact.items() if key not in {'fit_evidence_sha256', 'artifact_sha256'}}


def _limits():
    return dict(normalized_condition_number_limit=NORMALIZED_CONDITION_NUMBER_LIMIT,
        block_refit_groups=BLOCK_REFIT_GROUPS, min_independent_days=BLOCK_REFIT_MIN_INDEPENDENT_DAYS,
        max_bound_span_fraction=BLOCK_REFIT_MAX_BOUND_SPAN_FRACTION)


def _deadline(seconds):
    if type(seconds) not in (int, float) or not 0 < seconds <= 90:
        raise ValueError('bounded candidate replay timeout required')
    return time.monotonic()+seconds


def _shape(artifact, *, expected_runtime_revision, assessed_at):
    if (not isinstance(artifact, dict) or set(artifact) != ARTIFACT_FIELDS or
            artifact['schema'] != SCHEMA or artifact['domain'] != 'outdoor_shades_installed' or
            artifact['status'] != 'development_candidate' or
            artifact['release_authorized'] is not False or artifact['as_issued_evidence'] is not False):
        raise ValueError('closed installed-shade development candidate required')
    for key in ('code_revision', 'runtime_revision', 'source_snapshot_sha256', 'fit_evidence_sha256', 'artifact_sha256'):
        _sha(artifact[key])
    if artifact['runtime_revision'] != _sha(expected_runtime_revision):
        raise ValueError('candidate runtime differs from expected original runtime')
    if _digest({k: v for k, v in artifact.items() if k != 'artifact_sha256'}) != artifact['artifact_sha256']:
        raise ValueError('candidate digest differs')
    start, end, created = map(_utc, (artifact['trained_from'], artifact['trained_through'], artifact['created_at']))
    if not start < end <= created <= _utc(assessed_at):
        raise ValueError('candidate training/creation unavailable at assessment')
    _sensor_bindings(artifact['sensor_epochs'])
    dynamics = artifact['dynamics']
    if (not isinstance(dynamics, dict) or set(dynamics) != {'step_minutes', 'parameter_names', 'coefficients'} or
            type(dynamics['step_minutes']) is not int or dynamics['step_minutes'] != 5 or
            dynamics['parameter_names'] != list(PARAMETER_NAMES) or not isinstance(dynamics['coefficients'], list)):
        raise ValueError('distinct closed ten-parameter dynamics required')
    return InstalledShadeDynamics(tuple(dynamics['coefficients']))


def _measure(payload, inputs, *, initial_coefficients, blocks, iterations, deadline):
    _check_deadline(deadline)
    if type(iterations) is not int or not 1 <= iterations <= MULTIHORIZON_MAXITER:
        raise ValueError('bounded reported optimizer iteration count required')
    initial = InstalledShadeDynamics(tuple(initial_coefficients))
    final = InstalledShadeDynamics(tuple(payload['dynamics']['coefficients']))
    data = build_development_inputs(inputs, expected_snapshot_sha256=payload['source_snapshot_sha256'],
        sensor_epochs=payload['sensor_epochs'], assessed_at=payload['created_at'])
    groups = tuple((h, select_development_endpoints(data, horizon_hours=h,
        start=payload['trained_from'], end=payload['trained_through'])[:MAX_ORIGINS_PER_HORIZON]) for h in HORIZONS)
    if any(not rows for _, rows in groups): raise ValueError('original training horizon support missing')
    points = tuple(point for _, rows in groups for point in rows)
    batches = _prepare_batches(points)
    initial_loss, _, initial_matrix = _objective(initial.coefficients, batches, deadline=deadline)
    final_loss, _, final_matrix = _objective(final.coefficients, batches, deadline=deadline)
    initial_rank, initial_condition = _conditioning(initial_matrix)
    final_rank, final_condition = _conditioning(final_matrix)
    if final_loss > initial_loss+MULTIHORIZON_OBJECTIVE_TOLERANCE*max(1., initial_loss):
        raise ValueError('candidate worsens original training objective')
    for point in points:
        _check_deadline(deadline)
        for model in (initial, final):
            model.rollout(origin_at=point.origin.at, air_f=point.origin.air_f,
                          mass_f=point.origin.mass_f, forcings=point.forcings)
    days = sorted({p.origin.at.astimezone(DENVER).date() for p in points})
    if not isinstance(blocks, list) or len(blocks) != (BLOCK_REFIT_GROUPS if len(days) >= BLOCK_REFIT_MIN_INDEPENDENT_DAYS else 0):
        raise ValueError('actual deterministic refit coefficients missing')
    block_diagnostics = []; index = 0
    def refit(retained):
        nonlocal index
        _check_deadline(deadline)
        block = blocks[index]
        expected_days = [day.isoformat() for day in days[index::BLOCK_REFIT_GROUPS]]
        if (not isinstance(block, dict) or set(block) != {'group', 'omitted_days', 'coefficients'} or
                type(block['group']) is not int or block['group'] != index or block['omitted_days'] != expected_days or
                not isinstance(block['coefficients'], list)):
            raise ValueError('original deterministic omitted-day assignment differs')
        model = InstalledShadeDynamics(tuple(block['coefficients']))
        matrix = _objective(model.coefficients, _prepare_batches(retained), deadline=deadline)[2]
        rank, condition = _conditioning(matrix)
        for point in retained:
            _check_deadline(deadline)
            model.rollout(origin_at=point.origin.at, air_f=point.origin.air_f,
                          mass_f=point.origin.mass_f, forcings=point.forcings)
        block_diagnostics.append(dict(group=index, rank=rank, condition_number=condition))
        index += 1
        return model.coefficients
    stability = _assess_stability(points, final.coefficients, refitter=refit)
    support = dict(origin_counts={str(h): len(rows) for h, rows in groups},
        nonoverlapping_windows={str(h): _nonoverlap_count(rows) for h, rows in groups},
        unique_local_days=len(days), regimes=dict(sorted(Counter(p.origin.mode if p.origin.mode is not None else 'unknown' for p in points).items())))
    evidence = dict(schema=EVIDENCE_SCHEMA, candidate_payload_sha256=_digest(payload), limits=_limits(),
        initial_coefficients=list(initial.coefficients),
        optimizer=dict(initial_objective=initial_loss, final_objective=final_loss, iterations=iterations),
        conditioning=dict(initial_rank=initial_rank, initial_condition_number=initial_condition,
                          final_rank=final_rank, final_condition_number=final_condition),
        support=support, stability=asdict(stability), block_conditioning=block_diagnostics,
        fit_gates_passed=stability.assessed, release_authorized=False)
    # Normalize immutable dataclass tuples to the persisted closed JSON shape.
    evidence = json.loads(_canonical(evidence))
    evidence['fit_evidence_sha256'] = _digest(evidence)
    _check_deadline(deadline)
    return evidence


def build_candidate_bundle(inputs, report, *, code_revision, runtime_revision, created_at, timeout_seconds=60):
    if not isinstance(report, DevelopmentFit): raise ValueError('source-bound development fit required')
    deadline = _deadline(timeout_seconds)
    payload = dict(schema=SCHEMA, domain='outdoor_shades_installed', status='development_candidate',
        dynamics=dict(step_minutes=5, parameter_names=list(PARAMETER_NAMES), coefficients=list(report.fit.model.coefficients)),
        source_snapshot_sha256=report.source_snapshot_sha256, sensor_epochs=dict(report.sensor_epochs),
        trained_from=_utc(report.training_start).isoformat(), trained_through=_utc(report.training_end).isoformat(),
        created_at=_utc(created_at).isoformat(), code_revision=_sha(code_revision), runtime_revision=_sha(runtime_revision),
        release_authorized=False, as_issued_evidence=False)
    evidence = _measure(payload, inputs, initial_coefficients=report.fit.initial_coefficients,
        blocks=json.loads(_canonical([asdict(row) for row in report.stability.refits])),
        iterations=report.fit.iterations, deadline=deadline)
    expected = (report.fit.initial_objective, report.fit.final_objective, report.fit.conditioning_rank,
                report.fit.normalized_condition_number, dict(report.origin_counts), dict(report.independent_window_counts))
    measured = (evidence['optimizer']['initial_objective'], evidence['optimizer']['final_objective'],
        evidence['conditioning']['final_rank'], evidence['conditioning']['final_condition_number'],
        {int(k): v for k, v in evidence['support']['origin_counts'].items()},
        {int(k): v for k, v in evidence['support']['nonoverlapping_windows'].items()})
    if _canonical(expected) != _canonical(measured) or _canonical(asdict(report.stability)) != _canonical(evidence['stability']):
        raise ValueError('reported numerical fit differs from original source replay')
    artifact = {**payload, 'fit_evidence_sha256': evidence['fit_evidence_sha256']}
    artifact['artifact_sha256'] = _digest(artifact)
    _shape(artifact, expected_runtime_revision=runtime_revision, assessed_at=created_at)
    return dict(artifact=artifact, fit_evidence=evidence)


def validate_candidate_bundle(bundle, inputs, *, expected_runtime_revision, assessed_at, timeout_seconds=60):
    deadline = _deadline(timeout_seconds)
    if not isinstance(bundle, dict) or set(bundle) != {'artifact', 'fit_evidence'} or len(_canonical(bundle)) > MAX_BYTES:
        raise ValueError('closed bounded candidate/evidence bundle required')
    artifact, evidence = bundle['artifact'], bundle['fit_evidence']
    model = _shape(artifact, expected_runtime_revision=expected_runtime_revision, assessed_at=assessed_at)
    if (not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS or evidence['schema'] != EVIDENCE_SCHEMA or
            evidence['release_authorized'] is not False or evidence['fit_evidence_sha256'] != artifact['fit_evidence_sha256'] or
            _digest({k: v for k, v in evidence.items() if k != 'fit_evidence_sha256'}) != evidence['fit_evidence_sha256']):
        raise ValueError('closed original numerical evidence required')
    if not isinstance(evidence['stability'], dict) or 'refits' not in evidence['stability'] or not isinstance(evidence['optimizer'], dict) or 'iterations' not in evidence['optimizer']:
        raise ValueError('original fit/refit measurements required')
    measured = _measure(_payload(artifact), inputs, initial_coefficients=evidence['initial_coefficients'],
        blocks=evidence['stability']['refits'], iterations=evidence['optimizer']['iterations'], deadline=deadline)
    if _canonical(measured) != _canonical(evidence): raise ValueError('candidate evidence differs from original source replay')
    return model


def _persist(root, value, digest, suffix):
    target = root/(digest+suffix); raw = _canonical(value)
    if target.exists():
        if _owned_bytes(target, MAX_BYTES) != raw: raise ValueError('original immutable candidate member differs')
        return target
    temporary = root/('.candidate-'+uuid4().hex)
    try:
        _write_private(temporary, raw); _rename_new(temporary, target); _sync_directory(root)
    finally:
        if temporary.exists(): temporary.unlink()
    return target


def write_candidate_bundle(directory, bundle, inputs, **validation):
    bundle, inputs = deepcopy(bundle), deepcopy(inputs)
    validate_candidate_bundle(bundle, inputs, **validation)
    root = _private_directory(Path(directory))
    write_training_inputs_v2(root, inputs)
    _persist(root, bundle['fit_evidence'], bundle['fit_evidence']['fit_evidence_sha256'], '.installed-shade-fit-v1.json')
    return _persist(root, bundle['artifact'], bundle['artifact']['artifact_sha256'], '.installed-shade-candidate-v1.json')


def _read(path):
    def reject(_): raise ValueError('nonfinite candidate JSON')
    try: return json.loads(_owned_bytes(path, MAX_BYTES), object_pairs_hook=_object, parse_constant=reject)
    except (UnicodeDecodeError, json.JSONDecodeError): raise ValueError('candidate JSON unreadable') from None


def read_candidate_bundle(path, **validation):
    path = Path(path); root = _private_directory(path.parent); artifact = _read(path)
    if not isinstance(artifact, dict) or set(artifact) != ARTIFACT_FIELDS: raise ValueError('closed candidate file required')
    for key in ('artifact_sha256', 'fit_evidence_sha256', 'source_snapshot_sha256'): _sha(artifact[key])
    if path.name != artifact['artifact_sha256']+'.installed-shade-candidate-v1.json': raise ValueError('candidate address differs')
    evidence = _read(root/(artifact['fit_evidence_sha256']+'.installed-shade-fit-v1.json'))
    inputs = read_training_inputs_v2(root/(artifact['source_snapshot_sha256']+'.training-inputs-v2.json'))
    bundle = dict(artifact=artifact, fit_evidence=evidence)
    validate_candidate_bundle(bundle, inputs, **validation)
    return deepcopy(bundle)
