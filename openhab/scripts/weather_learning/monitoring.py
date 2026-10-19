"""Prospective weather outcome monitoring from retained issues; no fit or promotion."""
from datetime import datetime,time,timedelta
from zoneinfo import ZoneInfo
from .contracts import canonical,identity,instant,digest
from .evidence import utc
from .evaluation import _metrics,_horizon
from .features import temperature_targets,local_temperature_outcome,training_pair
from .shadow import TRAIN_OFFSETS,_read
from .solar_shadow import solar_window_forecast,compare_solar_windows,_source as validate_solar
from .energy_shadow import rain_day_forecast,compare_rain_products,_rain_source as validate_rain


def monitor_once(archive,state,*,now,site,sensor_epoch,code_revision,observation_policy_sha256,
                 read_temperature,read_solar,read_rain,apply=False,guard=lambda:None):
    now=utc(now);digest(observation_policy_sha256)
    if type(apply) is not bool:raise ValueError('explicit monitor publication required')
    issues=state.training_issues(now-timedelta(days=7),now,sensor_epoch=sensor_epoch)
    if len(issues)>8:raise ValueError('bounded original daily issues required')
    selected=[];solar_forecasts=[];rain_forecasts=[];solar_sources=[];rain_sources=[]
    pending=dict(solar=0,rain=0);withheld=[];zone=ZoneInfo(site.timezone)
    def source(kind,target,read,validate):
        key=identity(dict(kind=kind,target=target,policy_sha256=observation_policy_sha256))
        path=state.root/'weather-outcomes'/(key+'.json')
        if path.exists():
            value=validate(_read(path,16*1024**2))
            if instant(value['assessed_at'])>now:raise ValueError('future retained outcome refused')
            return value
        try:value=read()
        except Exception as error:
            guard();withheld.append(dict(kind=kind,target=target,reason=type(error).__name__));return None
        guard()
        if value is None:return None
        value=validate(value)
        if instant(value['assessed_at'])>now:raise ValueError('future local outcome refused')
        if apply:state._write(path,value,immutable=True)
        return value
    for original in issues:
        guard();payload=original['payload'];issued=instant(payload['decisionAt']);completed=instant(payload['generatedAt'])
        snapshot=archive.read(payload['source']['snapshotSha256'])
        if snapshot['site']!=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone):raise ValueError('weather monitoring site differs')
        targets={row.target_at:row for row in temperature_targets(snapshot,issued_at=issued)}
        first=min(targets)
        for row in payload['hours']:
            at=instant(row['at']);target=targets.get(at)
            if target is None or abs(target.mean_c-row['rawC'])>1e-9:raise ValueError('original issued temperature differs from Google source')
            offset=int((at-first).total_seconds()/3600)+1
            if at<=now-timedelta(minutes=2) and offset in TRAIN_OFFSETS:selected.append((target,row,payload['generation'],payload['model']['sha256']))
        next_day=issued.astimezone(zone).date()+timedelta(days=1)
        end=datetime.combine(next_day,time.min,zone).astimezone(now.tzinfo)
        start=completed.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        if start<end:
            forecast=solar_window_forecast(snapshot,issued_at=issued,completed_at=completed,start=start,end=end)
            solar_forecasts.append(forecast)
            if end+timedelta(minutes=2)<=now:
                value=source('solar',dict(start=start.isoformat(),end=end.isoformat()),lambda:read_solar(start,end,now),validate_solar)
                if value is not None:solar_sources.append(value)
            else:pending['solar']+=1
        forecast=rain_day_forecast(snapshot,issued_at=issued,completed_at=completed,local_date=next_day)
        rain_forecasts.append(forecast)
        rain_end=datetime.combine(next_day+timedelta(days=1),time.min,zone).astimezone(now.tzinfo)
        if rain_end+timedelta(minutes=2)<=now:
            value=source('rain',next_day.isoformat(),lambda:read_rain(next_day,now),validate_rain)
            if value is not None:rain_sources.append(value)
        else:pending['rain']+=1
    if len(selected)>320:raise ValueError('bounded prospective weather targets required')
    guard();metadata=read_temperature(sorted({target.target_at for target,_,_,_ in selected}),now) if selected else {};guard()
    raw=[];candidate=[];paired_raw=[];manifest=[];horizons={};missing=0
    for target,row,generation,model in selected:
        record=metadata.get(target.target_at)
        if record is None:missing+=1;continue
        try:outcome=local_temperature_outcome(record,target_at=target.target_at,assessed_at=now,sensor_epoch=sensor_epoch);pair=training_pair(target,outcome)
        except ValueError:missing+=1;continue
        day=target.target_at.astimezone(zone).date().isoformat();error=target.mean_c-outcome.value_c
        raw.append((error,day));horizon=horizons.setdefault(_horizon(target),dict(raw=[],candidate=[]));horizon['raw'].append((error,day))
        if row['localC'] is not None:
            candidate.append((row['localC']-outcome.value_c,day));paired_raw.append((error,day));horizon['candidate'].append((row['localC']-outcome.value_c,day))
        manifest.append(dict(pair_sha256=pair.pair_digest,issue_generation=generation,snapshot_sha256=target.snapshot_digest,
            model_sha256=model,outcome_sha256=outcome.receipt_digest,issued_at=target.issued_at.isoformat(),target_at=target.target_at.isoformat(),
            outcome_available_at=outcome.available_at.isoformat(),raw_c=target.mean_c,issued_local_c=row['localC'],observed_c=outcome.value_c))
    guard()
    report=dict(schema='earthship-weathernext-weather-performance/v1',provider='weathernext3',generated_at=now.isoformat(),
        valid_until=(now+timedelta(hours=2)).isoformat(),code_revision=code_revision,observation_policy_sha256=observation_policy_sha256,
        scoring_scope='original_daily_issues_and_frozen_local_predictions',issues=len(issues),
        temperature=dict(raw=_metrics(raw),candidate=_metrics(candidate),candidate_paired_raw=_metrics(paired_raw),withheld=missing,
            by_horizon={k:{name:_metrics(values) for name,values in v.items()} for k,v in horizons.items()},pair_manifest=manifest),
        solar=compare_solar_windows(solar_forecasts,solar_sources),rain=compare_rain_products(rain_forecasts,rain_sources),
        pending=pending,source_withheld=withheld,calibration_qualified=False,release_authorized=False,automatic_actuation=False)
    report['report_sha256']=identity(report)
    if len(canonical(report))>512*1024:raise ValueError('bounded weather performance report required')
    if apply:state._write(state.root/'weather-performance.json',report)
    return report
