"""Bounded hourly original sampling and SoC outcomes for the solar/load scenario."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
import os,time
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc,digest
from household_observation import _private_file,_directory
from household_energy_forecast import forecast_runtime_manifest,replay_energy_forecast
from household_solar_outcomes import seal_energy_outcomes,validate_score,cohort_for,build_energy_performance,energy_outcome_runtime_manifest,HORIZONS,MAX_BYTES
from household_energy_state import publish_owned,INDEX

SUFFIX='.household-energy-forecast-v1.json'
SCORE_SUFFIX='.solar-storage-outcome-v1.json'


def read_forecast(path):
    path=Path(path);original=_private_file(path,262144);forecast=loads(original[0])
    if path.name!=sha256(original[0]).hexdigest()+SUFFIX or forecast.get('schema')!='earthship-household-energy-forecast-receipt/v1':raise ValueError('original solar forecast file differs')
    pin=forecast['inputs']['plan_document_sha256'];digest(pin)
    plan_path=path.parent/(pin+'.household-model-plan-v6.json');plan_original=_private_file(plan_path,2097152)
    if sha256(plan_original[0]).hexdigest()!=pin:raise ValueError('original solar plan file differs')
    return forecast,loads(plan_original[0]),(path,original,plan_path,plan_original)


def unchanged(originals):
    path,original,plan_path,plan_original=originals
    if _private_file(path,262144)!=original or _private_file(plan_path,2097152)!=plan_original:raise ValueError('original solar inputs changed')


def read_score(path):
    raw,_=_private_file(Path(path),MAX_BYTES)
    if Path(path).name!=sha256(raw).hexdigest()+SCORE_SUFFIX:raise ValueError('retained solar score filename differs')
    return validate_score(loads(raw))


def candidates(stages,*,now,guard):
    groups={};cutoff=now-timedelta(days=7)
    for stage in stages:
        directory=Path(stage)/'evidence';_directory(directory)
        with os.scandir(directory) as entries:
            for i,entry in enumerate(entries):
                guard()
                if i>=20000:raise ValueError('bounded retained solar inventory required')
                if not entry.name.endswith(SUFFIX):continue
                if not entry.is_file(follow_symlinks=False):raise ValueError('regular original solar receipt required')
                stamp=datetime.fromtimestamp(entry.stat(follow_symlinks=False).st_mtime,timezone.utc)
                if not cutoff<=stamp<=now:continue
                hour=stamp.replace(minute=0,second=0,microsecond=0);group=groups.setdefault(hour,[]);group.append((stamp,str(directory/entry.name)));group.sort()
                if len(group)>3:group[1:-2]=[]
    return [Path(path) for _,rows in sorted(groups.items()) for _,path in rows]


def score_origin(path,*,previous,reader,clock,guard,forecast_runtime,outcome_runtime):
    guard();forecast,plan,original=read_forecast(path);sources={}
    if previous is not None:
        validate_score(previous)
        if previous['inputs']['forecast_document_sha256']!=sha256(original[1][0]).hexdigest() or previous['inputs']['forecast_receipt_sha256']!=forecast['receipt_sha256']:raise ValueError('previous solar outcome original differs')
        sources=loads(canonical(previous['inputs']['endpoint_sources']))
        if instant(previous['inputs']['assessed_at'])>utc(clock()):raise ValueError('solar assessment clock regressed')
    issue=instant(forecast['output']['array_pv']['origin']);now=utc(clock())
    if forecast['output']['nominal_storage']['status']=='conditional_nominal_simulation':
        for h in HORIZONS:
            key=str(h);target=issue+timedelta(hours=h)
            if now>=target+timedelta(minutes=5) and key not in sources:
                guard()
                source=reader(target_at=target)
                if source is None:break
                sources[key]=source;guard()
    result=seal_energy_outcomes(forecast_receipt=forecast,plan_receipt=plan,endpoint_sources=sources,assessed_at=clock(),forecast_runtime_manifest=forecast_runtime,outcome_runtime_manifest=outcome_runtime)
    unchanged(original);guard();return result


def run(*,stage,historical,guard,deadline,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,state_root=None,reader=None):
    now=utc(clock());stop=min(deadline,monotonic()+15.)
    def check():
        guard()
        if monotonic()>=stop:raise TimeoutError('solar storage scoring opportunity elapsed')
    check();runtime=energy_outcome_runtime_manifest();fr=forecast_runtime_manifest()
    stages=[Path(stage)]+[Path(row['stage']) for row in historical]
    if len(stages)>64 or len(set(stages))!=len(stages):raise ValueError('bounded unique retained solar stages required')
    root=Path(state_root) if state_root is not None else Path.home()/'.local/state/household-intel';_directory(root)
    store=root/'energy-outcomes'
    try:store.mkdir(mode=0o700)
    except FileExistsError:pass
    _directory(store);index_path=store/'samples.json'
    try:index=loads(_private_file(index_path,262144)[0])
    except FileNotFoundError:index=dict(schema=INDEX,samples={})
    if not isinstance(index,dict) or set(index)!={'schema','samples'} or index['schema']!=INDEX or not isinstance(index['samples'],dict) or len(index['samples'])>192:raise ValueError('bounded original solar sample index required')
    paths=candidates(stages,now=now,guard=check);current=[p for p in paths if p.parent==Path(stage)/'evidence']
    if not current:return dict(status='waiting',reason='current_solar_origin_unavailable')
    latest=max(current,key=lambda p:p.stat().st_mtime);forecast,plan,original=read_forecast(latest)
    replay_energy_forecast(forecast,plan_receipt=plan,runtime_manifest=fr);unchanged(original);check()
    if plan['output']['projections'].get('energy_persistence',{}).get('status')!='projected_nominal_baseline':
        return dict(status='waiting',reason='current_solar_reference_unavailable')
    cohort=cohort_for(forecast,plan)
    if cohort is None:return dict(status='waiting',reason='current_solar_storage_scenario_unavailable')
    cohort_id=identity(cohort);samples={};allowed={s/'evidence' for s in stages}
    for hour,ref in index['samples'].items():
        at=instant(hour)
        if at!=at.replace(minute=0,second=0,microsecond=0) or at>now:raise ValueError('original UTC sample hour required')
        if at<now-timedelta(days=7):continue
        if not isinstance(ref,dict) or set(ref)!={'forecast_path','forecast_sha256','forecast_receipt_sha256','issued_at','cohort_id','score_path','retry_after'}:raise ValueError('closed original solar reference required')
        path=Path(ref['forecast_path'])
        for key in ('forecast_sha256','forecast_receipt_sha256','cohort_id'):digest(ref[key])
        if path.parent not in allowed or path.name!=ref['forecast_sha256']+SUFFIX or instant(ref['issued_at']).replace(minute=0,second=0,microsecond=0)!=at:raise ValueError('retained hourly solar origin differs')
        if ref['score_path'] is not None and Path(ref['score_path']).parent!=store:raise ValueError('owned retained solar score required')
        if ref['retry_after'] is not None and not instant(ref['issued_at'])<=instant(ref['retry_after'])<=now+timedelta(minutes=30):raise ValueError('bounded source retry required')
        samples[hour]=ref
    for path in paths:
        check();hint=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).replace(minute=0,second=0,microsecond=0).isoformat()
        if hint in samples:continue
        forecast,plan,original=read_forecast(path);issued=instant(forecast['output']['array_pv']['origin']);hour=issued.replace(minute=0,second=0,microsecond=0).isoformat()
        if hour in samples or not now-timedelta(days=7)<=issued<=now or forecast['runtime_manifest']!=fr:continue
        if cohort_for(forecast,plan)!=cohort or plan['output']['projections'].get('energy_persistence',{}).get('status')!='projected_nominal_baseline':continue
        replay_energy_forecast(forecast,plan_receipt=plan,runtime_manifest=fr);unchanged(original)
        samples[hour]=dict(forecast_path=str(path),forecast_sha256=sha256(original[1][0]).hexdigest(),forecast_receipt_sha256=forecast['receipt_sha256'],issued_at=issued.isoformat(),cohort_id=cohort_id,score_path=None,retry_after=None)
        break
    scores=[];pending=[];due=[]
    for hour,ref in sorted(samples.items()):
        check()
        if ref['cohort_id']!=cohort_id:continue
        score=None if ref['score_path'] is None else read_score(Path(ref['score_path']))
        if score is not None:
            if score['inputs']['forecast_document_sha256']!=ref['forecast_sha256'] or score['inputs']['forecast_receipt_sha256']!=ref['forecast_receipt_sha256'] or score['output']['cohort_id']!=cohort_id:raise ValueError('retained score origin/cohort differs')
            scores.append(score)
        mature=[]
        for h in HORIZONS:
            if score is not None and str(h) in score['inputs']['endpoint_sources']:continue
            at=instant(ref['issued_at'])+timedelta(hours=h,minutes=5)
            if ref['retry_after'] is not None:at=max(at,instant(ref['retry_after']))
            pending.append(at)
            if at<=now:mature.append(at)
        if mature:due.append((min(mature),hour,ref,score))
    if due:
        _,hour,ref,previous=min(due)
        if reader is None:
            from household_capture import _connection
            from household_battery_source import fetch_endpoint
            connect=_connection(str(Path.home()/'.config/hex/energy-power-reader.jdbc'),'energy_power_reader')
            def remaining():
                check();budget=min(15.,stop-monotonic())
                if budget<1:raise TimeoutError('solar endpoint collection budget elapsed')
                return budget
            reader=lambda **request:fetch_endpoint(lambda:connect(remaining=remaining),remaining=remaining,clock=clock,**request)
        deferred=False
        def bounded_reader(**request):
            nonlocal deferred
            try:return reader(**request)
            except Exception:deferred=True;return None
        completed=score_origin(Path(ref['forecast_path']),previous=previous,reader=bounded_reader,clock=clock,guard=check,forecast_runtime=fr,outcome_runtime=runtime)
        if completed['output']['cohort_id']!=cohort_id:raise ValueError('sampled original solar cohort differs')
        from household_cycle import _retain_original
        ref['score_path']=str(_retain_original(store,completed,SCORE_SUFFIX,MAX_BYTES));ref['retry_after']=(utc(clock())+timedelta(minutes=10)).isoformat() if deferred else None
        scores=[s for s in scores if s['inputs']['forecast_receipt_sha256']!=ref['forecast_receipt_sha256']]+[completed]
        endpoints={s['inputs']['forecast_receipt_sha256']:s['inputs']['endpoint_sources'] for s in scores}
        pending=[]
        for r in samples.values():
            check()
            if r['cohort_id']!=cohort_id:continue
            for h in HORIZONS:
                if str(h) in endpoints.get(r['forecast_receipt_sha256'],{}):continue
                at=instant(r['issued_at'])+timedelta(hours=h,minutes=5)
                pending.append(max(at,instant(r['retry_after'])) if r['retry_after'] is not None else at)

    check()
    if energy_outcome_runtime_manifest()!=runtime or forecast_runtime_manifest()!=fr:raise ValueError('solar outcome runtime changed')
    report=build_energy_performance(scores,cohort=cohort,generated_at=clock(),next_mature_at=min(pending,default=None))
    publish_owned(index_path,dict(schema=INDEX,samples=samples),guard=check,maximum=262144)
    publish_owned(root/'energy-performance.json',report,guard=check)
    return dict(status='solar_storage_performance_refreshed',count=sum(row['count'] for row in report['by_horizon'].values()),report_sha256=report['report_sha256'],automatic_actuation=False)
