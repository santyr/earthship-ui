#!/usr/bin/env python3
"""Bounded independent calibrated-storage scoring; original models stay intact."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from io import BytesIO
import argparse,gzip,json,os,time,traceback
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household_native_training import directory,save,effective_selection
from household_observation import _private_file
from household_ac_load_store import _immutable
from household_calibrated_energy import replay,MAX_BYTES as FORECAST_MAX
from household_calibrated_outcomes import seal_outcomes,summarize_score,validate_score,validate_sample,performance,_predictions,HORIZONS,MAX_BYTES
from household_solar_score import read_forecast as read_energy,unchanged as energy_unchanged
from household_profiled_score import read_forecast as read_profile,unchanged as profile_unchanged
from weather_learning.worker import collector_lock
from calibrated_score_runtime import producer_roots,select_source_root,model_operation

FORECAST_SUFFIX='.calibrated-energy-v1.json'
SCORE_SUFFIX='.calibrated-score-v1.json.gz'
SAMPLE_SUFFIX='.calibrated-sample-v1.json'


def resolve_originals(forecast,*,stages):
    inputs=forecast['inputs'];pin=inputs['original_energy_document_sha256'];profile_pin=inputs['original_profiled_document_sha256']
    for stage in stages:
        evidence=Path(stage)/'evidence';path=evidence/(pin+'.household-energy-forecast-v1.json')
        if not path.exists():continue
        energy,plan,original=read_energy(path);energy_unchanged(original);profile=None;profile_path=None
        if profile_pin is not None:
            profile_path=evidence/(profile_pin+'.household-profiled-energy-v1.json')
            profile,other_energy,other_plan,profile_original=read_profile(profile_path);profile_unchanged(profile_original)
            if canonical(other_energy)!=canonical(energy) or canonical(other_plan)!=canonical(plan):raise ValueError('same-issue calibrated inputs required')
        if identity(energy)!=pin or plan['receipt_sha256']!=inputs['plan_receipt_sha256'] or profile_pin is not None and identity(profile)!=profile_pin:raise ValueError('original calibrated context differs')
        return energy,plan,profile,dict(energy_path=str(path),profiled_path=None if profile_path is None else str(profile_path))
    raise ValueError('retained calibrated forecast inputs unavailable')


def _forecast(path):
    raw=_private_file(path,FORECAST_MAX)[0];value=loads(raw)
    if path.name!=sha256(raw).hexdigest()+FORECAST_SUFFIX or value.get('receipt_sha256')!=identity({k:v for k,v in value.items() if k!='receipt_sha256'}):raise ValueError('original calibrated forecast differs')
    return value


def _inventory(store,*,now,guard):
    entries=[]
    with os.scandir(store) as stream:
        for i,entry in enumerate(stream):
            guard()
            if i>=20000:raise ValueError('bounded calibrated forecast inventory required')
            if not entry.name.endswith(FORECAST_SUFFIX):continue
            if not entry.is_file(follow_symlinks=False):raise ValueError('regular original forecast required')
            entries.append((entry.stat(follow_symlinks=False).st_mtime_ns,Path(entry.path)))
    values=[]
    for _,path in sorted(entries,reverse=True)[:512]:
        guard();value=_forecast(path);issue=instant(value['output']['issued_at'])
        if now-timedelta(hours=36)<=issue<=now:values.append((issue,path,value))
    return sorted(values,key=lambda r:(r[0],str(r[1])))


def _read_score(store,ref):
    raw=_private_file(store/(ref['score_file_sha256']+SCORE_SUFFIX),MAX_BYTES+65536)[0]
    if sha256(raw).hexdigest()!=ref['score_file_sha256']:raise ValueError('retained complete calibrated score differs')
    with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:expanded=stream.read(MAX_BYTES+1)
    if len(expanded)>MAX_BYTES:raise ValueError('bounded expanded calibrated score required')
    return validate_score(loads(expanded))


def _read_sample(store,ref):
    raw=_private_file(store/(ref['sample_sha256']+SAMPLE_SUFFIX),32768)[0];value=validate_sample(loads(raw))
    if identity(value)!=ref['sample_sha256'] or value['score_file_sha256']!=ref['score_file_sha256']:raise ValueError('retained calibrated sample differs')
    # Check original complete file bytes without reparsing all past sensor rows.
    full=_private_file(store/(ref['score_file_sha256']+SCORE_SUFFIX),MAX_BYTES+65536)[0]
    if sha256(full).hexdigest()!=ref['score_file_sha256']:raise ValueError('sample complete original score differs')
    return value


def run(*,state,view,clock=lambda:datetime.now(timezone.utc)):
    from household_cycle_pressure import PublicationHeadroom
    from household_forecast_score import read_score_dispatch
    state=directory(state);store=directory(state/'outcomes');deadline=time.monotonic()+75;pressure=PublicationHeadroom()
    def guard():
        pressure.check()
        if time.monotonic()>deadline:raise TimeoutError('calibrated outcome deadline elapsed')
    with collector_lock(store/'worker.lock'):
        guard();now=clock();selection=effective_selection();dispatch=read_score_dispatch(Path(selection['stage']),deployment_sha256=selection['deployment_sha256'],guard=guard)
        stages=[Path(selection['stage']),*[Path(r['stage']) for r in dispatch['historical']]]
        inventory=_inventory(state/'forecasts',now=now,guard=guard)
        if not inventory:return dict(status='awaiting_calibrated_forecast',automatic_actuation=False)
        roots=producer_roots();latest=inventory[-1];energy,plan,profile,_=resolve_originals(latest[2],stages=stages)
        origin=model_operation(producer_root=select_source_root(latest[2],roots),mode='origin',inputs=dict(forecast=latest[2],energy=energy,plan=plan,profiled=profile),state=store,deadline=deadline,guard=guard);guard()
        index_path=store/'index.json'
        try:index=loads(_private_file(index_path,1048576)[0])
        except FileNotFoundError:index=dict(schema='earthship-calibrated-outcome-index/v1',origins={})
        if set(index)!={'schema','origins'} or index['schema']!='earthship-calibrated-outcome-index/v1' or not isinstance(index['origins'],dict) or len(index['origins'])>512:raise ValueError('bounded owned calibrated origin index required')
        refs={k:r for k,r in index['origins'].items() if now-timedelta(days=7)<=instant(r['issued_at'])<=now}
        seen={(instant(r['issued_at']).replace(minute=0,second=0,microsecond=0),r['calibration_model_sha256']) for r in refs.values()}
        for issue,path,forecast in inventory:
            calibration=json.loads(forecast['inputs']['calibration_raw'])['final_model']['model_sha256'];key=(issue.replace(minute=0,second=0,microsecond=0),calibration)
            if key in seen:continue
            guard();energy,plan,profile,context=resolve_originals(forecast,stages=stages);metadata=_predictions(forecast,plan,profile);pin=identity(forecast)
            refs[pin]=dict(forecast_path=str(path),stage=str(Path(context['energy_path']).parents[1]),issued_at=issue.isoformat(),cohort_id=metadata['cohort_id'],
                calibration_model_sha256=calibration,score_file_sha256=None,sample_sha256=None,retry_after=(issue+timedelta(hours=1,minutes=5)).isoformat())
            seen.add(key)
        if len(refs)>512:raise ValueError('bounded sampled calibrated origins required')
        due=[(instant(r['retry_after']),k,r) for k,r in refs.items() if r['retry_after'] is not None and instant(r['retry_after'])<=now]
        deferred=[];scored=None
        if due:
            _,pin,ref=min(due);forecast=_forecast(Path(ref['forecast_path']));energy,plan,profile,_=resolve_originals(forecast,stages=[ref['stage']]);metadata=_predictions(forecast,plan,profile)
            previous=None if ref['score_file_sha256'] is None else _read_score(store,ref)
            hours={} if previous is None else loads(canonical(previous['inputs']['hour_sources']));endpoints={} if previous is None else loads(canonical(previous['inputs']['endpoint_sources']))
            from household_capture import _connection
            from household_battery_source import fetch_endpoint
            from household_ac_load_window import capture_hour
            connect=_connection(str(Path.home()/'.config/hex/energy-power-reader.jdbc'),'energy_power_reader')
            def remaining():
                guard();left=min(12.,deadline-time.monotonic()-10.)
                if left<1:raise TimeoutError('calibrated source read opportunity elapsed')
                return left
            # At most one horizon/two fixed read-only source queries per run.
            for h in HORIZONS:
                key=str(h);target=instant(ref['issued_at'])+timedelta(hours=h);p=metadata['by_horizon'][key]
                if now<target+timedelta(minutes=5):continue
                need_hour=key not in hours and p['load_mean_ac_w'] is not None;need_endpoint=key not in endpoints and p['soc_predictions'] is not None
                if not (need_hour or need_endpoint):continue
                if need_hour:
                    try:hours[key]=capture_hour(connect=connect,start=target-timedelta(hours=1),end=target,clock=clock,remaining=remaining)
                    except Exception as error:deferred.append(type(error).__name__)
                if need_endpoint:
                    try:endpoints[key]=fetch_endpoint(lambda:connect(remaining=remaining),target_at=target,remaining=remaining,clock=clock)
                    except Exception as error:deferred.append(type(error).__name__)
                break
            guard();score=model_operation(producer_root=select_source_root(forecast,roots),mode='score',inputs=dict(forecast=forecast,energy=energy,plan=plan,profiled=profile,hour_sources=hours,endpoint_sources=endpoints,assessed_at=clock()),state=store,deadline=deadline,guard=guard);guard()
            raw=canonical(score);compressed=gzip.compress(raw,compresslevel=3,mtime=0);file_pin=sha256(compressed).hexdigest();_immutable(store/(file_pin+SCORE_SUFFIX),compressed)
            sample=summarize_score(score,verified_at=clock(),score_file_sha256=file_pin);sample_raw=canonical(sample);sample_pin=sha256(sample_raw).hexdigest();_immutable(store/(sample_pin+SAMPLE_SUFFIX),sample_raw)
            pending=[]
            for h in HORIZONS:
                key=str(h);p=metadata['by_horizon'][key];target=instant(ref['issued_at'])+timedelta(hours=h,minutes=5)
                if (p['load_mean_ac_w'] is not None and key not in hours) or (p['soc_predictions'] is not None and key not in endpoints):pending.append(target)
            retry=None if not pending else max(min(pending),clock()+timedelta(minutes=15) if deferred else clock())
            ref.update(score_file_sha256=file_pin,sample_sha256=sample_pin,retry_after=None if retry is None else retry.isoformat());scored=ref['issued_at']
        samples=[]
        for ref in refs.values():
            guard()
            if ref['sample_sha256'] is not None:samples.append(_read_sample(store,ref))
        report=performance(samples,origin=origin,generated_at=clock());directory(Path(view).parent)
        try:old=loads(_private_file(view,32768)[0])
        except FileNotFoundError:old=None
        if old is not None and old.get('schema')!=report['schema']:raise ValueError('calibrated report belongs to another producer')
        guard();save(index_path,dict(schema=index['schema'],origins=refs));save(view,report)
        return dict(status='calibrated_outcomes_published',sampled_origins=len(refs),scored_origin=scored,deferred_source_reasons=deferred,cohort_id=origin['cohort_id'],by_horizon=report['by_horizon'],automatic_actuation=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,default=Path.home()/'.local/state/household-intel/calibrated-energy');p.add_argument('--view',type=Path,default=Path.home()/'.local/state/household-intel/calibrated-energy-performance.json');a=p.parse_args(argv);os.umask(0o077)
    try:
        result=run(state=a.state,view=a.view);save(a.state/'last-score-result.json',dict(result,checked_at=datetime.now(timezone.utc).isoformat()));print(json.dumps(result),flush=True);return 0
    except Exception as error:
        directory(a.state);save(a.state/'last-score-error.json',dict(at=datetime.now(timezone.utc).isoformat(),reason=type(error).__name__,traceback=traceback.format_exc()[-8192:]));print(json.dumps(dict(status='calibrated_outcomes_unavailable',reason=type(error).__name__,automatic_actuation=False)),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
