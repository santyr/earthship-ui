"""Versioned aggregate candidate binding core physics and source calibration.

Shape checks alone confer no source or release authority. Public preparation,
storage and reading replay the separate original calibration sources first.
"""
from copy import deepcopy
from pathlib import Path

from .forcing_capture import _canonical, _private_directory
from .graduation_policy import _utc, _sha, _finite
from .installed_shade_artifact import _digest, _shape as _base_shape
from .installed_shade_calibration import (_method, _regimes, validate_calibration,
    write_calibration, read_calibration, _persist, _read_json)
from .installed_shade_fit import HORIZONS
from .installed_shade_origin import RUNTIME_PATHS as BASE_PATHS
from .origin_capture import _runtime

SCHEMA = 'earthship-installed-shade-candidate/v2'
MAX_BYTES = 200000
RUNTIME_PATHS = BASE_PATHS | {'thermal_model/installed_shade_calibration.py',
    'thermal_model/installed_shade_calibrated_artifact.py',
    'thermal_model/installed_shade_calibrated_origin.py'}
FIELDS = {'schema','domain','status','base_candidate','base_runtime','runtime',
    'calibration','sensor_epochs','trained_from','trained_through','created_at',
    'code_revision','runtime_revision','release_authorized','as_issued_evidence','artifact_sha256'}
CALIBRATION_FIELDS = {'calibration_sha256','calibration_start','calibration_end',
    'created_at','method','regimes','bands'}


def _compatible_runtime(base, runtime):
    _runtime(base); _runtime(runtime)
    if (not BASE_PATHS <= set(base['source_manifest']) or
            not RUNTIME_PATHS <= set(runtime['source_manifest']) or
            any(runtime[key] != base[key] for key in
                ('observer_revision','interpreter_sha256','python_version','dependencies')) or
            any(runtime['source_manifest'].get(name) != value for name,value in base['source_manifest'].items())):
        raise ValueError('calibrated runtime must preserve original base source/dependency closure')


def _metadata(calibration):
    return {key:deepcopy(calibration[key]) for key in CALIBRATION_FIELDS-{'bands'}} | {
        'bands':{hours:dict(overall=value['overall']['radius_f'],
            regimes={regime:cell['radius_f'] for regime,cell in value['regimes'].items()})
            for hours,value in calibration['summary']['bands'].items()}}


def _shape(artifact, *, expected_runtime_revision, assessed_at):
    if (not isinstance(artifact,dict) or set(artifact)!=FIELDS or len(_canonical(artifact))>MAX_BYTES or
            artifact['schema']!=SCHEMA or artifact['domain']!='outdoor_shades_installed' or
            artifact['status']!='development_candidate' or artifact['release_authorized'] is not False or
            artifact['as_issued_evidence'] is not False):
        raise ValueError('closed calibrated installed-shade candidate required')
    if _digest({k:v for k,v in artifact.items() if k!='artifact_sha256'}) != _sha(artifact['artifact_sha256']):
        raise ValueError('calibrated candidate digest differs')
    _compatible_runtime(artifact['base_runtime'],artifact['runtime'])
    base_revision = _digest(artifact['base_runtime']); revision = _digest(artifact['runtime'])
    if (revision != _sha(expected_runtime_revision) or artifact['runtime_revision']!=revision or
            artifact['code_revision']!=artifact['runtime']['code_revision']):
        raise ValueError('calibrated runtime identity differs')
    model = _base_shape(artifact['base_candidate'],expected_runtime_revision=base_revision,assessed_at=assessed_at)
    base = artifact['base_candidate']; calibration = artifact['calibration']
    if (not isinstance(calibration,dict) or set(calibration)!=CALIBRATION_FIELDS or
            _canonical(calibration['method'])!=_canonical(_method()) or
            calibration['regimes']!=_regimes(calibration['regimes'])):
        raise ValueError('closed fixed calibration method required')
    _sha(calibration['calibration_sha256'])
    start,end,calibrated,created = map(_utc,(calibration['calibration_start'],calibration['calibration_end'],
        calibration['created_at'],artifact['created_at']))
    if (not _utc(base['created_at']) <= start < end <= calibrated <= created <= _utc(assessed_at) or
            artifact['sensor_epochs']!=base['sensor_epochs'] or
            _utc(artifact['trained_from'])!=_utc(base['trained_from']) or _utc(artifact['trained_through'])!=end):
        raise ValueError('aggregate learning cutoff or sensor binding differs')
    bands = calibration['bands']
    if not isinstance(bands,dict) or set(bands)!={str(h) for h in HORIZONS}:
        raise ValueError('all required calibrated horizon cells required')
    for value in bands.values():
        if (not isinstance(value,dict) or set(value)!={'overall','regimes'} or
                not isinstance(value['regimes'],dict) or set(value['regimes'])!=set(calibration['regimes'])):
            raise ValueError('exact calibrated regime cells required')
        for radius in [value['overall'],*value['regimes'].values()]:
            if radius is not None and _finite(radius)<0:
                raise ValueError('nonnegative original uncertainty radius required')
    return model


def _serialize(base_bundle,calibration,base_runtime,runtime,created_at):
    base = base_bundle['artifact']
    body = dict(schema=SCHEMA,domain='outdoor_shades_installed',status='development_candidate',
        base_candidate=deepcopy(base),base_runtime=deepcopy(base_runtime),runtime=deepcopy(runtime),
        calibration=_metadata(calibration),sensor_epochs=deepcopy(base['sensor_epochs']),
        trained_from=base['trained_from'],trained_through=calibration['calibration_end'],
        created_at=_utc(created_at).isoformat(),code_revision=runtime['code_revision'],
        runtime_revision=_digest(runtime),release_authorized=False,as_issued_evidence=False)
    body['artifact_sha256'] = _digest(body)
    return body


def build_calibrated_candidate(*, base_bundle, inputs, calibration, original_pairs,
                               base_runtime, runtime, created_at):
    _compatible_runtime(base_runtime,runtime)
    validate_calibration(calibration,bundle=base_bundle,inputs=inputs,original_pairs=original_pairs,
        expected_runtime_revision=_digest(base_runtime),assessed_at=created_at)
    result = _serialize(base_bundle,calibration,base_runtime,runtime,created_at)
    _shape(result,expected_runtime_revision=_digest(runtime),assessed_at=created_at)
    return result


def validate_calibrated_candidate(artifact, *, base_bundle, inputs, calibration, original_pairs,
                                  expected_runtime_revision, assessed_at):
    _shape(artifact,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at)
    validate_calibration(calibration,bundle=base_bundle,inputs=inputs,original_pairs=original_pairs,
        expected_runtime_revision=_digest(artifact['base_runtime']),assessed_at=artifact['created_at'])
    expected = _serialize(base_bundle,calibration,artifact['base_runtime'],artifact['runtime'],artifact['created_at'])
    if _canonical(expected)!=_canonical(artifact):
        raise ValueError('aggregate differs from original core/calibration source replay')
    return deepcopy(artifact)


def write_calibrated_candidate(directory, artifact, *, base_bundle, inputs, calibration,
                               original_pairs, expected_runtime_revision, assessed_at):
    artifact,base_bundle,inputs,calibration,original_pairs = deepcopy(
        (artifact,base_bundle,inputs,calibration,original_pairs))
    validate_calibrated_candidate(artifact,base_bundle=base_bundle,inputs=inputs,calibration=calibration,
        original_pairs=original_pairs,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at)
    root = _private_directory(Path(directory))
    write_calibration(root,calibration,bundle=base_bundle,inputs=inputs,original_pairs=original_pairs,
        expected_runtime_revision=_digest(artifact['base_runtime']),assessed_at=assessed_at)
    return _persist(root,artifact,artifact['artifact_sha256'],'.installed-shade-candidate-v2.json')


def read_calibrated_candidate(path, *, expected_runtime_revision, assessed_at):
    path=Path(path);root=_private_directory(path.parent);artifact=_read_json(path)
    _shape(artifact,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at)
    if path.name!=artifact['artifact_sha256']+'.installed-shade-candidate-v2.json':
        raise ValueError('calibrated candidate address differs')
    calibration=read_calibration(root/(artifact['calibration']['calibration_sha256']+'.installed-shade-calibration-v1.json'),
        expected_runtime_revision=_digest(artifact['base_runtime']),assessed_at=artifact['created_at'])
    if (calibration['base_candidate_sha256']!=artifact['base_candidate']['artifact_sha256'] or
            calibration['sensor_epochs']!=artifact['sensor_epochs'] or
            _canonical(_metadata(calibration))!=_canonical(artifact['calibration'])):
        raise ValueError('calibrated metadata differs from original source replay')
    from .installed_shade_artifact import _read
    pointer=artifact['base_candidate']['fit_evidence_sha256']
    evidence=_read(root/(pointer+'.installed-shade-fit-v1.json'))
    if evidence.get('fit_evidence_sha256')!=pointer or _digest({k:v for k,v in evidence.items() if k!='fit_evidence_sha256'})!=pointer:
        raise ValueError('original source-verified fit proof changed')
    return dict(artifact=deepcopy(artifact),calibration=calibration,fit_evidence=evidence)
