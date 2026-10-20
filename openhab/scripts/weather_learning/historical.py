"""Explicit retrospective acquisition; historical originals never become live issues."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import shutil
from hashlib import sha256
from .archive import Archive
from .config import Site
from .contracts import canonical,identity,instant,validate_snapshot
from .weathernext_ee import parse_collection_response
from .worker import collector_lock,DEFAULT_BANDS


def verify_history(snapshot):
    value=dict(snapshot);value.pop('snapshot_sha256',None);validate_snapshot(value)
    site=Site(**value['site']);rebuilt=[]
    for original in value['source_originals']:
        raw=original['payload']
        _,points=parse_collection_response(raw,collection=original['collection'],bands=raw['region'][0][4:],
            site=site,initialized_at=instant(value['initialized_at']),horizon=len(raw['metadata']))
        rebuilt.extend(points)
    order=lambda row:(row['variable'],row['statistic'],row['valid_at'])
    if canonical(sorted(rebuilt,key=order))!=canonical(sorted(value['points'],key=order)):
        raise ValueError('historical normalized points differ from native originals')
    return value


def _historical_only(archive):
    with archive._connect() as connection:
        if connection.execute('SELECT 1 FROM snapshots WHERE historical!=1 LIMIT 1').fetchone():
            raise ValueError('historical acquisition cannot use an operational archive')


def _record_coverage(archive,snapshot,ref,horizon,required):
    bands=identity(sorted(required))
    with archive._connect() as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS historical_coverage (initialized TEXT NOT NULL,horizon INTEGER NOT NULL,bands TEXT NOT NULL,digest TEXT NOT NULL,PRIMARY KEY(initialized,horizon,bands))')
        connection.execute('INSERT OR IGNORE INTO historical_coverage VALUES(?,?,?,?)',(snapshot['initialized_at'],horizon,bands,ref))


def indexed_history(archive,*,horizon,required=None):
    """Fresh byte hashes, without repeating normalized numerical derivation."""
    from .contracts import digest
    from weather_source_files import _read
    required=required or {tuple(b.rsplit('_',1)) for values in DEFAULT_BANDS.values() for b in values}
    with archive._connect() as connection:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='historical_coverage'").fetchone():return {}
        refs=connection.execute('SELECT initialized,digest FROM historical_coverage WHERE horizon>=? AND bands=? ORDER BY initialized,horizon',(horizon,identity(sorted(required)))).fetchall()
    result={}
    if len(refs)>10000:raise ValueError('bounded historical coverage index required')
    for initialized,ref in refs:
        digest(ref);instant(initialized)
        raw=_read(archive.objects/(ref+'.json'),8*1024**2)
        if sha256(raw).hexdigest()!=ref:raise ValueError('historical original bytes changed')
        result.setdefault(initialized,ref)
    return result


def cached_history(archive,initialized,horizon,*,required=None):
    required=required or {tuple(b.rsplit('_',1)) for values in DEFAULT_BANDS.values() for b in values}
    with archive._connect() as connection:
        refs=connection.execute('SELECT digest FROM snapshots WHERE initialized=? AND historical=1 ORDER BY completed,digest LIMIT 256',(initialized.isoformat(),)).fetchall()
    for (ref,) in refs:
        snapshot=archive.read(ref);index={(r['variable'],r['statistic'],instant(r['valid_at'])):r['value'] for r in snapshot['points']}
        if instant(snapshot['initialized_at'])!=initialized:raise ValueError('historical index run differs')
        if all(index.get((v,s,initialized+timedelta(hours=h))) is not None for v,s in required for h in range(1,horizon+1)):
            verify_history(snapshot);_record_coverage(archive,snapshot,ref,horizon,required);return snapshot,ref
    return None


def collect_history(reader,archive,*,initializations,horizon=360,now=None,bands_by_grid=None):
    now=now or datetime.now(timezone.utc)
    if (not isinstance(initializations,list) or not 1<=len(initializations)<=4 or
        type(horizon) is not int or not 1<=horizon<=360):raise ValueError('one to four bounded historical runs required')
    if any(not isinstance(at,datetime) or at.utcoffset() is None or at.utcoffset()!=timedelta(0) or
        at.hour not in (0,6,12,18) or at.minute or at.second or at.microsecond or at>now-timedelta(hours=24) for at in initializations):
        raise ValueError('elapsed UTC full-cycle initializations required')
    if initializations!=sorted(set(initializations)):raise ValueError('unique ordered historical runs required')
    bands=bands_by_grid or DEFAULT_BANDS
    required={tuple(b.rsplit('_',1)) for values in bands.values() for b in values}
    with collector_lock(archive.root/'collector.lock'):
        _historical_only(archive);result=[];downloads=0;ready=False
        for at in initializations:
            cached=cached_history(archive,at,horizon,required=required)
            if cached is not None:
                snapshot,name=cached
            else:
                if shutil.disk_usage(archive.root).free<32*1024**2:raise ValueError('historical archive disk headroom unavailable')
                if not ready:reader.initialize();ready=True
                raw=reader.fetch_points(run=dict(start_time=at.strftime('%Y-%m-%dT%H:%M:%SZ')),bands_by_grid=bands,horizon=horizon)
                snapshot=verify_history(raw)
                if instant(snapshot['initialized_at'])!=at:raise ValueError('historical fetch returned another run')
                index={(r['variable'],r['statistic'],instant(r['valid_at'])):r['value'] for r in snapshot['points']}
                if not all(index.get((v,s,at+timedelta(hours=h))) is not None for v,s in required for h in range(1,horizon+1)):
                    raise ValueError('complete historical requested coverage required')
                snapshot['historical']=True;name=archive.store_snapshot(snapshot);downloads+=1
                archive.read(name);_record_coverage(archive,snapshot,name,horizon,required)
            result.append(dict(initialized_at=at.isoformat(),sha256=name))
        return dict(schema='earthship-weathernext-historical-batch/v1',status='historical_batch_complete',downloaded=downloads,
            snapshots=result,production_writes=False,automatic_actuation=False)
