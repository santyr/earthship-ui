"""Use older persistence only before receipt coverage, with inferred units.

Recent invalid/missing receipts are never repaired from numeric Item state.
Older numeric targets retain explicitly unknown sensor health and hardware ID.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import json
from weather_source_files import _read
from .contracts import identity,instant
from .numeric_history import capture_numeric_day,original_series,temperature_targets,infer_temperature_unit
from thermal_model.schema import THERMAL_ITEMS

STREAMS={'air':'indoor','mass':'north_wall','outdoor':'outdoor'}


def read_numeric_measurements(root,*,receipt_measurements,guard):
    root=Path(root);index_raw=_read(root/'numeric-index.json',262144);index=json.loads(index_raw)
    if index['index_sha256']!=identity({k:v for k,v in index.items() if k!='index_sha256'}):raise ValueError('numeric index differs')
    if not 1<=len(index['days'])<=366 or not receipt_measurements:raise ValueError('bounded numeric days and receipt overlap required')
    boundary=min(receipt_measurements)
    def source(row):
        guard();path=root/(row['date']+'.numeric-source.json.gz');raw=_read(path,8*1024**2)
        if sha256(raw).hexdigest()!=row['file_sha256']:raise ValueError('numeric original differs from index')
        value=capture_numeric_day(root,row['date'],site=index['site'],token_reader=None)
        if value['source_sha256']!=row['source_sha256']:raise ValueError('numeric source identity differs')
        return value
    evidence={role:[] for role in STREAMS};units={};manifest=[]
    # Infer against actual matching streams, never from plausible seasonal ranges.
    for row in reversed(index['days']):
        if row['date']<boundary[:10]:continue
        value=source(row)
        for role,stream in STREAMS.items():
            labels={at:streams[stream] for at,streams in receipt_measurements.items() if row['date']==at[:10] and streams.get(stream) is not None}
            test=infer_temperature_unit(original_series(value,role),labels)
            if test['unit'] is not None:evidence[role].append(dict(date=row['date'],source_sha256=value['source_sha256'],**test))
        if all(len(evidence[role])>=3 for role in STREAMS):break
    for role,tests in evidence.items():
        candidates={t['unit'] for t in tests}
        if len(candidates)!=1:raise ValueError('consistent receipt-overlap numeric units required: '+role)
        units[role]=next(iter(candidates))
    result={}
    for row in index['days']:
        if row['date']>=boundary[:10]:continue
        value=source(row);start=instant(value['start']);targets=[start+timedelta(minutes=5*i) for i in range(288)]
        for role,stream in STREAMS.items():
            labels=temperature_targets(original_series(value,role),targets,item=THERMAL_ITEMS[role],source_sha256=value['source_sha256'],unit=units[role])
            for at,label in zip(targets,labels):result.setdefault(at.isoformat(),{})[stream]=label
        manifest.append(dict(date=row['date'],source_sha256=value['source_sha256'],file_sha256=row['file_sha256']))
    from .history_index import verify_retained_selection
    verify_retained_selection(index_raw,_read(root/'numeric-index.json',262144))
    return result,dict(source_quality='legacy_numeric_without_sensor_receipts',units=units,unit_overlap=evidence,
        unit_assumed_constant_before_receipt_coverage=True,receipt_coverage_start=boundary,days=manifest)
