"""Small daily-origin diagnostic batches; scheduling hints are not evidence.

Sample the earliest archive completion per Denver day. Original publication
clocks and sources remain authoritative in the collector and score replay.
"""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from time import monotonic
from zoneinfo import ZoneInfo

from forecast_input_capture import _canonical,_directory,_instant
from forecast_temperature_origin import _read,_write,read_origin
from forecast_temperature_score import _frame
from forecast_temperature_collection import collect_target
from weather_temperature_config import _object,_nonfinite

MAX_ENTRIES=100000
MAX_DAYS=366
MAX_TARGETS=4
PATTERN=re.compile(r'([0-9a-f]{64})\.temperature-origin-v1\.json')


def daily_origins(directory,*,deadline=None,clock=monotonic):
    root=_directory(Path(directory));days={};zone=ZoneInfo('America/Denver')
    with os.scandir(root) as entries:
        for count,entry in enumerate(entries,1):
            if count>MAX_ENTRIES:raise ValueError('bounded origin archive required')
            if deadline is not None and clock()>=deadline:raise TimeoutError('batch budget elapsed')
            match=PATTERN.fullmatch(entry.name)
            if match is None:continue
            info=entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
                raise ValueError('private original archive member required')
            day=datetime.fromtimestamp(info.st_mtime,tz=timezone.utc).astimezone(zone).date()
            candidate=(info.st_mtime_ns,match[1])
            if day not in days or candidate<days[day]:days[day]=candidate
            if len(days)>MAX_DAYS:raise ValueError('bounded daily origin inventory required')
    return [days[day][1] for day in sorted(days)]


def _hint(out,key):
    path=out/(key+'.batch-attempt-v1.json')
    if not path.exists():return False
    value=json.loads(_read(path,4096),object_pairs_hook=_object,parse_constant=_nonfinite)
    if (not isinstance(value,dict) or set(value)!={'schema','source_packet','release_authority'}
            or value['schema']!='earthship-temperature-batch-attempt-hint/v1' or value['release_authority'] is not False
            or not isinstance(value['source_packet'],str) or not re.fullmatch(r'[0-9a-f]{64}\.temperature-score-sources-v1\.json',value['source_packet'])):
        raise ValueError('closed scheduling hint required')
    # Hints suppress repeated scheduled attempts only. No support, confidence or
    # score is derived from them; reports must replay original source packets.
    return True


def _retry_time(out,digest):
    path=out/(digest+'.batch-retry-hint-v1.json')
    if not path.exists():return None
    value=json.loads(_read(path,4096),object_pairs_hook=_object,parse_constant=_nonfinite)
    if (not isinstance(value,dict) or set(value)!={'schema','next_attempt_at','release_authority'}
            or value['schema']!='earthship-temperature-batch-retry-hint/v1' or value['release_authority'] is not False):
        raise ValueError('closed retry hint required')
    return _instant(value['next_attempt_at'])


def _retry_later(out,digest,assessed):
    path=out/(digest+'.batch-retry-hint-v1.json')
    if path.exists():_read(path,4096)
    raw=_canonical({'schema':'earthship-temperature-batch-retry-hint/v1',
        'next_attempt_at':(assessed+timedelta(minutes=30)).isoformat(),'release_authority':False})
    fd,temporary=tempfile.mkstemp(prefix='.batch-retry-',dir=out)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def collect_batch(*,origin_directory,output_directory,assessed_at,backend,deadline=None,clock=monotonic):
    root=_directory(Path(origin_directory));out=_directory(Path(output_directory));assessed=_instant(assessed_at)
    deadline=clock()+60 if deadline is None else deadline
    result={'status':'batch_complete','attempted':0,'qualified':0,'withheld':0,'failed':0,'source_errors':0,
        'sampling':'earliest_archive_completion_per_Denver_day','release_authority':False}
    try:
        if clock()>=deadline:raise TimeoutError('batch budget elapsed')
        origins=list(reversed(daily_origins(root,deadline=deadline,clock=clock)))
        retries={digest:_retry_time(out,digest) for digest in origins}
        origins.sort(key=lambda digest:(retries[digest] is not None,
            retries[digest] or datetime.min.replace(tzinfo=timezone.utc)))
        for digest in origins:
            if result['attempted']>=MAX_TARGETS:return result
            if clock()>=deadline:raise TimeoutError('batch budget elapsed')
            if retries[digest] is not None and assessed<retries[digest]:continue
            try:
                origin,weather=read_origin(root,root/(digest+'.temperature-origin-v1.json'))
                _,_,frame=_frame(origin,weather);issued=_instant(origin['publication_completed_at'])
            except (ValueError,OSError,KeyError,TypeError):
                result['source_errors']+=1
                _retry_later(out,digest,assessed);continue
            for target in sorted(frame):
                if clock()>=deadline:raise TimeoutError('batch budget elapsed')
                if target<=issued or target+timedelta(minutes=5)>assessed:continue
                key=sha256(_canonical([digest,target.isoformat()])).hexdigest()
                if (out/(key+'.qualified-target-v1.json')).exists() or _hint(out,key):continue
                result['attempted']+=1
                try:
                    collected=collect_target(origin_directory=root,origin_sha256=digest,target=target.isoformat(),
                        assessed_at=assessed.isoformat(),output_directory=out,backend=backend)
                    status=collected['status']
                    if status in ('qualified','withheld'):
                        result[status]+=1
                        _write(out,key+'.batch-attempt-v1.json',_canonical({'schema':'earthship-temperature-batch-attempt-hint/v1',
                            'source_packet':collected['source_packet'],'release_authority':False}))
                    elif status=='busy':result['status']='busy';return result
                except Exception:
                    result['failed']+=1
                    _retry_later(out,digest,assessed)
                    break
                if result['attempted']>=MAX_TARGETS:return result
    except TimeoutError:result['status']='budget_exhausted'
    return result
