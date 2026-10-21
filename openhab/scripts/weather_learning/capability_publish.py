"""Bounded raw-statistics sidecar derived from already retained originals.

This does not change legacy payloads, fetch data, fit a model or grant control
authority. Retention is explicit; constructing or reading a product is pure.
"""
from datetime import datetime,timedelta,timezone
import re
from pathlib import Path
from zoneinfo import ZoneInfo
from .capabilities import SCHEMA,QUANTILES,profile,validate_quantiles
from .config import COLLECTIONS,Site
from .contracts import canonical,digest,finite,identity,instant
from .evidence import utc
from .features import prospective_snapshot
from household_job_budget import AdmissionDeferred

MAX_BYTES=256*1024
TEMPERATURE='station_head_temperature_2m'
LABEL='WeatherNext p10–p90; local coverage not yet verified'
METHOD='raw-native-statistics/v1'
HOUR_FIELDS={'valid_at','source_sha256','mean_c',*(s+'_c' for s in QUANTILES),'range_status'}
SOURCE_FIELDS={'snapshot_sha256','profile_sha256','run_id','initialized_at','first_seen_at','available_at','grid_sha256'}

def _temperature_rows(body,decision,last):
    rows={};cells=set()
    for point in body['points']:
        if point['variable']!=TEMPERATURE:continue
        at=instant(point['valid_at'])
        if not decision<at<=last:continue
        rows.setdefault(at,{})[point['statistic']]=point['value'];cells.add((point['latitude'],point['longitude']))
    if len(cells)!=1:raise ValueError('one retained native station cell required')
    result=[]
    for at,statistics in sorted(rows.items()):
        if statistics.get('mean') is None:continue
        status='available' if statistics.get('p10') is not None and statistics.get('p90') is not None else 'missing_quantiles'
        try:validate_quantiles(statistics)
        except ValueError:status='crossing_quantiles';statistics={'mean':statistics['mean']}
        result.append(dict(valid_at=at.isoformat(),source_sha256=body['snapshot_sha256'],mean_c=statistics['mean'],
            **{s+'_c':statistics.get(s) for s in QUANTILES},range_status=status))
    grid=identity(dict(collection=COLLECTIONS['station'],variable=TEMPERATURE,cell=next(iter(cells))))
    return result,grid

def build_capability_report(archive,*,decision,site,horizons=(24,336),guard=lambda:None):
    """Select near/extended sources independently; every row retains its source.

    The longest covered source supplies the outlook, with newer short coverage
    overlaid only where it is actually present. This is a display composite.
    """
    decision=utc(decision)
    if not isinstance(site,Site) or not isinstance(horizons,tuple) or not horizons or any(type(h) is not int or not 1<=h<=336 for h in horizons):
        raise ValueError('bounded display horizons and authoritative site required')
    sources={};hours={};expires=decision+timedelta(minutes=90)
    for horizon in sorted(set(horizons),reverse=True):
        guard();end=decision+timedelta(hours=horizon);last=end.replace(minute=0,second=0,microsecond=0)
        if last<end:last+=timedelta(hours=1)
        try:
            selected=archive.eligible_snapshot(decision,last,required_variables={TEMPERATURE})
            if selected is None:continue
            body=prospective_snapshot(selected,issued_at=decision)
            if body['site']!=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone):raise ValueError('source site differs')
            rows,grid=_temperature_rows(body,decision,last);guard()
            if not rows:continue
            source=body['snapshot_sha256']
            actual_bands=sorted((original['collection'],tuple(original['payload']['region'][0][4:])) for original in body['source_originals'])
            sources[source]=dict(snapshot_sha256=source,profile_sha256=identity(dict(native_bands=actual_bands)),
                run_id=body['run_id'],initialized_at=body['initialized_at'],first_seen_at=body['first_seen_at'],
                available_at=body['ingestion_completed_at'],grid_sha256=grid)
            expires=min(expires,instant(body['initialized_at'])+timedelta(hours=24))
            for row in rows:hours[row['valid_at']]=row
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except (OSError,ValueError,KeyError,TypeError):
            # A malformed optional source/segment cannot erase another valid
            # segment or the separate legacy deterministic publication.
            guard();continue
    used={r['source_sha256'] for r in hours.values()}
    value=dict(schema=SCHEMA,provider='weathernext3',generated_at=decision.isoformat(),valid_until=expires.isoformat(),
        timezone=site.timezone,status='available' if hours else 'unavailable',sources=[s for k,s in sorted(sources.items()) if k in used],
        groups=dict(temperature=dict(method=METHOD,label=LABEL,nominal_interval_probability=.8,local_coverage_qualified=False,
            hours=[hours[k] for k in sorted(hours)])),automatic_actuation=False,release_authorized=False)
    value['report_sha256']=identity(value)
    return validate_capability_report(value)

def validate_capability_report(value,*,now=None):
    if isinstance(value,dict) and value.get('schema')=='earthship-weathernext-capabilities/v2':
        from .atmospheric_publish import validate_atmospheric_report
        return validate_atmospheric_report(value,now=now)
    fields={'schema','provider','generated_at','valid_until','timezone','status','sources','groups','automatic_actuation','release_authorized','report_sha256'}
    if (not isinstance(value,dict) or set(value)!=fields or value['schema']!=SCHEMA or value['provider']!='weathernext3' or
            value['automatic_actuation'] is not False or value['release_authorized'] is not False or
            len(canonical(value))>MAX_BYTES or value['report_sha256']!=identity({k:v for k,v in value.items() if k!='report_sha256'})):
        raise ValueError('bounded unchanged read-only capability report required')
    generated,end=map(instant,(value['generated_at'],value['valid_until']));ZoneInfo(value['timezone'])
    if not generated<end<=generated+timedelta(minutes=90):raise ValueError('bounded supplemental report lifetime required')
    if now is not None and not generated<=utc(now)<end:raise ValueError('capability report unavailable at read clock')
    if not isinstance(value['sources'],list) or len(value['sources'])>16:raise ValueError('bounded public source references required')
    sources={}
    for s in value['sources']:
        if not isinstance(s,dict) or set(s)!=SOURCE_FIELDS:raise ValueError('curated closed source reference required')
        for k in ('snapshot_sha256','profile_sha256','grid_sha256'):digest(s[k])
        init,seen,available=map(instant,(s['initialized_at'],s['first_seen_at'],s['available_at']))
        if not init<=seen<=available<=generated<=init+timedelta(hours=24):raise ValueError('source unavailable at issuance')
        if end>init+timedelta(hours=24):raise ValueError('report cannot renew original source lifetime')
        if not isinstance(s['run_id'],str) or not 1<=len(s['run_id'])<=128:raise ValueError('bounded run identity required')
        run=s['run_id']
        if run.startswith('ee:'):run_init=instant(run[3:])
        elif re.fullmatch(r'\d{8}_\d{2}hr_\d{2}_preds',run):run_init=datetime.strptime(run[:11],'%Y%m%d_%H').replace(tzinfo=timezone.utc)
        else:raise ValueError('known public native run identity required')
        if run_init!=init:raise ValueError('public run initialization differs')
        if s['snapshot_sha256'] in sources:raise ValueError('unique source references required')
        sources[s['snapshot_sha256']]=s
    groups=value['groups']
    if not isinstance(groups,dict) or set(groups)!={'temperature'}:raise ValueError('known capability groups required')
    t=groups['temperature']
    if (not isinstance(t,dict) or set(t)!={'method','label','nominal_interval_probability','local_coverage_qualified','hours'} or
            t['method']!=METHOD or t['label']!=LABEL or t['nominal_interval_probability']!=.8 or t['local_coverage_qualified'] is not False or
            not isinstance(t['hours'],list) or len(t['hours'])>337):raise ValueError('raw native temperature marginal contract required')
    times=[];used=set()
    for h in t['hours']:
        if not isinstance(h,dict) or set(h)!=HOUR_FIELDS or h['source_sha256'] not in sources:raise ValueError('closed source-bound temperature row required')
        at=instant(h['valid_at']);times.append(at);used.add(h['source_sha256']);s=sources[h['source_sha256']]
        if not generated<at<=instant(s['initialized_at'])+timedelta(hours=360):raise ValueError('future native target required')
        values={k[:-2]:v for k,v in h.items() if k.endswith('_c')}
        if not finite(values['mean']):raise ValueError('finite mean required')
        validate_quantiles(values)
        status=h['range_status']
        if (status not in ('available','missing_quantiles','crossing_quantiles') or
                (status=='available')!=(values['p10'] is not None and values['p90'] is not None) or
                status=='crossing_quantiles' and any(values[s] is not None for s in QUANTILES)):
            raise ValueError('truthful optional range status required')
    if times!=sorted(set(times)) or used!=set(sources):raise ValueError('ordered unique targets and used sources required')
    if value['status']!=('available' if times else 'unavailable'):raise ValueError('truthful supplemental availability required')
    return value

def retain_capability_report(root,value,*,indoor=None):
    """Explicit write boundary. Existing originals are never replaced."""
    from .shadow import ShadowStore,_directory
    from .worker import collector_lock
    value=validate_capability_report(value);root=Path(root);state=ShadowStore(root)
    _directory(root/'capability-issues')
    with collector_lock(root/'capability.lock'):
        moisture=value['groups'].get('atmosphere',{}).get('moisture')
        if moisture is not None and moisture['mode']=='qualified_comparison':
            from .moisture_context import current_sensor_context
            from .shadow import _read
            from household.sensor_observations import PreparedSensorObservations
            pin=moisture['indoor_context_sha256'];path=root/'capability-issues'/(pin+'.indoor.json')
            if indoor is None:
                try:original=_read(path,MAX_BYTES)
                except (OSError,ValueError):raise ValueError('original qualified indoor context required before publication') from None
                PreparedSensorObservations(canonical(original))
            else:original=current_sensor_context(indoor,instant(value['generated_at'])).to_dict()
            if identity(original)!=pin:raise ValueError('qualified indoor original differs from public source reference')
            from .atmospheric_publish import validate_moisture_original
            validate_moisture_original(value,PreparedSensorObservations(canonical(original)))
            state._write(path,original,immutable=True)
        state._write(root/'capability-issues'/(value['report_sha256']+'.json'),value,immutable=True)
        from .capability_scoring import CapabilityScores
        queue=CapabilityScores(state);queue.recover_latest();queue.register(value)
        state._write(root/'weather-capabilities.json',value)
        queue.confirm(value)
    return value['report_sha256']
