"""Private pre-fit input capture; exact dataset reconstruction, no fit or authority."""
from copy import deepcopy
from dataclasses import asdict,fields
from hashlib import sha256
from itertools import islice
import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from .dataset import build_samples,dataset_manifest
from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc,_sha
from .origin_capture import _object
from .pipeline import _read_authorities
from .schema import ActionEvent,ModeEvent,THERMAL_ITEMS,OPTIONAL_OBSERVATION_ITEMS
from .temperature_history import STREAMS,STEP
from .training_sources import build_training_sources,validate_training_sources,_read_private
from .runtime_bundle import _write_private,_sync_directory
from .rollback import _rename_new

SCHEMA='earthship-thermal-training-inputs/v1'
MAX_BYTES=32000000
MAX_SERIES_POINTS=120000
MAX_EVENTS=10000
NORMALIZATION='UTC timestamps; nonfinite measurements become null invalid barriers'
FLAGS={'fitting_executed','installed','release_authorized'}
FIELDS={'schema','start','end','captured_at','collection_code_revision','normalization',
        'series_by_role','events','modes','temperature_evidence','temperature_grids',
        'dataset_manifest','snapshot_sha256'}|FLAGS
ITEMS={**THERMAL_ITEMS,**OPTIONAL_OBSERVATION_ITEMS}
MAX_WINDOW_STEPS=MAX_SERIES_POINTS//len(ITEMS)


def _digest(value):return sha256(_canonical(value)).hexdigest()


def _window(start,end,captured):
    if not start<end<=captured or end-start>MAX_WINDOW_STEPS*STEP:
        raise ValueError('bounded completed training interval required')


def _bounded(values,limit):
    result=tuple(islice(iter(values),limit+1))
    if len(result)>limit:raise ValueError('training input count exceeds bound')
    return result


def _measurement(value):
    if type(value) in (int,float):return value if math.isfinite(value) else None
    if value is None or type(value) is bool or isinstance(value,str) and len(value)<=64:return value
    raise ValueError('bounded scalar training measurement required')


def _event(value,kind):
    if not isinstance(value,dict) or set(value)!={field.name for field in fields(kind)}:
        raise ValueError('exact original journal event required')
    row=dict(value)
    for name in ('received_at','effective_at'):row[name]=_utc(row[name])
    return kind(**row)


class _Series:
    retains_native_grids=True
    def __init__(self,record):self.record=record
    def __call__(self,item,start,end):
        if (_utc(start)!=_utc(self.record['start']) or _utc(end)!=_utc(self.record['end']) or item not in ITEMS.values()):
            raise ValueError('exact frozen training request required')
        role=next(role for role,name in ITEMS.items() if name==item)
        return tuple((_utc(at),value) for at,value in self.record['series_by_role'][role])
    def evidence_manifest(self):return deepcopy(self.record['temperature_evidence'])
    def temperature_grids(self):return deepcopy(self.record['temperature_grids'])


class _Journal:
    def __init__(self,record):self.record=record
    def _read(self,name,kind,start,end):
        if _utc(start)!=_utc(self.record['start']) or _utc(end)!=_utc(self.record['end']):
            raise ValueError('exact frozen journal request required')
        return tuple(_event(value,kind) for value in self.record[name])
    def effective_events(self,start,end):return self._read('events',ActionEvent,start,end)
    def effective_modes(self,start,end):return self._read('modes',ModeEvent,start,end)


def restore_training_inputs(record):
    if (not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMA or
            record['normalization']!=NORMALIZATION or any(record[key] is not False for key in FLAGS) or
            len(_canonical(record))>MAX_BYTES or
            _digest({key:value for key,value in record.items() if key!='snapshot_sha256'})!=record['snapshot_sha256']):
        raise ValueError('closed original training input snapshot required')
    _sha(record['collection_code_revision'])
    start,end,captured=map(_utc,(record['start'],record['end'],record['captured_at']))
    _window(start,end,captured)
    series=record['series_by_role'];total=0
    if not isinstance(series,dict) or set(series)!=set(ITEMS):raise ValueError('complete original series required')
    for rows in series.values():
        if not isinstance(rows,list):raise ValueError('original series list required')
        total+=len(rows)
        if total>MAX_SERIES_POINTS:raise ValueError('series count exceeds bound')
        for row in rows:
            if not isinstance(row,list) or len(row)!=2 or not start<=_utc(row[0])<end or _measurement(row[1])!=row[1]:
                raise ValueError('bounded normalized original measurement required')
    for name,kind in (('events',ActionEvent),('modes',ModeEvent)):
        if not isinstance(record[name],list) or len(record[name])>MAX_EVENTS:raise ValueError('bounded original journal events required')
        for value in record[name]:
            event=_event(value,kind)
            if event.received_at>captured or event.effective_at>captured:raise ValueError('future journal input unavailable at capture')
    value=deepcopy(record);reader=_Series(value);journal=_Journal(value)
    raw={role:reader(item,start,end) for role,item in ITEMS.items()}
    events=journal.effective_events(start,end);modes=journal.effective_modes(start,end)
    samples=build_samples(raw,events,modes,start,end)
    if dataset_manifest(samples,events,modes)!=record['dataset_manifest']:
        raise ValueError('dataset differs from captured original construction')
    artifact=SimpleNamespace(data_manifest={**record['dataset_manifest'],'temperature_evidence':record['temperature_evidence']})
    validate_training_sources(build_training_sources(samples,reader),artifact)
    # Post-cutover point values must be the exact retained native grid, including
    # missing-receipt barriers. Rehashing a rebuilt dataset cannot change them.
    cutover=_utc(record['temperature_evidence']['cutover'])
    for role in STREAMS:
        native=[[at,None if receipt is None else receipt['temperatureF']] for at,receipt in record['temperature_grids'][role]]
        actual=[[ _utc(at).isoformat(),value] for at,value in record['series_by_role'][role] if _utc(at)>=cutover]
        expected=[[_utc(at).isoformat(),value] for at,value in native]
        if actual!=expected:raise ValueError('raw temperatures differ from original native receipts')
    return SimpleNamespace(start=start,end=end,series_reader=reader,journal=journal,samples=samples)


def capture_training_inputs(*,start,end,series_reader,journal,clock,revision_reader,site_settings_loader=None):
    if (getattr(series_reader,'retains_native_grids',False) is not True or
            not all(callable(getattr(series_reader,name,None)) for name in ('temperature_grids','evidence_manifest'))):
        raise ValueError('retained original native temperature reader required')
    start,end,captured=map(_utc,(start,end,clock()))
    _window(start,end,captured)
    total=[0]
    def bounded_reader(item,left,right):
        rows=_bounded(series_reader(item,left,right),MAX_SERIES_POINTS-total[0]);total[0]+=len(rows);return rows
    bounded_journal=SimpleNamespace(effective_events=lambda *args:_bounded(journal.effective_events(*args),MAX_EVENTS),
        effective_modes=lambda *args:_bounded(journal.effective_modes(*args),MAX_EVENTS))
    series,events,modes=_read_authorities(start=start,end=end,series_reader=bounded_reader,journal=bounded_journal,site_settings_loader=site_settings_loader)
    samples=build_samples(series,events,modes,start,end)
    def encode_event(event):
        row=asdict(event)
        for name in ('received_at','effective_at'):row[name]=_utc(row[name]).isoformat()
        return row
    body=dict(schema=SCHEMA,start=start.isoformat(),end=end.isoformat(),captured_at=captured.isoformat(),
        collection_code_revision=_sha(revision_reader()),normalization=NORMALIZATION,
        series_by_role={role:[[_utc(at).isoformat(),_measurement(value)] for at,value in rows] for role,rows in series.items()},
        events=[encode_event(event) for event in events],modes=[encode_event(mode) for mode in modes],
        temperature_evidence=series_reader.evidence_manifest(),temperature_grids=series_reader.temperature_grids(),
        dataset_manifest=dataset_manifest(samples,events,modes),**{key:False for key in FLAGS})
    body['snapshot_sha256']=_digest(body);restore_training_inputs(body)
    return body


def read_training_inputs(path):
    path=Path(path)
    if path.lstat().st_size>MAX_BYTES:raise ValueError('training input snapshot exceeds bound')
    def reject(_):raise ValueError('nonfinite training input document')
    record=json.loads(_read_private(path),object_pairs_hook=_object,parse_constant=reject)
    restore_training_inputs(record)
    if path.name!=record['snapshot_sha256']+'.training-inputs-v1.json':raise ValueError('training snapshot address differs')
    return record


def write_training_inputs(directory,record):
    restore_training_inputs(record);root=_private_directory(Path(directory));raw=_canonical(record)
    target=root/(record['snapshot_sha256']+'.training-inputs-v1.json')
    if target.exists():
        if read_training_inputs(target)!=record:raise ValueError('original snapshot differs')
        return target
    temporary=root/('.training-inputs-'+uuid4().hex)
    try:
        _write_private(temporary,raw);_rename_new(temporary,target);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()
    return target
