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
    write_calibration, read_calibration, _persist, _read_json,
    validate_raw_calibration, write_raw_calibration, read_raw_calibration, RAW_SCHEMA as RAW_CALIBRATION_SCHEMA,
    RAW_SOURCE_CONTRACT, validate_source_calibration, write_source_calibration, read_source_calibration,
    SOURCE_SCHEMA as SOURCE_CALIBRATION_SCHEMA, SOURCE_CONTRACT, _source_operation, _raw_packet_digest,
    validate_compressed_source_calibration,write_compressed_source_calibration,read_compressed_source_calibration,
    COMPRESSED_SOURCE_SCHEMA as COMPRESSED_CALIBRATION_SCHEMA,COMPRESSED_SOURCE_CONTRACT)
from .installed_shade_fit import HORIZONS
from .installed_shade_origin import RUNTIME_PATHS as BASE_PATHS
from .origin_capture import _runtime

SCHEMA = 'earthship-installed-shade-candidate/v2'
RAW_SCHEMA = 'earthship-installed-shade-candidate/v3'
SOURCE_SCHEMA = 'earthship-installed-shade-candidate/v4'
COMPRESSED_SOURCE_SCHEMA = 'earthship-installed-shade-candidate/v5'
_SCHEMAS = {2:SCHEMA,3:RAW_SCHEMA,4:SOURCE_SCHEMA,5:COMPRESSED_SOURCE_SCHEMA}
_CALIBRATION_VALIDATORS = {2:validate_calibration,3:validate_raw_calibration,4:validate_source_calibration,5:validate_compressed_source_calibration}
MAX_BYTES = 200000
RUNTIME_PATHS = BASE_PATHS | {'thermal_model/installed_shade_calibration.py',
    'thermal_model/installed_shade_calibrated_artifact.py',
    'thermal_model/installed_shade_calibrated_origin.py'}
FIELDS = {'schema','domain','status','base_candidate','base_runtime','runtime',
    'calibration','sensor_epochs','trained_from','trained_through','created_at',
    'code_revision','runtime_revision','release_authorized','as_issued_evidence','artifact_sha256'}
CALIBRATION_FIELDS = {'calibration_sha256','calibration_start','calibration_end',
    'created_at','method','regimes','bands'}

RAW_CALIBRATION_FIELDS = CALIBRATION_FIELDS | {'schema','source_contract'}


def _check_version(value):
    if type(value) is not int or value not in (2,3,4,5):
        raise ValueError('explicit calibrated candidate version required')
    return value


def _compatible_runtime(base, runtime, *, _version=2):
    _runtime(base); _runtime(runtime)
    _check_version(_version)
    required = RUNTIME_PATHS
    if _version in (3,4,5):
        # Use the complete executing raw replay/publication closure. Import at
        # the call site because the publisher itself imports candidate readers.
        from .installed_shade_publication import RAW_RUNTIME_PATHS
        required = RAW_RUNTIME_PATHS
    if (not BASE_PATHS <= set(base['source_manifest']) or
            not required <= set(runtime['source_manifest']) or
            any(runtime[key] != base[key] for key in
                ('observer_revision','interpreter_sha256','python_version','dependencies')) or
            any(runtime['source_manifest'].get(name) != value for name,value in base['source_manifest'].items())):
        raise ValueError('calibrated runtime must preserve original base source/dependency closure')


def _metadata(calibration, *, _version=2):
    result = {key:deepcopy(calibration[key]) for key in CALIBRATION_FIELDS-{'bands'}} | {
        'bands':{hours:dict(overall=value['overall']['radius_f'],
            regimes={regime:cell['radius_f'] for regime,cell in value['regimes'].items()})
            for hours,value in calibration['summary']['bands'].items()}}
    if _version in (3,4,5):result.update(schema=calibration['schema'],source_contract=calibration['source_contract'])
    return result


def _shape(artifact, *, expected_runtime_revision, assessed_at, _version=2):
    _check_version(_version)
    if (not isinstance(artifact,dict) or set(artifact)!=FIELDS or len(_canonical(artifact))>MAX_BYTES or
            artifact['schema']!=_SCHEMAS[_version] or artifact['domain']!='outdoor_shades_installed' or
            artifact['status']!='development_candidate' or artifact['release_authorized'] is not False or
            artifact['as_issued_evidence'] is not False):
        raise ValueError('closed calibrated installed-shade candidate required')
    if _digest({k:v for k,v in artifact.items() if k!='artifact_sha256'}) != _sha(artifact['artifact_sha256']):
        raise ValueError('calibrated candidate digest differs')
    _compatible_runtime(artifact['base_runtime'],artifact['runtime'],_version=_version)
    base_revision = _digest(artifact['base_runtime']); revision = _digest(artifact['runtime'])
    if (revision != _sha(expected_runtime_revision) or artifact['runtime_revision']!=revision or
            artifact['code_revision']!=artifact['runtime']['code_revision']):
        raise ValueError('calibrated runtime identity differs')
    model = _base_shape(artifact['base_candidate'],expected_runtime_revision=base_revision,assessed_at=assessed_at)
    base = artifact['base_candidate']; calibration = artifact['calibration']
    if (not isinstance(calibration,dict) or set(calibration)!=(RAW_CALIBRATION_FIELDS if _version in (3,4,5) else CALIBRATION_FIELDS) or
            (_version in (3,4,5) and (calibration['schema']!=({3:RAW_CALIBRATION_SCHEMA,4:SOURCE_CALIBRATION_SCHEMA,5:COMPRESSED_CALIBRATION_SCHEMA}[_version]) or
                calibration['source_contract']!=({3:RAW_SOURCE_CONTRACT,4:SOURCE_CONTRACT,5:COMPRESSED_SOURCE_CONTRACT}[_version]))) or
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


def _serialize(base_bundle,calibration,base_runtime,runtime,created_at, *, _version=2):
    base = base_bundle['artifact']
    body = dict(schema=_SCHEMAS[_version],domain='outdoor_shades_installed',status='development_candidate',
        base_candidate=deepcopy(base),base_runtime=deepcopy(base_runtime),runtime=deepcopy(runtime),
        calibration=_metadata(calibration,_version=_version),sensor_epochs=deepcopy(base['sensor_epochs']),
        trained_from=base['trained_from'],trained_through=calibration['calibration_end'],
        created_at=_utc(created_at).isoformat(),code_revision=runtime['code_revision'],
        runtime_revision=_digest(runtime),release_authorized=False,as_issued_evidence=False)
    body['artifact_sha256'] = _digest(body)
    return body


def _build_calibrated_candidate(*, base_bundle, inputs, calibration, original_pairs,
                               base_runtime, runtime, created_at, _version=2):
    _compatible_runtime(base_runtime,runtime,_version=_version)
    _CALIBRATION_VALIDATORS[_version](calibration,bundle=base_bundle,inputs=inputs,original_pairs=original_pairs,
        expected_runtime_revision=_digest(base_runtime),assessed_at=created_at)
    result = _serialize(base_bundle,calibration,base_runtime,runtime,created_at,_version=_version)
    _shape(result,expected_runtime_revision=_digest(runtime),assessed_at=created_at,_version=_version)
    if _version in (4,5):
        _CALIBRATION_VALIDATORS[_version](calibration,bundle=base_bundle,inputs=inputs,original_pairs=original_pairs,
            expected_runtime_revision=_digest(base_runtime),assessed_at=created_at)
    return result


def _validate_calibrated_candidate(artifact, *, base_bundle, inputs, calibration, original_pairs,
                                  expected_runtime_revision, assessed_at, _version=2):
    _shape(artifact,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at,_version=_version)
    _CALIBRATION_VALIDATORS[_version](calibration,bundle=base_bundle,inputs=inputs,original_pairs=original_pairs,
        expected_runtime_revision=_digest(artifact['base_runtime']),assessed_at=artifact['created_at'])
    expected = _serialize(base_bundle,calibration,artifact['base_runtime'],artifact['runtime'],artifact['created_at'],_version=_version)
    if _canonical(expected)!=_canonical(artifact):
        raise ValueError('aggregate differs from original core/calibration source replay')
    return deepcopy(artifact)


def _write_calibrated_candidate(directory, artifact, *, base_bundle, inputs, calibration,
                               original_pairs, expected_runtime_revision, assessed_at, _version=2):
    artifact,base_bundle,inputs,calibration,original_pairs = deepcopy(
        (artifact,base_bundle,inputs,calibration,original_pairs))
    _validate_calibrated_candidate(artifact,base_bundle=base_bundle,inputs=inputs,calibration=calibration,
        original_pairs=original_pairs,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at,_version=_version)
    root = _private_directory(Path(directory))
    {2:write_calibration,3:write_raw_calibration,4:write_source_calibration,5:write_compressed_source_calibration}[_version](root,calibration,bundle=base_bundle,inputs=inputs,original_pairs=original_pairs,
        expected_runtime_revision=_digest(artifact['base_runtime']),assessed_at=assessed_at)
    options={}
    if _version in (4,5):
        reader=read_compressed_source_calibration if _version==5 else read_source_calibration
        def guard():
            original=reader(root/(calibration['calibration_sha256']+f'.installed-shade-calibration-v{_version-1}.json'),
                expected_runtime_revision=_digest(artifact['base_runtime']),assessed_at=assessed_at)
            if _canonical(original)!=_canonical(calibration):
                raise ValueError('original source calibration changed during candidate retention')
        options['before_publish']=guard
    path=_persist(root,artifact,artifact['artifact_sha256'],f'.installed-shade-candidate-v{_version}.json',**options)
    if _version in (4,5):guard()
    return path


def _read_calibrated_candidate(path, *, expected_runtime_revision, assessed_at, _version=2):
    path=Path(path);root=_private_directory(path.parent);artifact=_read_json(path)
    _shape(artifact,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at,_version=_version)
    if path.name!=artifact['artifact_sha256']+f'.installed-shade-candidate-v{_version}.json':
        raise ValueError('calibrated candidate address differs')
    calibration_path=root/(artifact['calibration']['calibration_sha256']+f'.installed-shade-calibration-v{_version-1}.json')
    calibration={2:read_calibration,3:read_raw_calibration,4:read_source_calibration,5:read_compressed_source_calibration}[_version](calibration_path,
        expected_runtime_revision=_digest(artifact['base_runtime']),assessed_at=artifact['created_at'])
    if (calibration['base_candidate_sha256']!=artifact['base_candidate']['artifact_sha256'] or
            calibration['sensor_epochs']!=artifact['sensor_epochs'] or
            _canonical(_metadata(calibration,_version=_version))!=_canonical(artifact['calibration'])):
        raise ValueError('calibrated metadata differs from original source replay')
    from .installed_shade_artifact import _read
    pointer=artifact['base_candidate']['fit_evidence_sha256']
    evidence=_read(root/(pointer+'.installed-shade-fit-v1.json'))
    if evidence.get('fit_evidence_sha256')!=pointer or _digest({k:v for k,v in evidence.items() if k!='fit_evidence_sha256'})!=pointer:
        raise ValueError('original source-verified fit proof changed')
    if _version in (4,5):
        reader=read_compressed_source_calibration if _version==5 else read_source_calibration
        current=reader(calibration_path,expected_runtime_revision=_digest(artifact['base_runtime']),assessed_at=assessed_at)
        if _canonical(current)!=_canonical(calibration):raise ValueError('original candidate calibration changed during readback')
    return dict(artifact=deepcopy(artifact),calibration=calibration,fit_evidence=evidence)



def build_calibrated_candidate(**values):
    """Legacy receipt-calibrated candidate, distinct from raw calibration proof."""
    return _build_calibrated_candidate(**values,_version=2)


def build_raw_calibrated_candidate(**values):
    return _build_calibrated_candidate(**values,_version=3)


def validate_calibrated_candidate(artifact,**values):
    return _validate_calibrated_candidate(artifact,**values,_version=2)


def validate_raw_calibrated_candidate(artifact,**values):
    return _validate_calibrated_candidate(artifact,**values,_version=3)


def write_calibrated_candidate(directory,artifact,**values):
    return _write_calibrated_candidate(directory,artifact,**values,_version=2)


def write_raw_calibrated_candidate(directory,artifact,**values):
    return _write_calibrated_candidate(directory,artifact,**values,_version=3)


def read_calibrated_candidate(path,**values):
    return _read_calibrated_candidate(path,**values,_version=2)


def read_raw_calibrated_candidate(path,**values):
    return _read_calibrated_candidate(path,**values,_version=3)


def build_source_calibrated_candidate(**values):
    """Freeze core physics with calibration replayed from original issue queries."""
    _raw_packet_digest(values['original_pairs'])
    return _source_operation(_build_calibrated_candidate,**deepcopy(values),_version=4)


def validate_source_calibrated_candidate(artifact,**values):
    _raw_packet_digest(values['original_pairs'])
    artifact,values=deepcopy((artifact,values))
    return _source_operation(_validate_calibrated_candidate,artifact,**values,_version=4)


def write_source_calibrated_candidate(directory,artifact,**values):
    _raw_packet_digest(values['original_pairs'])
    artifact,values=deepcopy((artifact,values))
    return _source_operation(_write_calibrated_candidate,directory,artifact,**values,_version=4)


def read_source_calibrated_candidate(path,**values):
    return _source_operation(_read_calibrated_candidate,path,**values,_version=4)


def build_compressed_source_calibrated_candidate(**values):
    """Freeze original physics/calibration4/source6; no release authority."""
    _raw_packet_digest(values['original_pairs'])
    return _source_operation(_build_calibrated_candidate,**deepcopy(values),_version=5)


def validate_compressed_source_calibrated_candidate(artifact,**values):
    _raw_packet_digest(values['original_pairs'])
    artifact,values=deepcopy((artifact,values))
    return _source_operation(_validate_calibrated_candidate,artifact,**values,_version=5)


def write_compressed_source_calibrated_candidate(directory,artifact,**values):
    _raw_packet_digest(values['original_pairs'])
    artifact,values=deepcopy((artifact,values))
    return _source_operation(_write_calibrated_candidate,directory,artifact,**values,_version=5)


def read_compressed_source_calibrated_candidate(path,**values):
    return _source_operation(_read_calibrated_candidate,path,**values,_version=5)
