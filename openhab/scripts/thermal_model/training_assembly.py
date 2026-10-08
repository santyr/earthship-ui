"""Bounded original measurement assembly with freshly read full journal context."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc,_sha
from .runtime_bundle import _owned_bytes,_write_private,_sync_directory
from .rollback import _rename_new
from .temperature_history import STREAMS
from .training_inputs import (FIELDS,FLAGS,ITEMS,MAX_BYTES,MAX_SERIES_POINTS,_bounded,_digest,
                              _window,_Series,capture_training_inputs,restore_training_inputs)

SCHEMA='earthship-thermal-training-assembly/v1'
BINDING_FIELDS={'schema','input_snapshot_sha256s','measurement_collection_code_revision',
    'assembly_code_revision','assembled_snapshot_sha256','journal_captured_at','start','end','binding_sha256'}|FLAGS
IDENTITY={'stream','model','sensor_id','policy'}


def _prepare(records,captured):
    records=_bounded(records,8)
    if len(records)<2 or any(not isinstance(record,dict) or set(record)!=FIELDS for record in records):
        raise ValueError('two to eight closed original input snapshots required')
    if sum(len(_canonical(record)) for record in records)>MAX_BYTES:raise ValueError('aggregate source bytes exceed bound')
    records=sorted(records,key=lambda record:_utc(record['start']))
    start,end=_utc(records[0]['start']),_utc(records[-1]['end']);_window(start,end,captured)
    if any(_utc(left['end'])!=_utc(right['start']) for left,right in zip(records,records[1:])):
        raise ValueError('adjacent nonoverlapping source intervals required')
    if any(_utc(record['captured_at'])>captured for record in records):raise ValueError('future source capture unavailable')
    revision=records[0]['collection_code_revision'];evidence=records[0]['temperature_evidence']
    if any(record['collection_code_revision']!=revision or
           any(record['temperature_evidence'][key]!=evidence[key] for key in ('version','cutover','semantics')) for record in records):
        raise ValueError('uniform measurement collection revision and cutover required')
    if sum(len(rows) for record in records for rows in record['series_by_role'].values())>MAX_SERIES_POINTS:
        raise ValueError('aggregate source points exceed bound')
    for record in records:restore_training_inputs(record)
    # Freeze validated originals before invoking the supplied journal callbacks.
    records=deepcopy(records)
    series={role:[row for record in records for row in record['series_by_role'][role]] for role in ITEMS}
    grids={role:[row for record in records for row in record['temperature_grids'][role]] for role in STREAMS}
    merged=deepcopy(records[0]['temperature_evidence'])
    for role in STREAMS:
        original=merged['roles'][role]
        if any({key:record['temperature_evidence']['roles'][role][key] for key in IDENTITY}!=
               {key:original[key] for key in IDENTITY} for record in records):raise ValueError('uniform native source identity required')
        for key in ('legacy_points','targets','qualified','missing'):
            original[key]=sum(record['temperature_evidence']['roles'][role][key] for record in records)
        digest=sha256()
        for row in grids[role]:
            digest.update((json.dumps(row,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode())
        original['grid_sha256']=digest.hexdigest()
    reader=_Series(dict(start=start.isoformat(),end=end.isoformat(),series_by_role=series,
                        temperature_grids=grids,temperature_evidence=merged))
    return records,start,end,reader


def assemble_training_inputs(records,*,journal,clock,revision_reader):
    captured=_utc(clock());revision=_sha(revision_reader())
    originals,start,end,reader=_prepare(records,captured)
    # Per-chunk events/modes are intentionally not used: corrections and carry
    # must come from one fresh full-interval journal view.
    record=capture_training_inputs(start=start,end=end,series_reader=reader,journal=journal,
                                  clock=lambda:captured,revision_reader=lambda:revision)
    if _sha(revision_reader())!=revision:raise ValueError('assembly code changed during collection')
    binding=dict(schema=SCHEMA,input_snapshot_sha256s=[value['snapshot_sha256'] for value in originals],
        measurement_collection_code_revision=originals[0]['collection_code_revision'],assembly_code_revision=revision,
        assembled_snapshot_sha256=record['snapshot_sha256'],journal_captured_at=record['captured_at'],
        start=record['start'],end=record['end'],**{key:False for key in FLAGS})
    binding['binding_sha256']=_digest(binding)
    verify_training_assembly(record,binding,originals)
    return record,binding


def verify_training_assembly(record,binding,records):
    if (not isinstance(binding,dict) or set(binding)!=BINDING_FIELDS or binding['schema']!=SCHEMA or
            any(binding[key] is not False for key in FLAGS) or
            _digest({key:value for key,value in binding.items() if key!='binding_sha256'})!=binding['binding_sha256']):
        raise ValueError('closed original assembly binding required')
    captured=_utc(record['captured_at']);originals,start,end,reader=_prepare(records,captured)
    restore_training_inputs(record)
    expected=dict(input_snapshot_sha256s=[value['snapshot_sha256'] for value in originals],
        measurement_collection_code_revision=originals[0]['collection_code_revision'],
        assembly_code_revision=record['collection_code_revision'],assembled_snapshot_sha256=record['snapshot_sha256'],
        journal_captured_at=record['captured_at'],start=start.isoformat(),end=end.isoformat())
    if any(binding[key]!=value for key,value in expected.items()):raise ValueError('assembly binding differs from original source snapshots')
    if record['start']!=start.isoformat() or record['end']!=end.isoformat():raise ValueError('assembled interval differs')
    for role,item in ITEMS.items():
        expected_rows=[[_utc(at).isoformat(),value] for at,value in reader(item,start,end)]
        if record['series_by_role'][role]!=expected_rows:raise ValueError('assembled measurements differ from original sources')
    if record['temperature_grids']!=reader.temperature_grids() or record['temperature_evidence']!=reader.evidence_manifest():
        raise ValueError('assembled native grids differ from original sources')
    return binding


def write_training_assembly(directory,record,binding,records):
    verify_training_assembly(record,binding,records)
    root=_private_directory(Path(directory));raw=_canonical(binding)
    target=root/(binding['binding_sha256']+'.training-assembly-v1.json')
    if target.exists():
        if _owned_bytes(target,16000)!=raw:raise ValueError('existing assembly binding differs')
        return target
    temporary=root/('.training-assembly-'+uuid4().hex)
    try:
        _write_private(temporary,raw);_rename_new(temporary,target);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()
    return target
