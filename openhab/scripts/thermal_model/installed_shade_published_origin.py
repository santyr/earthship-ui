"""Actual main-publication observations, separate from original numeric captures.

Both persisted receipts are retained unchanged with their Item identities. A
historical publication's mode/report digest describes what was issued; it never
authorizes a current release. Numeric/source replay supplies the score, and the
new binding refers to the actual main publication, not a fabricated old output.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path

from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc,_sha
from .installed_shade_artifact import _digest
from .installed_shade_publication import validate_installed_publication,validate_raw_installed_publication,validate_source_installed_publication,_read_origin
from .installed_shade_calibration import _persist,_read_json
from .origin_capture import _object
from . import installed_shade_origin as base
from . import installed_shade_calibrated_origin as calibrated

SCHEMA='earthship-installed-shade-origin/v3'
PAIR_SCHEMA='earthship-installed-shade-source-scored-pair/v3'
RAW_SCHEMA='earthship-installed-shade-origin/v5'
RAW_PAIR_SCHEMA='earthship-installed-shade-source-scored-pair/v5'
SOURCE_CALIBRATED_SCHEMA='earthship-installed-shade-origin/v7'
SOURCE_BASE_SCHEMA='earthship-installed-shade-origin/v9'
SCHEMAS={3:SCHEMA,5:RAW_SCHEMA,7:SOURCE_CALIBRATED_SCHEMA,9:SOURCE_BASE_SCHEMA}
PAIR_SCHEMAS={3:PAIR_SCHEMA,5:RAW_PAIR_SCHEMA,7:'earthship-installed-shade-source-scored-pair/v7',9:'earthship-installed-shade-source-scored-pair/v9'}
NUMERIC_ITEM='Thermal_OriginalForecast_JSON'
PUBLICATION_ITEM='Thermal_Model_JSON'
FIELDS={'schema','recorded_at','numeric_capture','numeric_publication','publication','capture_sha256'}
MAX_CAPTURE_BYTES=2000000
EPOCH=datetime(1970,1,1,tzinfo=timezone.utc)


def _clock():return datetime.now(timezone.utc)


def _receipt(value,item):
    if (not isinstance(value,dict) or set(value)!={'item','time','state'} or value['item']!=item or
            type(value['time']) is not int or not isinstance(value['state'],str) or
            len(value['state'].encode())>=16384):raise ValueError('bounded actual persisted Item receipt required')
    def reject(_):raise ValueError('nonfinite persisted publication')
    try:output=json.loads(value['state'],object_pairs_hook=_object,parse_constant=reject)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('actual persisted publication JSON invalid') from None
    return output,EPOCH+timedelta(milliseconds=value['time'])


def _check_version(version):
    if type(version) is not int or version not in (3,5,7,9):
        raise ValueError('explicit actual publication capture version required')


def _ports(numeric, *, _version=3):
    _check_version(_version)
    if _version==7:
        if numeric.get('schema')!=calibrated.SOURCE_SCHEMA:raise ValueError('query-bound calibrated numeric capture required')
        return calibrated.validate_source_calibrated_capture,lambda record:calibrated._prediction(record,_version=6),calibrated.score_source_calibrated_capture
    if _version==9:
        if numeric.get('schema')!=base.SOURCE_SCHEMA:raise ValueError('query-bound base numeric capture required')
        return base.validate_source_issued_capture,base._source_prediction,base.score_source_issued_capture
    if _version==5:
        if numeric.get('schema')!=calibrated.RAW_SCHEMA:
            raise ValueError('typed raw-calibrated numeric capture required')
        return (calibrated.validate_raw_calibrated_capture,
            lambda record:calibrated._prediction(record,_version=4),calibrated.score_raw_calibrated_capture)
    if numeric.get('schema')==base.SCHEMA:return base.validate_issued_capture,base._prediction,base.score_issued_capture
    if numeric.get('schema')==calibrated.SCHEMA:return calibrated.validate_calibrated_capture,calibrated._prediction,calibrated.score_calibrated_capture
    raise ValueError('typed unchanged original numeric capture required')


def _build_publication_capture(original_path,*,numeric_publication,publication,_version=3):
    _check_version(_version)
    if _version==7:original=calibrated.read_source_calibrated_capture(original_path)
    elif _version==9:original=base.read_source_issued_capture(original_path)
    else:original=calibrated.read_raw_calibrated_capture(original_path) if _version==5 else _read_origin(original_path)[0]
    record=json.loads(_canonical(dict(schema=SCHEMAS[_version],recorded_at=_utc(_clock()).isoformat(),
        numeric_capture=original,numeric_publication=numeric_publication,publication=publication)))
    record['capture_sha256']=_digest(record)
    return _validate_publication_capture(record,_version=_version)


def _validate_publication_capture(record, *, _version=3):
    _check_version(_version)
    if (not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMAS[_version] or
            len(_canonical(record))>MAX_CAPTURE_BYTES or
            _digest({k:v for k,v in record.items() if k!='capture_sha256'})!=_sha(record['capture_sha256'])):
        raise ValueError('closed bounded actual publication capture required')
    numeric=record['numeric_capture'];validate,predict,_=_ports(numeric,_version=_version);validate(numeric)
    original,numeric_at=_receipt(record['numeric_publication'],NUMERIC_ITEM)
    output,published_at=_receipt(record['publication'],PUBLICATION_ITEM);(validate_source_installed_publication if _version in (7,9) else validate_raw_installed_publication if _version==5 else validate_installed_publication)(output)
    issue=_utc(numeric['issued_at']);recorded=_utc(record['recorded_at'])
    if (not issue<=numeric_at<=_utc(numeric['published_at'])<=published_at<=recorded or
            not published_at<_utc(output['validUntil']) or output['status']=='unavailable' or
            not _utc(output['release']['qualifiedAt'])<=published_at):
        raise ValueError('actual publication chronology/freshness unavailable')
    if (_canonical(original)!=_canonical(numeric['output']) or _canonical(output['forecast'])!=_canonical(original) or
            _utc(output['generatedAt'])!=issue or output['release']['originCaptureSha256']!=numeric['capture_sha256'] or
            output['release']['artifactSha256']!=numeric['candidate']['artifact_sha256'] or
            output['release']['runtimeSha256']!=_digest(numeric['runtime']) or
            output['release']['sensorEpochs']!=numeric['source_epochs'] or
            _utc(output['model']['createdAt'])!=_utc(numeric['candidate']['created_at']) or
            _utc(output['model']['trainedThrough'])!=_utc(numeric['candidate']['trained_through']) or
            output['model']['codeRevision']!=numeric['candidate']['code_revision']):
        raise ValueError('actual publication changed the bound numeric origin')
    if _version in (7,9) and output['release']['nativeOriginBindingSha256']!=_digest(numeric['native_origin_binding']):
        raise ValueError('actual main receipt changed the original query proof')
    # Replay the same original evidence at the main receipt's real clock. This
    # view is not a new original forecast/capture or substituted persisted state.
    current=deepcopy(numeric);current['published_at']=published_at.isoformat()
    replay,phases=predict(current)
    if _canonical(replay)!=_canonical(original) or phases!=numeric['source_epochs']:
        raise ValueError('main delivery failed original native expiry/source replay')
    return record


def _write_publication_capture(directory,record, *, _version=3):
    record=deepcopy(record);_validate_publication_capture(record,_version=_version);root=_private_directory(Path(directory))
    numeric=record['numeric_capture']
    if _version==7:writer=calibrated.write_source_calibrated_capture
    elif _version==9:writer=base.write_source_issued_capture
    else:writer=calibrated.write_raw_calibrated_capture if _version==5 else (calibrated.write_calibrated_capture if numeric['schema']==calibrated.SCHEMA else base.write_issued_capture)
    writer(root,numeric)
    return _persist(root,record,record['capture_sha256'],f'.installed-shade-origin-v{_version}.json',
        before_publish=(lambda:_validate_publication_capture(record,_version=_version)) if _version in (7,9) else None)


def _read_publication_capture(path, *, _version=3):
    path=Path(path);_private_directory(path.parent);record=_read_json(path);_validate_publication_capture(record,_version=_version)
    if path.name!=record['capture_sha256']+f'.installed-shade-origin-v{_version}.json':raise ValueError('actual publication capture address differs')
    return record


def _score_publication_capture(record,*,publication,horizon_hours,outcome,recent_cycle_grid,assessed_at,_version=3):
    _validate_publication_capture(record,_version=_version)
    if _canonical(publication)!=_canonical(record['publication']):raise ValueError('actual main receipt differs from original capture')
    output,published=_receipt(publication,PUBLICATION_ITEM);numeric=record['numeric_capture'];_,_,score=_ports(numeric,_version=_version)
    issue=_utc(numeric['issued_at']);now=_utc(assessed_at)
    if type(horizon_hours) is not int or horizon_hours not in (1,6,12,24,48):raise ValueError('actual supported publication scoring horizon required')
    if not published<issue+timedelta(hours=horizon_hours)<=now-timedelta(minutes=5) or _utc(record['recorded_at'])>now:
        raise ValueError('actual main publication/later outcome is not mature')
    receipt=record['numeric_publication']
    # Project the actual numeric receipt onto its explicit numeric API. Neither
    # its timestamp nor payload is reconstructed from the main publication.
    result=score(numeric,publication={key:receipt[key] for key in ('time','state')},horizon_hours=horizon_hours,
        outcome=outcome,recent_cycle_grid=recent_cycle_grid,assessed_at=now)
    result.update(schema=PAIR_SCHEMAS[_version],original_capture_sha256=record['capture_sha256'],
        numeric_capture_sha256=numeric['capture_sha256'],publication_sha256=_digest(publication),
        numeric_publication_sha256=_digest(receipt),publication_mode=output['status'])
    return result



def build_publication_capture(original_path,**values):
    return _build_publication_capture(original_path,**values,_version=3)


def build_raw_publication_capture(original_path,**values):
    return _build_publication_capture(original_path,**values,_version=5)


def validate_publication_capture(record):
    return _validate_publication_capture(record,_version=3)


def validate_raw_publication_capture(record):
    return _validate_publication_capture(record,_version=5)


def write_publication_capture(directory,record):
    return _write_publication_capture(directory,record,_version=3)


def write_raw_publication_capture(directory,record):
    return _write_publication_capture(directory,record,_version=5)


def read_publication_capture(path):
    return _read_publication_capture(path,_version=3)


def read_raw_publication_capture(path):
    return _read_publication_capture(path,_version=5)


def score_publication_capture(record,**values):
    return _score_publication_capture(record,**values,_version=3)


def score_raw_publication_capture(record,**values):
    return _score_publication_capture(record,**values,_version=5)


def _source_version(schema):
    if schema==SOURCE_CALIBRATED_SCHEMA:return 7
    if schema==SOURCE_BASE_SCHEMA:return 9
    raise ValueError('explicit query-bound main capture required')


def build_source_publication_capture(original_path,**values):
    name=Path(original_path).name
    if name.endswith('.installed-shade-origin-v6.json'):version=7
    elif name.endswith('.installed-shade-origin-v8.json'):version=9
    else:raise ValueError('explicit query-bound numeric file required')
    return _build_publication_capture(original_path,**values,_version=version)


def validate_source_publication_capture(record):
    if not isinstance(record,dict):raise ValueError('query-bound main capture required')
    return _validate_publication_capture(record,_version=_source_version(record.get('schema')))


def write_source_publication_capture(directory,record):
    if not isinstance(record,dict):raise ValueError('query-bound main capture required')
    return _write_publication_capture(directory,record,_version=_source_version(record.get('schema')))


def read_source_publication_capture(path):
    name=Path(path).name
    if name.endswith('.installed-shade-origin-v7.json'):version=7
    elif name.endswith('.installed-shade-origin-v9.json'):version=9
    else:raise ValueError('explicit query-bound main file required')
    return _read_publication_capture(path,_version=version)


def score_source_publication_capture(record,**values):
    if not isinstance(record,dict):raise ValueError('query-bound main capture required')
    return _score_publication_capture(record,**values,_version=_source_version(record.get('schema')))
