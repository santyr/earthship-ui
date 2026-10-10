"""Collect one original correction outcome; no fits or publication authority.

Backend supplies only original persisted detail receipts and raw native rows.
Transport configuration and scheduling remain separate from this source core.
"""
from datetime import timedelta
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import stat

from forecast_input_capture import _canonical,_directory,_instant
from forecast_temperature_origin import read_origin,_policy,_read,_write
from forecast_temperature_score import SOURCE_SCHEMA,_frame,score_sources,write_sources,read_sources
from weather_temperature_config import _object,_nonfinite


def collect_target(*,origin_directory,origin_sha256,target,assessed_at,output_directory,backend):
    if not isinstance(origin_sha256,str) or not re.fullmatch('[0-9a-f]{64}',origin_sha256):
        raise ValueError('original origin digest required')
    root=_directory(Path(origin_directory));out=_directory(Path(output_directory))
    target,assessed=map(_instant,(target,assessed_at))
    origin,weather=read_origin(root,root/(origin_sha256+'.temperature-origin-v1.json'))
    _,_,frame=_frame(origin,weather)
    if target not in frame or target<=_instant(origin['publication_started_at']):
        raise ValueError('original future target required')
    base={'release_authority':False}
    if assessed<target+timedelta(minutes=5):return dict(base,status='pending')
    key=sha256(_canonical([origin_sha256,target.isoformat()])).hexdigest()
    index=out/(key+'.qualified-target-v1.json')
    fd=os.open(out/'collection.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC,0o600)
    try:
        metadata=os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=os.geteuid() or metadata.st_mode&0o077 or metadata.st_nlink!=1:
            raise ValueError('private single-link collector lock required')
        try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return dict(base,status='busy')
        if index.exists():
            saved=json.loads(_read(index,4096),object_pairs_hook=_object,parse_constant=_nonfinite)
            if not isinstance(saved,dict) or set(saved)!={'schema','source_packet'} or saved['schema']!='earthship-temperature-qualified-target/v1' or not isinstance(saved['source_packet'],str):
                raise ValueError('original qualified target index required')
            packet=read_sources(out,out/saved['source_packet'])
            if packet['origin_sha256']!=origin_sha256 or _instant(packet['target'])!=target or score_sources(root,packet)['status']!='qualified':
                raise ValueError('qualified target index differs from original sources')
            return dict(base,status='already_qualified',source_packet=saved['source_packet'])
        policies,_=_policy(origin['native_policy'])
        start=target-timedelta(seconds=policies['outdoor'].validity_seconds)
        receipt=backend.publication(origin)
        rows=backend.native(start=start,end=target,assessed_at=assessed)
        backend.verify_unchanged()
        packet={'schema':SOURCE_SCHEMA,'origin_sha256':origin_sha256,'publication_receipt':receipt,
            'target':target.isoformat(),'assessed_at':assessed.isoformat(),'history_start':start.isoformat(),'native_rows':rows}
        score=score_sources(root,packet)
        path=write_sources(out,packet)
        if score['status']=='qualified':
            _write(out,index.name,_canonical({'schema':'earthship-temperature-qualified-target/v1','source_packet':path.name}))
        return dict(base,status=score['status'],source_packet=path.name)
    finally:os.close(fd)
