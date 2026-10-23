"""Native provisional artifact with retained originals and a versioned runtime.

Building or validating this artifact never selects a model, publishes forecasts,
claims as-issued skill, or grants physical authority.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
import time
import numpy as np
from pathlib import Path
import re
from thermal_model.forcing_capture import _canonical, _private_directory
from thermal_model.graduation_policy import _utc, _sha
from thermal_model.origin_capture import _runtime, _source_bytes, _object
from thermal_model.native_operational_io import current_runtime as current_base_runtime
from thermal_model.provisional_artifact import FIT_FIELDS as BASE_FIT_FIELDS, candidate_digest, validate_candidate
from thermal_model.runtime_bundle import _owned_bytes
from thermal_model.training_inputs import read_training_inputs_v2
from thermal_model.installed_shade_artifact import _persist
from astro_geometry_series import replay_series
from native_thermal_inputs import replay_native_development, solar_feature_contract
from native_thermal_model import RULE
from native_thermal_fit import SCHEMA as FIT_SCHEMA, prepare_native_batches, _points
from native_thermal_model import NativeInstalledShadeDynamics
from thermal_model.installed_shade_fit import _objective
from thermal_model.installed_shade_dynamics import LOWER, UPPER
from thermal_model.actions import DENVER

SCHEMA = 'earthship-provisional-thermal-candidate/v2'
JOINT_SCHEMA = 'earthship-provisional-thermal-candidate/v3'
IRRADIANCE_SCHEMA='earthship-provisional-thermal-candidate/v4'
SCHEMAS={SCHEMA,JOINT_SCHEMA,IRRADIANCE_SCHEMA}
IRRADIANCE_SOURCES={'openhab/scripts/native_irradiance_shade.py'}
JOINT_SOURCES={'openhab/scripts/native_joint_shade.py','openhab/thermal-shade-context.json'}
RUNTIME_SCHEMA = 'earthship-native-thermal-runtime-binding/v1'
FIT_EVIDENCE_SCHEMA = 'earthship-native-development-fit-evidence/v2'
ROOT = Path(__file__).resolve().parents[2]
REQUIRED_SOURCES = frozenset('openhab/scripts/'+name for name in (
    'native_thermal_inputs.py', 'native_thermal_model.py', 'native_thermal_fit.py',
    'native_thermal_artifact.py', 'astro_geometry.py', 'astro_geometry_series.py',
    'astro_forecast_context.py', 'astro_geometry_worker.py')) | {'scripts/java/NativeSolarGeometry.java'}
OPTIONAL_SOURCES = frozenset('openhab/scripts/'+name for name in (
    'native_thermal_forecast.py', 'native_thermal_live.py', 'native_thermal_score.py'))
CONDITIONING_SOURCES = frozenset('openhab/scripts/'+name for name in (
    'production_thermal_source.py','thermal_weather_source.py',
    'household/production_weather_conditioning.py','household/thermal_weather_conditioning.py'))
RUNTIME_FIELDS = {'schema', 'base_runtime', 'native_source_manifest', 'native_code_revision'}
FIELDS = {'schema', 'created_at', 'runtime', 'runtime_sha256', 'originals', 'fit', 'artifact_sha256'}
FIT_FIELDS = BASE_FIT_FIELDS | {'schema', 'model_rule', 'solar_feature', 'dataset_sha256',
                              'geometry_series_sha256', 'as_issued_forecast', 'release_authorized'}
EVIDENCE_FIELDS = {'schema', 'created_at', 'code_revision', 'fit_runtime', 'fit',
                   'release_authorized', 'production_model_changed'}
LIMITS = {'snapshot': 16*1024*1024, 'dataset': 8*1024*1024, 'geometry': 4*1024*1024, 'fit_evidence': 131072}


def digest(value, field=None):
    body = value if field is None else {k:v for k,v in value.items() if k != field}
    return sha256(_canonical(body)).hexdigest()


def validate_native_runtime(value):
    if not isinstance(value, dict) or set(value) != RUNTIME_FIELDS or value['schema'] != RUNTIME_SCHEMA:
        raise ValueError('closed native model runtime required')
    _runtime(value['base_runtime'])
    sources = value['native_source_manifest']
    if (not isinstance(sources, dict) or not REQUIRED_SOURCES <= set(sources) <= REQUIRED_SOURCES | OPTIONAL_SOURCES | CONDITIONING_SOURCES | JOINT_SOURCES | IRRADIANCE_SOURCES or
            digest(sources) != _sha(value['native_code_revision'])):
        raise ValueError('complete original native source closure required')
    if set(sources)&CONDITIONING_SOURCES and not CONDITIONING_SOURCES<=set(sources):
        raise ValueError('complete production thermal conditioning closure required')
    for identity in sources.values(): _sha(identity)
    return deepcopy(value)


def current_native_runtime(*, guard=lambda: None):
    guard(); base = current_base_runtime(); guard()
    names = REQUIRED_SOURCES | {name for name in OPTIONAL_SOURCES | CONDITIONING_SOURCES | JOINT_SOURCES | IRRADIANCE_SOURCES if (ROOT/name).exists()}
    sources = {}
    for name in sorted(names):
        guard(); sources[name] = sha256(_source_bytes(ROOT/name, maximum=2000000)).hexdigest()
    value = dict(schema=RUNTIME_SCHEMA, base_runtime=base,
                 native_source_manifest=sources, native_code_revision=digest(sources))
    for name, identity in sources.items():
        guard()
        if sha256(_source_bytes(ROOT/name, maximum=2000000)).hexdigest() != identity:
            raise ValueError('native source changed during runtime capture')
    if _canonical(current_base_runtime()) != _canonical(base):
        raise ValueError('native interpreter/dependencies/base sources changed')
    guard(); return validate_native_runtime(value)


def _read(path, maximum):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('resolved original native artifact path required')
    _private_directory(path.parent); raw = _owned_bytes(path, maximum)
    def nonfinite(_): raise ValueError('nonfinite native artifact JSON')
    try: value = json.loads(raw, object_pairs_hook=_object, parse_constant=nonfinite)
    except (UnicodeError, json.JSONDecodeError): raise ValueError('original native artifact JSON required') from None
    return raw, value


def _fit_environment(fitted, current, *, joint=False, irradiance=False):
    fitted = validate_native_runtime(fitted); current = validate_native_runtime(current)
    if (_canonical(fitted['base_runtime']) != _canonical(current['base_runtime']) or
            any(fitted['native_source_manifest'][name] != current['native_source_manifest'][name] for name in REQUIRED_SOURCES | (JOINT_SOURCES if joint else set()) | (IRRADIANCE_SOURCES if irradiance else set()))):
        raise ValueError('native fit environment/source closure differs')


def _references(paths):
    if not isinstance(paths, dict) or set(paths) != set(LIMITS):
        raise ValueError('complete retained native dependencies required')
    return {role: dict(path=str(path), sha256=sha256(_read(path, LIMITS[role])[0]).hexdigest())
            for role, path in paths.items()}


def fit_profile(fit):
    if not isinstance(fit,dict):raise ValueError('explicit original fit object required')
    if fit.get('schema')==FIT_SCHEMA:
        return dict(joint=False,fields=FIT_FIELDS,rule=RULE,model=NativeInstalledShadeDynamics,lower=LOWER,upper=UPPER,objective=_objective,count=10,irradiance=False,solar_feature=solar_feature_contract)
    if fit.get('schema') in ('earthship-native-solar-provisional-fit/v2','earthship-native-solar-provisional-fit/v3'):
        import native_joint_shade as j
        import native_irradiance_shade as ir
        irradiance=fit['schema']=='earthship-native-solar-provisional-fit/v3'
        return dict(joint=True,fields=FIT_FIELDS|{'shade_context','regime_support'},rule=ir.RULE if irradiance else j.RULE,
            model=ir.NativeIrradianceShadeDynamics if irradiance else j.NativeJointShadeDynamics,
            lower=j.LOWER,upper=j.UPPER,objective=j.objective,count=14,irradiance=irradiance,
            solar_feature=ir.solar_feature_contract if irradiance else solar_feature_contract)
    raise ValueError('unsupported native fitting profile')


def _statistics(fit, data, guard):
    profile=fit_profile(fit);joint=profile['joint']
    model_type=profile['model'];objective=profile['objective']
    deadline = time.monotonic()+85
    def check():
        guard()
        if time.monotonic() > deadline: raise ValueError('native artifact replay budget expired')
    points, support = _points(data, fit['training_start'], fit['training_end'], check, joint=joint)
    if (support != fit['horizon_support'] or len(points) != fit['endpoint_count'] or
            len({p.origin.at.astimezone(DENVER).date() for p in points}) != fit['independent_origin_dates']):
        raise ValueError('native fit support differs from original endpoints')
    batches = prepare_native_batches(data, training_start=fit['training_start'],
        training_end=fit['training_end'], deadline=deadline, guard=check, joint=joint, irradiance=profile['irradiance'])
    initial, _, sensitivity = objective(fit['initial_coefficients'], batches, deadline=deadline)
    final, _, _ = objective(fit['coefficients'], batches, deadline=deadline)
    if (not math.isclose(initial, fit['initial_objective'], rel_tol=1e-9, abs_tol=1e-9) or
            not math.isclose(final, fit['final_objective'], rel_tol=1e-9, abs_tol=1e-9)):
        raise ValueError('native fit losses differ from original endpoint predictions')
    scaled = sensitivity*(np.asarray(profile['upper'])-np.asarray(profile['lower']))
    rank = int(np.linalg.matrix_rank(scaled))
    if rank != fit['conditioning_rank']: raise ValueError('native fit sensitivity rank differs')
    if rank == profile['count']:
        singular = np.linalg.svd(scaled, compute_uv=False)
        if not math.isclose(float(singular[0]/singular[-1]), fit['normalized_condition_number'], rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError('native fit conditioning differs')
    for name in ('initial_coefficients', 'coefficients'):
        model = model_type(tuple(fit[name]), geometry=data.geometry,
                                            expected_series_sha256=data.geometry.sha256)
        for point in points:
            check(); model.rollout(origin_at=point.origin.at, air_f=point.origin.air_f,
                mass_f=point.origin.mass_f, forcings=point.forcings, guard=check)
    if joint:
        import native_joint_shade as j
        if _canonical(fit['regime_support'])!=_canonical(j.regime_support(data,points,start=fit['training_start'],end=fit['training_end'])):
            raise ValueError('joint regime support differs from original measurements/endpoints')
    check()


def validate_native_candidate(value, *, assessed_at, runtime, expected_artifact_sha256, guard=lambda: None):
    try:
        guard(); runtime = validate_native_runtime(runtime)
        if (not isinstance(value, dict) or set(value) != FIELDS or value['schema'] not in SCHEMAS or
                value['artifact_sha256'] != _sha(expected_artifact_sha256) or
                digest(value, 'artifact_sha256') != value['artifact_sha256'] or
                _canonical(validate_native_runtime(value['runtime'])) != _canonical(runtime) or
                digest(runtime) != _sha(value['runtime_sha256'])):
            raise ValueError('original native candidate/runtime identity required')
        fit = value['fit']
        profile=fit_profile(fit);joint=profile['joint']
        if value['schema']!=(IRRADIANCE_SCHEMA if profile['irradiance'] else JOINT_SCHEMA if joint else SCHEMA):raise ValueError('native candidate profile version differs')
        if joint:
            import native_joint_shade as j
            if not JOINT_SOURCES<=set(runtime['native_source_manifest']) or _canonical(fit['shade_context'])!=_canonical(j.shade_contract()):raise ValueError('original joint source/context required')
        if (not isinstance(fit, dict) or set(fit) != profile['fields'] or
                fit['model_rule'] != profile['rule'] or _canonical(fit['solar_feature']) != _canonical(profile['solar_feature']()) or
                fit['as_issued_forecast'] is not False or fit['release_authorized'] is not False):
            raise ValueError('closed native provisional learning contract required')
        for key in ('dataset_sha256', 'geometry_series_sha256'): _sha(fit[key])
        refs = value['originals']
        if not isinstance(refs, dict) or set(refs) != set(LIMITS):
            raise ValueError('complete original native dependencies required')
        raw = {}; original = {}; paths = {}
        for role, reference in refs.items():
            guard()
            if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
                raise ValueError('closed original native reference required')
            paths[role] = Path(reference['path']); raw[role], original[role] = _read(paths[role], LIMITS[role])
            if sha256(raw[role]).hexdigest() != _sha(reference['sha256']):
                raise ValueError('retained native dependency changed')
        # Reuse every existing coefficient/support/phase/chronology guard.
        base = runtime['base_runtime']
        legacy = dict(schema='earthship-provisional-thermal-candidate/v1', created_at=value['created_at'],
            runtime=base, runtime_sha256=digest(base), snapshot_path=str(paths['snapshot']),
            snapshot_file_sha256=refs['snapshot']['sha256'], fit={key:fit[key] for key in BASE_FIT_FIELDS})
        legacy['artifact_sha256'] = candidate_digest(legacy)
        if joint:j.validate_fit_metadata(fit,created_at=value['created_at'],assessed_at=assessed_at)
        else:validate_candidate(legacy, assessed_at=assessed_at, runtime=base)
        guard()
        evidence = original['fit_evidence']
        if (not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS or
                evidence['schema'] != ('earthship-native-development-fit-evidence/v4' if profile['irradiance'] else 'earthship-native-development-fit-evidence/v3' if joint else FIT_EVIDENCE_SCHEMA) or evidence['release_authorized'] is not False or
                evidence['production_model_changed'] is not False or
                re.fullmatch('[0-9a-f]{40}', evidence['code_revision']) is None or
                _canonical(evidence['fit']) != _canonical(fit)):
            raise ValueError('original runtime-bound fitting evidence required')
        _fit_environment(evidence['fit_runtime'], runtime, joint=joint, irradiance=profile['irradiance'])
        record = read_training_inputs_v2(paths['snapshot']); guard()
        if record['snapshot_sha256'] != fit['source_snapshot_sha256']:
            raise ValueError('native model source snapshot differs')
        packet = original['geometry']
        geometry = replay_series(raw['geometry'], request=packet['request'],
            expected_series_sha256=fit['geometry_series_sha256'], expected_native_runtime=packet['native_runtime'])
        data = replay_native_development(raw['dataset'], record=record,
            expected_dataset_sha256=fit['dataset_sha256'], expected_snapshot_sha256=fit['source_snapshot_sha256'],
            sensor_epochs=fit['sensor_epochs'], geometry=geometry, expected_series_sha256=fit['geometry_series_sha256']); guard()
        if not data.development.start <= _utc(fit['training_start']) < _utc(fit['training_end']) <= data.development.end:
            raise ValueError('native fitting interval differs from retained dataset')
        if not _utc(data.to_dict()['assessed_at']) <= _utc(evidence['created_at']) <= _utc(value['created_at']) <= _utc(assessed_at):
            raise ValueError('native dataset/fit/artifact chronology differs')
        _statistics(fit, data, guard)
        for role, reference in refs.items():
            guard()
            if sha256(_read(paths[role], LIMITS[role])[0]).hexdigest() != reference['sha256']:
                raise ValueError('native original changed across artifact validation')
    except (OSError, TypeError, KeyError, OverflowError):
        raise ValueError('invalid native provisional artifact') from None
    return deepcopy(value)


def build_native_candidate(*, originals, runtime, created_at, guard=lambda: None):
    refs = _references(originals)
    fit = _read(originals['fit_evidence'], LIMITS['fit_evidence'])[1]['fit']
    profile=fit_profile(fit)
    value = dict(schema=IRRADIANCE_SCHEMA if profile['irradiance'] else JOINT_SCHEMA if profile['joint'] else SCHEMA, created_at=_utc(created_at).isoformat(),
        runtime=validate_native_runtime(runtime), runtime_sha256=digest(runtime), originals=refs, fit=deepcopy(fit))
    value['artifact_sha256'] = digest(value, 'artifact_sha256')
    return validate_native_candidate(value, assessed_at=created_at, runtime=runtime,
                                    expected_artifact_sha256=value['artifact_sha256'], guard=guard)


def write_native_candidate(directory, value, *, assessed_at, runtime, expected_artifact_sha256, guard=lambda: None):
    value = validate_native_candidate(value, assessed_at=assessed_at, runtime=runtime,
        expected_artifact_sha256=expected_artifact_sha256, guard=guard)
    return _persist(_private_directory(Path(directory)), value, value['artifact_sha256'], '.native-provisional-candidate-v4.json' if value['schema']==IRRADIANCE_SCHEMA else '.native-provisional-candidate-v3.json' if value['schema']==JOINT_SCHEMA else '.native-provisional-candidate-v2.json')


def read_native_candidate(path, *, assessed_at, runtime, expected_artifact_sha256, guard=lambda: None):
    return validate_native_candidate(_read(path, 131072)[1], assessed_at=assessed_at, runtime=runtime,
                                    expected_artifact_sha256=expected_artifact_sha256, guard=guard)
