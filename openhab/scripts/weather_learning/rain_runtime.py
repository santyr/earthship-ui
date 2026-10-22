"""Explicit source-pinned rain shadow producer; local reads, no fitting or selection."""
from datetime import datetime,time,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import urlopen
import argparse,json,time as monotime
from household_job_budget import AdmissionDeferred
from weather_source_files import _read
from weather_rain_evidence import RainPolicy
from .contracts import canonical,identity,instant,digest
from .evidence import utc
from .config import Site
from .archive import Archive
from .shadow import ShadowStore
from .rain_origin import make_origin
from .rain_calibration import make_forecast,_policy,PRODUCTS
from .rain_issues import make_issue
from .rain_two_part import numerical_sources,context as model_context
from .weather_response import validate_model as validate_gain
from .rain_queue import RainQueue,CACHE,public_view

ROOT=Path(__file__).resolve().parents[3]
FIELDS={'schema','enabled','archive','state','site','rain_policy','observation_cutover','resolution_source','model_artifacts','gain_model_artifacts','runtime_manifest'}


def runtime_manifest():return numerical_sources()


def _path(value,*,optional=False):
    if optional and value is None:return None
    if not isinstance(value,str) or not Path(value).is_absolute() or Path(value).resolve()!=Path(value):raise ValueError('resolved explicit rain path required')
    return Path(value)


def profile(path):
    value=json.loads(_read(Path(path),131072))
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!='earthship-rain-shadow-profile/v1' or type(value['enabled']) is not bool:raise ValueError('closed explicit rain profile required')
    Site(**value['site']);instant(value['observation_cutover'])
    for name in ('archive','state','rain_policy','resolution_source'):_path(value[name],optional=name=='resolution_source')
    for name in ('model_artifacts','gain_model_artifacts'):
        if not isinstance(value[name],dict) or len(value[name])>16:raise ValueError('bounded explicit rain model catalog required')
        for pin,ref in value[name].items():
            digest(pin)
            if not isinstance(ref,dict) or set(ref)!={'path','file_sha256'}:raise ValueError('literal rain artifact reference required')
            _path(ref['path']);digest(ref['file_sha256'])
    if value['runtime_manifest']!=runtime_manifest():raise ValueError('exact rain runtime source profile required')
    return value


def _sources(archive,decision,site,guard):
    if archive.missing:return []
    with archive._connect() as db:
        rows=db.execute('SELECT digest FROM snapshots WHERE historical=0 AND first_seen<=? AND completed<=? AND initialized>? ORDER BY initialized DESC,completed DESC,digest LIMIT 257',(decision.isoformat(),decision.isoformat(),(decision-timedelta(hours=24)).isoformat())).fetchall()
    if len(rows)>256:raise ValueError('bounded available rain source inventory required')
    result=[]
    for (name,) in rows:
        guard();source=archive.read(name)
        if source['site']!=site:continue
        # Declared native hours define eligibility before any mean/head values
        # are inspected. A newer short profile cannot hide an older long run.
        hours=[instant(p['valid_at']) for p in source['points'] if p['variable'] in PRODUCTS]
        if not hours:continue
        initialized=instant(source['initialized_at'])
        result.append(dict(name=name,initialized=initialized,completed=instant(source['ingestion_completed_at']),start=min(hours)-timedelta(hours=1),end=min(max(hours),initialized+timedelta(hours=360))))
    return result


def _interval_source(sources,start,end):
    eligible=[s for s in sources if s['start']<=start<end<=s['end']]
    if not eligible:return None
    latest=max((s['initialized'],s['completed']) for s in eligible);chosen=[s for s in eligible if (s['initialized'],s['completed'])==latest]
    if len(chosen)!=1:raise ValueError('conflicting same-clock original rain sources')
    return chosen[0]


def intervals(snapshot,decision,*,last=None):
    zone=ZoneInfo(snapshot['site']['timezone'])
    if last is None:last=min(instant(snapshot['initialized_at'])+timedelta(hours=360),max(instant(p['valid_at']) for p in snapshot['points'] if p['variable'] in PRODUCTS))
    first=decision.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1);rows=[];start=first
    while start+timedelta(hours=24)<=last:
        rows.append(('rolling_24_hours',start,start+timedelta(hours=24)));start+=timedelta(hours=24)
    day=decision.astimezone(zone).date()+timedelta(days=1)
    while True:
        start=datetime.combine(day,time.min,zone).astimezone(timezone.utc);end=datetime.combine(day+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
        if end>last:break
        rows.append(('local_calendar_day',start,end));day+=timedelta(days=1)
    day=decision.astimezone(zone).date();end=datetime.combine(day+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
    if first<end<=last:rows.append(('remaining_day',first,end))
    if len(rows)>32:raise ValueError('bounded future rain interval population required')
    return rows


def _artifact(ref):
    from hashlib import sha256
    raw=_read(_path(ref['path']),16*1024**2)
    if sha256(raw).hexdigest()!=ref['file_sha256']:raise ValueError('original rain artifact bytes changed')
    return json.loads(raw)


def _choose(models,decision,*,context=None):
    eligible=[m for m in models if instant(m['fitted_at'] if 'fitted_at' in m else m['trained_at'])<=decision and (context is None or m['context']==context)]
    if not eligible:return None
    def clock(m):return (instant(m['fitted_at'] if 'fitted_at' in m else m['trained_at']),instant(m['cutoff']))
    latest=max(map(clock,eligible));chosen=[m for m in eligible if clock(m)==latest]
    if len(chosen)!=1:raise ValueError('conflicting same-clock rain artifacts')
    return chosen[0]


def _read_current():
    with urlopen('http://127.0.0.1:5000/rain_evidence',timeout=3) as stream:raw=stream.read(4097)
    if len(raw)>4096:raise ValueError('bounded current rain receipt required')
    return raw.decode()


def _cache_current(queue,key,now):
    view=queue.original(key)['public_view']
    try:current=_read(queue.state.root/CACHE,16*1024**2)==canonical(view)
    except (OSError,ValueError):return False
    return current and instant(view['generated_at'])<=utc(now)<instant(view['valid_until'])


def run(path,*,apply=False,clock=lambda:datetime.now(timezone.utc),guard=lambda:None,origin_reader=None):
    if type(apply) is not bool:raise ValueError('explicit rain retention flag required')
    value=profile(path);guard()
    if not value['enabled']:return dict(status='disabled',retained=False,automatic_actuation=False)
    archive=Archive.open_readonly(_path(value['archive']),allow_missing=True)
    if archive.missing:return dict(status='source_unavailable',retained=False,automatic_actuation=False)
    native=json.loads(_read(_path(value['rain_policy']),8192))
    if native.pop('version',None)!=1:raise ValueError('known native rain policy required')
    native=RainPolicy(**native);resolution=None if value['resolution_source'] is None else json.loads(_read(_path(value['resolution_source']),65536))
    requested=utc(clock());raw=None
    try:raw=(origin_reader or _read_current)();guard()
    except (TimeoutError,AdmissionDeferred,MemoryError):raise
    except Exception:guard()
    received=utc(clock());origin=make_origin(raw=raw,requested_at=requested,received_at=received,policy=native,cutover=instant(value['observation_cutover']),resolution_source=resolution,experiment_policy=_policy(json.loads(_read(ROOT/'docs/operations/weathernext3-capabilities/rain-calibration-protocol.json',65536,source=True))))
    policy=origin['sources']['experiment_policy'];decision=utc(clock());guard();sources=_sources(archive,decision,value['site'],guard)
    if not sources:return dict(status='source_unavailable',retained=False,automatic_actuation=False)
    requests=[]
    for kind,start,end in intervals(dict(site=value['site']),decision,last=max(s['end'] for s in sources)):
        selected=_interval_source(sources,start,end)
        if selected is not None:requests.append((kind,start,end,selected['name']))
    source_names=sorted({name for _,_,_,name in requests});models=[];gains=[]
    for pin,ref in value['model_artifacts'].items():
        guard();m=_artifact(ref)
        if m.get('model_sha256')!=pin or identity({k:v for k,v in m.items() if k!='model_sha256'})!=pin or m['numerical_sources']!=value['runtime_manifest']:raise ValueError('original local rain artifact/source differs')
        models.append(m)
    for pin,ref in value['gain_model_artifacts'].items():
        guard();m=validate_gain(_artifact(ref))
        if m['model_sha256']!=pin or m['kind']!='rain_24h_mm':raise ValueError('original rain gain identity differs')
        gains.append(m)
    generation=identity(dict(snapshot_sha256s=source_names,origin_cohort_sha256=origin['cohort_sha256'],models=value['model_artifacts'],gains=value['gain_model_artifacts'],producer=value['runtime_manifest']))
    queue=None
    if apply:
        queue=RainQueue(ShadowStore(_path(value['state'])),policy=policy);old=queue.generation_bundle(generation)
        if old is None:queue.recover(clock=clock);old=queue.generation_bundle(generation)
        if old is not None:return dict(status='already_issued',retained=True,issued=True,bundle_sha256=old,cache_current=_cache_current(queue,old,clock()),automatic_actuation=False)
    issues=[];refusals=[]
    cached_name=None;cached_snapshot=None
    for kind,start,end,name in requests:
        guard()
        if name!=cached_name:cached_snapshot=archive.read(name);cached_name=name
        forecast=make_forecast(snapshot=cached_snapshot,start=start,end=end,issued_at=decision,completed_at=decision,interval_kind=kind,availability_basis='recorded_ingestion_availability');f=forecast.to_dict();prepared=utc(clock())
        if prepared>=start:refusals.append(dict(interval_kind=kind,start=start.isoformat(),reason='preparation_completed_after_interval_start'));continue
        model=_choose(models,decision,context=model_context(f,origin['cohort_sha256'])) if origin['status']=='available' else None
        issues.append(make_issue(forecast,model=model,observation_cohort_sha256=origin['cohort_sha256'],policy=policy,prepared_at=prepared,mode='prospective_shadow',gain_model=_choose(gains,decision)))
    guard()
    if value['runtime_manifest']!=runtime_manifest():raise ValueError('rain runtime source changed during preparation')
    if not issues:return dict(status='no_future_intervals',retained=False,refusals=refusals,automatic_actuation=False)
    if apply:key=queue.publish(issues,clock=clock,origin_context=origin,generation=generation);guard()
    else:key=None
    # A concurrent publication may have retained this generation first. Report
    # its actual originals, including refusals, rather than our unused proposal.
    wrapper=None if not apply else queue.original(key)
    values=[i.to_dict() for i in issues] if wrapper is None else wrapper['issues']
    local_rows=sum(i['local_prediction']['status']=='experimental_prediction' for i in values)
    return dict(status='local_shadow' if local_rows else 'raw_shadow',retained=apply,issued=apply,bundle_sha256=key,cache_current=None if not apply else _cache_current(queue,key,clock()),rows=len(values),source_snapshot_sha256s=sorted({i['forecast']['snapshot_sha256'] for i in values}),complete_comparison_rows=sum(i['forecast']['common_complete_targets'] for i in values),interval_kinds=sorted({i['forecast']['interval_kind'] for i in values}),local_candidate_rows=local_rows,origin_status=origin['status'] if wrapper is None else wrapper['origin_context']['status'],generation_sha256=generation,refusals=refusals,probability_calibration_qualified=False,selected_pointer_installed=False,automatic_actuation=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,required=True);p.add_argument('--apply',action='store_true');args=p.parse_args(argv);deadline=monotime.monotonic()+90
    def guard():
        if monotime.monotonic()>=deadline:raise TimeoutError('optional rain producer deadline elapsed')
    try:print(json.dumps(run(args.profile,apply=args.apply,guard=guard)));return 0
    except Exception as error:print(json.dumps(dict(status='unavailable',reason=type(error).__name__,retained=None,emission_status='unknown_partial_state',automatic_actuation=False)));return 1

if __name__=='__main__':raise SystemExit(main())
