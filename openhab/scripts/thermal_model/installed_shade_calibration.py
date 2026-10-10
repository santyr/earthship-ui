"""Source-replayed development calibration for the installed-shade candidate.

Absolute residuals use a fixed finite-sample order statistic. The data are a
chronological temperature series, not proven exchangeable observations: this
recipe grants no coverage guarantee or release authority. Later untouched and
prospective coverage/width/skill gates must still pass. This schema is separate
from the uncalibrated candidate and original issue schemas; old issues are never
retroactively given uncertainty bands.
"""
from copy import deepcopy
from fractions import Fraction
import math
from pathlib import Path
from statistics import NormalDist

from .forcing_capture import _canonical
from .graduation_policy import (_utc, _finite, _sha, CONFIDENCE,
    NOMINAL_COVERAGE, COVERAGE_PRECISION)
from .graduation_statistics import _sample
from .installed_shade_artifact import _digest, validate_candidate_bundle
from .installed_shade_fit import HORIZONS
from .installed_shade_dynamics import PARAMETER_NAMES

SCHEMA = 'earthship-installed-shade-calibration/v1'
RAW_SCHEMA = 'earthship-installed-shade-calibration/v2'
RAW_SOURCE_CONTRACT = 'earthship-installed-shade-score-sources/v2'
MAX_INDEX_BYTES = 4000000
MAX_RECORD_BYTES = 4000000
FIELDS = {'schema', 'base_candidate_sha256', 'runtime_sha256', 'sensor_epochs',
    'calibration_start', 'calibration_end', 'created_at', 'regimes', 'method',
    'summary', 'source_packets_sha256', 'source_pair_bindings',
    'coverage_guaranteed', 'release_authorized', 'calibration_sha256'}
RAW_FIELDS = FIELDS | {'source_contract'}


def _minimum():
    z = NormalDist().inv_cdf((1+CONFIDENCE)/2)
    return max(2*len(PARAMETER_NAMES), math.ceil(
        z*z*NOMINAL_COVERAGE*(1-NOMINAL_COVERAGE)/COVERAGE_PRECISION**2))


def _regimes(values):
    if (not isinstance(values, list) or not 1 <= len(values) <= 3 or
            any(value not in ('warm', 'shoulder', 'winter') for value in values) or
            len(set(values)) != len(values)):
        raise ValueError('explicit unique supported calibration regimes required')
    return sorted(values)


def _method():
    return dict(name='symmetric_absolute_residual_order_statistic/v1',
        nominal_coverage=NOMINAL_COVERAGE, minimum_independent_days=_minimum(),
        minimum_independent_windows=_minimum(), horizons=list(HORIZONS),
        sample_rule='utc_nonoverlap_then_first_issue_per_denver_day',
        rank_rule='ceil((n+1)*nominal_coverage), one-based; no interpolation or clipping',
        regime_rule='stratify_the_same_horizon_selected_daily_sample',
        requires_untouched_and_prospective_validation=True)


def _cell(raw, nonoverlap, daily):
    ready = min(len(nonoverlap), len(daily)) >= _minimum()
    # Decimal rational arithmetic keeps exact rank boundaries independent of
    # floating-point rounding. Infinite quantiles are never clipped to a max.
    coverage = Fraction(str(NOMINAL_COVERAGE))
    numerator = (len(daily)+1)*coverage.numerator
    rank = (numerator+coverage.denominator-1)//coverage.denominator
    ready = ready and 1 <= rank <= len(daily)
    radius = sorted(abs(row['model_error_f']) for row in daily)[rank-1] if ready else None
    return dict(raw_pairs=len(raw), independent_windows=len(nonoverlap),
        independent_days=len(daily), order_statistic_rank=rank if ready else None,
        radius_f=radius, selected_windows=[{key:row[key] for key in
            ('issue_at','target_at','horizon_hours','regime')} for row in daily])


def _summarize(rows, *, regimes):
    """Internal numerical seam; callers cannot use summaries as source evidence."""
    regimes = _regimes(regimes)
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ValueError('bounded calibration rows required')
    selected = []; seen = set()
    required = {'issue_at','target_at','horizon_hours','regime','model_error_f'}
    for original in rows:
        if not isinstance(original, dict) or not required <= set(original):
            raise ValueError('original residual window required')
        row = dict(original); hours = row['horizon_hours']
        issue, target = map(_utc, (row['issue_at'],row['target_at']))
        if (type(hours) is not int or hours not in HORIZONS or row['regime'] not in regimes or
                (target-issue).total_seconds() != hours*3600):
            raise ValueError('calibration horizon/regime/target differs')
        identity = (issue,target,hours)
        if identity in seen: raise ValueError('duplicate calibration window')
        seen.add(identity); row['model_error_f'] = _finite(row['model_error_f'])
        selected.append(row)
    bands = {}
    for hours in HORIZONS:
        raw = [row for row in selected if row['horizon_hours'] == hours]
        nonoverlap, daily = _sample(raw)
        bands[str(hours)] = dict(overall=_cell(raw,nonoverlap,daily), regimes={regime:
            _cell([row for row in raw if row['regime']==regime],
                [row for row in nonoverlap if row['regime']==regime],
                [row for row in daily if row['regime']==regime]) for regime in regimes})
    complete = all(cell['radius_f'] is not None for value in bands.values()
        for cell in [value['overall'], *value['regimes'].values()])
    return dict(complete=complete, bands=bands)


def _packet_digest(packets):
    if not isinstance(packets, list) or not 1 <= len(packets) <= 10000:
        raise ValueError('original calibration source packets required')
    if len(_canonical(packets)) > MAX_INDEX_BYTES:
        raise ValueError('original calibration source packet byte bound exceeded')
    addressed = []
    for original in packets:
        if not isinstance(original, dict) or not isinstance(original.get('origin_path'),str):
            raise ValueError('original source path required, not residual summaries')
        addressed.append({**original,'origin_path':Path(original['origin_path']).name})
    return _digest(addressed)


def _raw_packet_digest(packets):
    if not isinstance(packets,list) or not 1<=len(packets)<=10000 or len(_canonical(packets))>MAX_INDEX_BYTES:
        raise ValueError('bounded original raw calibration index required')
    addressed=[]
    for reference in packets:
        if (not isinstance(reference,dict) or set(reference)!={'raw_score_sources_path'} or
                not isinstance(reference['raw_score_sources_path'],str) or not 1<=len(reference['raw_score_sources_path'])<=1024):
            raise ValueError('original raw calibration source references required')
        path=Path(reference['raw_score_sources_path'])
        if not path.is_absolute():raise ValueError('absolute original raw calibration path required')
        addressed.append(dict(raw_score_sources_path=path.name))
    return _digest(addressed)


def build_calibration(**values):
    """Legacy receipt-only diagnostic profile; no raw-source authority."""
    return _build_calibration(**values,_version=1)


def build_raw_calibration(**values):
    """Learn development bands only after replaying original raw query archives."""
    return _build_calibration(**values,_version=2)


def validate_calibration(record,**values):
    return _validate_calibration(record,**values,_version=1)


def validate_raw_calibration(record,**values):
    return _validate_calibration(record,**values,_version=2)


def _build_calibration(*, bundle, inputs, expected_runtime_revision, original_pairs,
                      calibration_start, calibration_end, regimes, created_at, _version=1):
    """Replay original native training and issued pairs before learning bands.

    The calibration interval follows coefficient training AND core-candidate
    creation. Its end becomes part of the eventual aggregate learning cutoff;
    a future calibrated candidate must be frozen before release evaluation.
    """
    if type(_version) is not int or _version not in (1,2):raise ValueError('explicit calibration source version required')
    regimes = _regimes(regimes)
    start,end,created = map(_utc,(calibration_start,calibration_end,created_at))
    expected_runtime_revision = _sha(expected_runtime_revision)
    packet_sha = (_raw_packet_digest if _version==2 else _packet_digest)(original_pairs)
    validate_candidate_bundle(bundle,inputs,expected_runtime_revision=expected_runtime_revision,assessed_at=created)
    artifact = bundle['artifact']
    if not _utc(artifact['trained_through']) <= _utc(artifact['created_at']) <= start < end <= created:
        raise ValueError('calibration must follow base fitting/freeze and precede final freeze')
    # Imported at the use site to keep future explicit versioned qualification
    # adapters free to consume this module without an import-time cycle.
    from .installed_shade_qualification import _score_packets
    scored = _score_packets(original_pairs,assessed_at=created,candidate=dict(
        artifact_sha256=artifact['artifact_sha256'],runtime_sha256=expected_runtime_revision,
        sensor_epochs=artifact['sensor_epochs']),version=4 if _version==2 else 1)
    if _version==2 and scored.get('raw_native_score_sources') is not True:
        raise ValueError('original raw native calibration sources required')
    for row in scored['rows']:
        if not start <= _utc(row['issue_at']) < _utc(row['target_at']) <= end:
            raise ValueError('original window outside separate development calibration interval')
    body = dict(schema=RAW_SCHEMA if _version==2 else SCHEMA,base_candidate_sha256=artifact['artifact_sha256'],
        runtime_sha256=expected_runtime_revision,sensor_epochs=deepcopy(artifact['sensor_epochs']),
        calibration_start=start.isoformat(),calibration_end=end.isoformat(),created_at=created.isoformat(),
        regimes=regimes,method=_method(),summary=_summarize(scored['rows'],regimes=regimes),
        source_packets_sha256=packet_sha,source_pair_bindings=scored['bindings'],
        coverage_guaranteed=False,release_authorized=False)
    if _version==2:body['source_contract']=RAW_SOURCE_CONTRACT
    if len(_canonical(body)) > MAX_RECORD_BYTES:
        raise ValueError('bounded calibration record required')
    body['calibration_sha256'] = _digest(body)
    return body


def _validate_calibration(record, *, bundle, inputs, expected_runtime_revision,
                         original_pairs, assessed_at, _version=1):
    if type(_version) is not int or _version not in (1,2):raise ValueError('explicit calibration source version required')
    fields=RAW_FIELDS if _version==2 else FIELDS
    schema=RAW_SCHEMA if _version==2 else SCHEMA
    if (not isinstance(record,dict) or set(record)!=fields or record['schema']!=schema or
            (_version==2 and record['source_contract']!=RAW_SOURCE_CONTRACT) or
            len(_canonical(record)) > MAX_RECORD_BYTES or
            record['coverage_guaranteed'] is not False or record['release_authorized'] is not False or
            _digest({k:v for k,v in record.items() if k!='calibration_sha256'}) != _sha(record['calibration_sha256'])):
        raise ValueError('closed bounded development calibration required')
    if _utc(record['created_at']) > _utc(assessed_at):
        raise ValueError('calibration unavailable at assessment')
    expected = _build_calibration(bundle=bundle,inputs=inputs,
        expected_runtime_revision=expected_runtime_revision,original_pairs=original_pairs,
        calibration_start=record['calibration_start'],calibration_end=record['calibration_end'],
        regimes=record['regimes'],created_at=record['created_at'],_version=_version)
    if _canonical(expected) != _canonical(record):
        raise ValueError('calibration differs from original source replay')
    return deepcopy(record)


def _persist(root, value, digest, suffix, *, before_publish=None):
    from .replay_budget import check_shared_budget
    check_shared_budget()
    from .runtime_bundle import _owned_bytes, _write_private, _sync_directory
    from .rollback import _rename_new
    from uuid import uuid4
    raw = _canonical(value)
    if len(raw) > MAX_RECORD_BYTES: raise ValueError('bounded private calibration member required')
    target = root/(_sha(digest)+suffix)
    if target.exists():
        if _owned_bytes(target,MAX_RECORD_BYTES) != raw:
            raise ValueError('immutable original calibration member differs')
        return target
    temporary = root/('.calibration-'+uuid4().hex)
    try:
        _write_private(temporary,raw)
        check_shared_budget()
        # Source guards may consume time: chronology is the final check.
        if before_publish is not None:before_publish()
        _rename_new(temporary,target); _sync_directory(root)
    finally:
        if temporary.exists(): temporary.unlink()
    return target


def _read_json(path):
    import json
    from .runtime_bundle import _owned_bytes
    from .origin_capture import _object
    def reject(_): raise ValueError('nonfinite calibration source JSON')
    try:
        return json.loads(_owned_bytes(path,MAX_RECORD_BYTES),object_pairs_hook=_object,parse_constant=reject)
    except (UnicodeDecodeError,json.JSONDecodeError):
        raise ValueError('original calibration source JSON unreadable') from None


def write_calibration(directory, record, *, bundle, inputs, expected_runtime_revision,
                      original_pairs, assessed_at):
    from .forcing_capture import _private_directory
    from .installed_shade_artifact import write_candidate_bundle
    from .installed_shade_origin import read_issued_capture, write_issued_capture
    record,bundle,inputs,original_pairs = deepcopy((record,bundle,inputs,original_pairs))
    validate_calibration(record,bundle=bundle,inputs=inputs,
        expected_runtime_revision=expected_runtime_revision,original_pairs=original_pairs,assessed_at=assessed_at)
    root = _private_directory(Path(directory))
    write_candidate_bundle(root,bundle,inputs,
        expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at)
    packets = []; retained = set()
    for packet in original_pairs:
        original = Path(packet['origin_path'])
        if original not in retained:
            copied = write_issued_capture(root,read_issued_capture(original))
            if copied.name != original.name: raise ValueError('original capture address changed')
            retained.add(original)
        packets.append({**packet,'origin_path':original.name})
    _persist(root,packets,record['source_packets_sha256'],'.installed-shade-calibration-sources-v1.json')
    # Addressed source members are retained first; the calibration is published
    # last. This creates no active candidate or production publication.
    return _persist(root,record,record['calibration_sha256'],'.installed-shade-calibration-v1.json')


def read_calibration(path, *, expected_runtime_revision, assessed_at):
    from .forcing_capture import _private_directory
    from .installed_shade_artifact import _read
    from .training_inputs import read_training_inputs_v2
    path = Path(path); root = _private_directory(path.parent)
    record = _read_json(path)
    if not isinstance(record,dict) or set(record)!=FIELDS:
        raise ValueError('closed original calibration file required')
    digest = _sha(record['calibration_sha256'])
    if path.name != digest+'.installed-shade-calibration-v1.json':
        raise ValueError('original calibration address differs')
    packet_sha = _sha(record['source_packets_sha256'])
    packets = _read_json(root/(packet_sha+'.installed-shade-calibration-sources-v1.json'))
    if _packet_digest(packets) != packet_sha:
        raise ValueError('original source packet index differs')
    resolved = []
    for packet in packets:
        name = packet['origin_path']
        if Path(name).name != name: raise ValueError('original capture must be a private addressed member')
        resolved.append({**packet,'origin_path':str(root/name)})
    base_sha = _sha(record['base_candidate_sha256'])
    artifact = _read(root/(base_sha+'.installed-shade-candidate-v1.json'))
    if not isinstance(artifact,dict) or artifact.get('artifact_sha256')!=base_sha:
        raise ValueError('original base candidate address differs')
    fit_sha = _sha(artifact.get('fit_evidence_sha256'))
    input_sha = _sha(artifact.get('source_snapshot_sha256'))
    bundle = dict(artifact=artifact,fit_evidence=_read(root/(fit_sha+'.installed-shade-fit-v1.json')))
    inputs = read_training_inputs_v2(root/(input_sha+'.training-inputs-v2.json'))
    return validate_calibration(record,bundle=bundle,inputs=inputs,
        expected_runtime_revision=expected_runtime_revision,original_pairs=resolved,assessed_at=assessed_at)


def write_raw_calibration(directory,record,*,bundle,inputs,expected_runtime_revision,
                          original_pairs,assessed_at):
    """Retain the base evidence and raw archive locators; calibration is last.

    Query/capture archives remain the original addressed sources. Their absolute
    locators confer no authority: typed readback replays their original bytes.
    The index digest addresses source filenames independently of archive roots.
    """
    from .forcing_capture import _private_directory
    from .installed_shade_artifact import write_candidate_bundle
    record,bundle,inputs,original_pairs=deepcopy((record,bundle,inputs,original_pairs))
    validate_raw_calibration(record,bundle=bundle,inputs=inputs,
        expected_runtime_revision=expected_runtime_revision,original_pairs=original_pairs,assessed_at=assessed_at)
    root=_private_directory(Path(directory))
    write_candidate_bundle(root,bundle,inputs,expected_runtime_revision=expected_runtime_revision,assessed_at=assessed_at)
    _persist(root,original_pairs,record['source_packets_sha256'],'.installed-shade-calibration-sources-v2.json')
    return _persist(root,record,record['calibration_sha256'],'.installed-shade-calibration-v2.json')


def read_raw_calibration(path,*,expected_runtime_revision,assessed_at):
    from .forcing_capture import _private_directory
    from .installed_shade_artifact import _read
    from .training_inputs import read_training_inputs_v2
    path=Path(path);root=_private_directory(path.parent);record=_read_json(path)
    if (not isinstance(record,dict) or set(record)!=RAW_FIELDS or record['schema']!=RAW_SCHEMA or
            record['source_contract']!=RAW_SOURCE_CONTRACT):raise ValueError('closed raw calibration file required')
    digest=_sha(record['calibration_sha256'])
    if (path.name!=digest+'.installed-shade-calibration-v2.json' or
            _digest({key:value for key,value in record.items() if key!='calibration_sha256'})!=digest or
            _utc(record['created_at'])>_utc(assessed_at)):
        raise ValueError('original raw calibration address or chronology differs')
    packet_sha=_sha(record['source_packets_sha256'])
    packets=_read_json(root/(packet_sha+'.installed-shade-calibration-sources-v2.json'))
    if _raw_packet_digest(packets)!=packet_sha:raise ValueError('original raw calibration index differs')
    base_sha=_sha(record['base_candidate_sha256']);artifact=_read(root/(base_sha+'.installed-shade-candidate-v1.json'))
    if not isinstance(artifact,dict) or artifact.get('artifact_sha256')!=base_sha:raise ValueError('original base candidate address differs')
    fit_sha=_sha(artifact.get('fit_evidence_sha256'));input_sha=_sha(artifact.get('source_snapshot_sha256'))
    bundle=dict(artifact=artifact,fit_evidence=_read(root/(fit_sha+'.installed-shade-fit-v1.json')))
    inputs=read_training_inputs_v2(root/(input_sha+'.training-inputs-v2.json'))
    return validate_raw_calibration(record,bundle=bundle,inputs=inputs,
        expected_runtime_revision=expected_runtime_revision,original_pairs=packets,assessed_at=assessed_at)
