"""Prospective weather outcome monitoring from retained issues; no fit or promotion."""
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
from household_job_budget import AdmissionDeferred
from .contracts import canonical,identity,instant,digest
from .evidence import utc
from .performance import (score_temperature,summarize_temperature_scores,validate_temperature_score,
    EVALUATION_VERSION,EVALUATION_CONTRACT_SHA256)
from .pending_scores import PendingScores
from .features import local_temperature_outcome
from .shadow import _read
from .solar_shadow import solar_window_forecast,compare_solar_windows,solar_comparison_report,_source as validate_solar
from .energy_shadow import rain_day_forecast,compare_rain_products,rain_comparison_report,_rain_source as validate_rain


def monitor_once(archive,state,*,now,site,sensor_epoch,code_revision,observation_policy_sha256,
                 read_temperature,read_solar,read_rain,apply=False,guard=lambda:None,read_corrections=None,read_capabilities=None,read_refresh=None):
    import tempfile
    from pathlib import Path
    if type(apply) is not bool:raise ValueError('explicit monitor publication required')
    arguments=dict(now=now,site=site,sensor_epoch=sensor_epoch,code_revision=code_revision,
        observation_policy_sha256=observation_policy_sha256,read_temperature=read_temperature,
        read_solar=read_solar,read_rain=read_rain,apply=apply,guard=guard,read_corrections=read_corrections,read_capabilities=read_capabilities,read_refresh=read_refresh)
    context=dict(sensor_epoch=sensor_epoch,observation_policy_sha256=observation_policy_sha256,
        evaluation_version=EVALUATION_VERSION,evaluation_contract_sha256=EVALUATION_CONTRACT_SHA256)
    if apply:
        return _monitor_once(archive,state,queue=PendingScores(state,**context),**arguments)
    # Preview performs the same bounded discovery/scoring against a disposable
    # index; it never advances the production cursor or completes durable work.
    with tempfile.TemporaryDirectory(prefix='monitor-preview-',dir=state.root) as temporary:
        queue=PendingScores(state,db_path=Path(temporary)/'queue.sqlite3',**context)
        return _monitor_once(archive,state,queue=queue,**arguments)


def _monitor_once(archive,state,*,queue,now,site,sensor_epoch,code_revision,observation_policy_sha256,
                 read_temperature,read_solar,read_rain,apply,guard,read_corrections,read_capabilities,read_refresh):
    now=utc(now);digest(observation_policy_sha256)
    if type(apply) is not bool:raise ValueError('explicit monitor publication required')
    names=state.training_issue_names(now-timedelta(days=7),now,sensor_epoch=sensor_epoch)
    if len(names)>8:raise ValueError('bounded original daily issues required')
    solar_forecasts=[];rain_forecasts=[];solar_sources=[];rain_sources=[]
    pending=dict(solar=0,rain=0);withheld=[];zone=ZoneInfo(site.timezone)
    source_attempts=0
    if read_corrections is not None and not callable(read_corrections):raise ValueError('callable correction monitor required')
    if read_capabilities is not None and not callable(read_capabilities):raise ValueError('callable capability monitor required')
    def source(kind,target,read,validate):
        nonlocal source_attempts
        key=identity(dict(kind=kind,target=target,policy_sha256=observation_policy_sha256))
        path=state.root/'weather-outcomes'/(key+'.json')
        try:
            if path.exists():
                value=validate(_read(path,16*1024**2))
                if instant(value['assessed_at'])>now:raise ValueError('future retained outcome refused')
                return value
            source_attempts+=1
            value=read();guard()
            if value is None:return None
            value=validate(value)
            if instant(value['assessed_at'])>now:raise ValueError('future local outcome refused')
            if apply:state._write(path,value,immutable=True)
            return value
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception as error:
            guard();withheld.append(dict(kind=kind,target=target,reason=type(error).__name__));return None
    def optional(kind,operation,**context):
        # Cancellation, owner deadlines and resource admission are global stops;
        # an optional data/derivation fault is scoped to its issue and domain.
        guard()
        try:
            result=operation();guard();return result
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception as error:
            guard();withheld.append(dict(kind=kind,reason=type(error).__name__[:80],**context));return None
    issues=[]
    for name in names:
        guard()
        try:
            original=state.read_issue(name);payload=original['payload']
            snapshot=archive.read(payload['source']['snapshotSha256'])
            if snapshot['site']!=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone):
                raise ValueError('weather monitoring site differs')
        except (OSError,ValueError,KeyError,TypeError) as error:
            withheld.append(dict(kind='original_issue',issue_sha256=name,reason=type(error).__name__));continue
        issues.append((original,snapshot))
    for original,snapshot in issues:
        guard();payload=original['payload'];issued=instant(payload['decisionAt']);completed=instant(payload['generatedAt'])
        next_day=issued.astimezone(zone).date()+timedelta(days=1)
        end=datetime.combine(next_day,time.min,zone).astimezone(now.tzinfo)
        start=completed.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        if start<end:
            forecast=optional('solar_derivation',lambda:solar_window_forecast(snapshot,issued_at=issued,completed_at=completed,start=start,end=end),
                issue_sha256=identity(original))
            if forecast is not None:
                solar_forecasts.append(forecast)
                if end+timedelta(minutes=2)<=now:
                    value=source('solar',dict(start=start.isoformat(),end=end.isoformat()),lambda:read_solar(start,end,now),validate_solar)
                    if value is not None:solar_sources.append(value)
                else:pending['solar']+=1
        forecast=optional('rain_derivation',lambda:rain_day_forecast(snapshot,issued_at=issued,completed_at=completed,local_date=next_day),
            issue_sha256=identity(original))
        if forecast is not None:
            rain_forecasts.append(forecast)
            rain_end=datetime.combine(next_day+timedelta(days=1),time.min,zone).astimezone(now.tzinfo)
            if rain_end+timedelta(minutes=2)<=now:
                value=source('rain',next_day.isoformat(),lambda:read_rain(next_day,now),validate_rain)
                if value is not None:rain_sources.append(value)
            else:pending['rain']+=1
    bootstrap=queue.bootstrap(archive,site=site,now=now,guard=guard)
    capability_reserve=min(8,max(0,64-source_attempts)) if read_capabilities is not None else 0
    refresh_reserve=min(8,max(0,64-source_attempts-capability_reserve)) if read_refresh is not None else 0
    temperature_limit=min(32 if read_corrections is not None else 64,max(0,64-source_attempts-capability_reserve-refresh_reserve))
    due=queue.due(now,limit=temperature_limit) if temperature_limit else [];loaded=[]
    for work in due:
        guard()
        try:original,target,row=queue.load(work,archive,site=site)
        except FileNotFoundError:
            queue.defer(work,reason='missing_original',now=now);continue
        except (ValueError,KeyError,TypeError):
            queue.defer(work,reason='invalid_original',now=now);continue
        loaded.append((work,original,target,row))
    try:
        guard();metadata=read_temperature(sorted({target.target_at for _,_,target,_ in loaded}),now) if loaded else {};guard()
        if not isinstance(metadata,dict):raise ValueError('explicit temperature observation mapping required')
    except (TimeoutError,AdmissionDeferred,MemoryError):raise
    except Exception as error:
        guard();metadata={};withheld.append(dict(kind='temperature',reason=type(error).__name__))
    missing=0
    for work,original,target,row in loaded:
        guard();record=metadata.get(target.target_at)
        if record is None:
            missing+=1;queue.defer(work,reason='observation_missing',now=now);continue
        try:
            outcome=local_temperature_outcome(record,target_at=target.target_at,assessed_at=now,sensor_epoch=sensor_epoch)
            score=score_temperature(original=original,target=target,row=row,outcome=outcome,
                observation_policy_sha256=observation_policy_sha256)
        except (ValueError,KeyError,TypeError):
            missing+=1;queue.defer(work,reason='quality_withheld',now=now);continue
        queue.commit(work,score,validator=validate_temperature_score)
    scores=list(queue.iter_scores(now-timedelta(days=7),now))
    temperature=summarize_temperature_scores(scores,withheld=missing)
    temperature['coverage_window']=queue.window_counts(now-timedelta(days=7),now,now=now)
    temperature['work']=dict(bootstrap=bootstrap,states=queue.counts(),dependencies=queue.source_dependencies(),backlog=queue.backlog(now),
        batch_limit=temperature_limit,observation_arrival_allowance_days=7,report_target_window_days=7)
    corrections=None
    capability_attempts=0
    if read_capabilities is not None:
        # An optional fault may follow successful reads, so its full reservation
        # remains consumed on failure. Never lend an unknown partial budget.
        capability_attempts=capability_reserve
        try:
            guard();capabilities=read_capabilities(now=now,limit=capability_reserve,apply=apply,guard=guard);guard()
            used=capabilities['observations_attempted']
            if type(used) is not int or not 0<=used<=capability_reserve:raise ValueError('bounded capability observation accounting required')
            capability_attempts=used
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception as error:
            guard();withheld.append(dict(kind='capabilities',reason=type(error).__name__))
    refresh_attempts=0
    if read_refresh is not None:
        refresh_attempts=refresh_reserve
        try:
            guard();refresh=read_refresh(now=now,limit=refresh_reserve,apply=apply,guard=guard);guard()
            used=refresh['observations_attempted']
            if type(used) is not int or not 0<=used<=refresh_reserve:raise ValueError('bounded refresh observation accounting required')
            refresh_attempts=used
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception as error:
            guard();withheld.append(dict(kind='refresh',reason=type(error).__name__))
    if read_corrections is not None:
        # Legacy daily windows and every attempted queue label share one budget.
        # Reserve temperature work, then lend only the remaining quota.
        remaining=min(32,max(0,64-source_attempts-len(loaded)-capability_attempts-refresh_attempts))
        try:
            guard();corrections=read_corrections(now=now,limit=remaining,apply=apply,guard=guard);guard()
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except Exception as error:
            guard();corrections=dict(status='unavailable',reason=type(error).__name__,automatic_actuation=False)
    guard()
    solar=optional('solar_aggregation',lambda:compare_solar_windows(solar_forecasts,solar_sources))
    rain=optional('rain_aggregation',lambda:compare_rain_products(rain_forecasts,rain_sources))
    if solar is None:solar=solar_comparison_report(pairs=[],withheld=[],cohorts={},decisions=[])
    if rain is None:rain=rain_comparison_report(pairs=[],withheld=[],cohorts={},decisions=[])
    guard()
    report=dict(schema='earthship-weathernext-weather-performance/v2',provider='weathernext3',generated_at=now.isoformat(),
        valid_until=(now+timedelta(hours=2)).isoformat(),code_revision=code_revision,observation_policy_sha256=observation_policy_sha256,
        scoring_scope='original_daily_issues_and_frozen_local_predictions',issues=len(issues),
        temperature=temperature,corrections=corrections,
        solar=solar,rain=rain,
        pending=pending,source_withheld=withheld,calibration_qualified=False,release_authorized=False,automatic_actuation=False)
    report['report_sha256']=identity(report)
    if len(canonical(report))>512*1024:raise ValueError('bounded weather performance report required')
    if apply:state._write(state.root/'weather-performance.json',report)
    return report
