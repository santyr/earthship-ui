"""Scheduled conditional battery outcomes; no actuator transport or fitting."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import os,secrets,time
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc,digest
from household.battery_outcomes import seal_battery_outcomes,build_performance,_score_record,HORIZONS,MAX_SCORE_BYTES,_cohort
from household_observation import _private_file,_directory
from household_outcomes import original_plan_runtime
from household_pipeline import thermal_execution_runtime
from household_battery_outcomes import battery_runtime_manifest

SUFFIX='.household-model-plan-v6.json'
SCORE_SUFFIX='.battery-outcome-v1.json'
INDEX_SCHEMA='earthship-household-battery-sample-index/v1'
REPORT_SCHEMA='earthship-household-battery-performance/v1'


class EndpointDeferred(Exception):pass


def read_plan(path):
    path=Path(path);raw,metadata=_private_file(path,2097152)
    if path.name!=sha256(raw).hexdigest()+SUFFIX:raise ValueError('original battery plan filename differs')
    plan=loads(raw)
    if plan.get('schema') not in ('earthship-household-model-plan-receipt/v6','earthship-household-model-plan-receipt/v7'):raise ValueError('original battery projection version required')
    return plan,(raw,metadata)


def replay_compatible(plan,*,runtime):
    try:original_plan_runtime(plan,actual=runtime)
    except ValueError:return False
    return True


def score_origin(path,*,previous,reader,clock,guard,runtime,thermal_runtime=None):
    guard();plan,original=read_plan(path);expected=original_plan_runtime(plan,actual=runtime)
    thermal=thermal_runtime if thermal_runtime is not None else thermal_execution_runtime(Path(__file__).resolve().parent,plan['inputs']['thermal_inputs'])
    sources={}
    if previous is not None:
        _score_record(previous)
        if previous['inputs']['plan_receipt_sha256']!=plan['receipt_sha256'] or previous['inputs']['plan_document_sha256']!=sha256(canonical(plan)).hexdigest():raise ValueError('previous score origin differs')
        sources=loads(canonical(previous['inputs']['endpoint_sources']))
    issue=instant(plan['inputs']['snapshot']['as_of']);now=utc(clock())
    if previous is not None and instant(previous['inputs']['assessed_at'])>now:raise ValueError('battery assessment clock regressed')
    if plan['output']['projections']['energy_persistence']['status']=='projected_nominal_baseline':
        for hours in HORIZONS:
            target=issue+timedelta(hours=hours);key=str(hours)
            if hours<=plan['inputs']['config']['horizon_hours'] and now>=target+timedelta(minutes=5) and key not in sources:
                guard()
                try:sources[key]=reader(target_at=target)
                except EndpointDeferred:break
                guard()
    guard();result=seal_battery_outcomes(plan_receipt=plan,endpoint_sources=sources,assessed_at=clock(),plan_runtime_manifest=expected,
        outcome_runtime_manifest=runtime,thermal_runtime=thermal)
    if _private_file(Path(path),2097152)!=original:raise ValueError('battery origin changed')
    guard();return result


def publish(path,value,*,guard):
    """Replace only an owned artifact of this exact schema under the score lock."""
    path=Path(path);directory=_directory(path.parent);encoded=canonical(value)
    if len(encoded)>262144 or value.get('schema') not in (INDEX_SCHEMA,REPORT_SCHEMA):raise ValueError('bounded battery publication required')
    try:previous=_private_file(path,262144)
    except FileNotFoundError:previous=None
    if previous is not None and loads(previous[0]).get('schema')!=value['schema']:raise ValueError('battery target belongs to another producer')
    temporary=path.parent/('.battery-'+secrets.token_hex(16))
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(encoded);stream.flush();os.fsync(stream.fileno())
        guard()
        try:current=_private_file(path,262144)
        except FileNotFoundError:current=None
        if current!=previous or _directory(path.parent)!=directory:raise ValueError('battery publication context changed')
        os.replace(temporary,path)
        if _private_file(path,262144)[0]!=encoded:raise ValueError('battery publication readback differs')
    finally:
        try:temporary.unlink()
        except FileNotFoundError:pass


def retain(directory,score,*,guard):
    from household_cycle import _retain_original
    guard();return _retain_original(directory,score,SCORE_SUFFIX,MAX_SCORE_BYTES)


def _score(path):
    raw,_=_private_file(path,MAX_SCORE_BYTES)
    if path.name!=sha256(raw).hexdigest()+SCORE_SUFFIX:raise ValueError('original battery score filename differs')
    return _score_record(loads(raw))


def candidates(stages,*,now,guard):
    """Metadata is a bounded selection hint; decoded originals prove issue time."""
    groups={};cutoff=now-timedelta(days=7)
    for stage in stages:
        directory=Path(stage)/'evidence';_directory(directory)
        with os.scandir(directory) as entries:
            for count,entry in enumerate(entries):
                if count>=20000:raise ValueError('bounded battery evidence inventory required')
                if not entry.name.endswith(SUFFIX):continue
                guard();info=entry.stat(follow_symlinks=False)
                at=datetime.fromtimestamp(info.st_mtime,timezone.utc)
                if cutoff<=at<=now:
                    hour=at.replace(minute=0,second=0,microsecond=0).isoformat()
                    group=groups.setdefault(hour,[]);group.append((info.st_mtime,str(Path(directory)/entry.name)))
                    group.sort()
                    if len(group)>3:group[1:-2]=[]
    return [Path(path) for hour,rows in sorted(groups.items()) for _,path in rows]


def run(*,stage,historical,guard,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,
        deadline,state_root=None,reader=None):
    """One original per UTC hour; at most one mature origin per normal slot."""
    now=utc(clock());budget=min(deadline,monotonic()+20.);stages=[Path(stage)]+[Path(ref['stage']) for ref in historical]
    def check():
        guard()
        if monotonic()>=budget:raise TimeoutError('battery score budget elapsed')
    check();runtime=battery_runtime_manifest()
    root=Path(state_root) if state_root is not None else Path.home()/'.local/state/household-intel'
    _directory(root);store=root/'battery-outcomes'
    try:store.mkdir(mode=0o700)
    except FileExistsError:pass
    _directory(store);index_path=store/'samples.json'
    try:index=loads(_private_file(index_path,262144)[0])
    except FileNotFoundError:index=dict(schema=INDEX_SCHEMA,samples={})
    if not isinstance(index,dict) or set(index)!={'schema','samples'} or index['schema']!=INDEX_SCHEMA or not isinstance(index['samples'],dict) or len(index['samples'])>192:raise ValueError('bounded original battery sample index required')
    paths=candidates(stages,now=now,guard=check)
    if not paths:return dict(status='waiting',reason='battery_origin_unavailable')
    # Choose the latest current-stage origin for the active physical/model cohort.
    latest=max((p for p in paths if p.parent==Path(stage)/'evidence'),key=lambda p:p.stat().st_mtime,default=None)
    if latest is None:return dict(status='waiting',reason='current_battery_origin_unavailable')
    current,_=read_plan(latest);projection=current['output']['projections']['energy_persistence']
    if projection['status']!='projected_nominal_baseline':return dict(status='waiting',reason='current_battery_baseline_unavailable')
    # Source closure and full numerical replay happen for every newly sampled origin.
    from household.pipeline import replay_pipeline
    expected=original_plan_runtime(current,actual=runtime)
    replay_pipeline(current,runtime_manifest=expected,thermal_runtime=thermal_execution_runtime(Path(__file__).resolve().parent,current['inputs']['thermal_inputs']))
    check();cohort=_cohort(current,projection);cohort_id=identity(cohort);samples={}
    allowed={p/'evidence' for p in stages}
    for hour,ref in index['samples'].items():
        issued=instant(hour)
        if issued!=issued.replace(minute=0,second=0,microsecond=0) or issued>now:raise ValueError('original hourly sample key required')
        if issued<now-timedelta(days=7):continue
        if not isinstance(ref,dict) or set(ref)!={'plan_path','plan_sha256','plan_receipt_sha256','issued_at','cohort_id','score_path','retry_after'}:raise ValueError('closed original battery reference required')
        path=Path(ref['plan_path']);digest(ref['plan_sha256']);digest(ref['plan_receipt_sha256']);digest(ref['cohort_id'])
        if path.parent not in allowed or path.name!=ref['plan_sha256']+SUFFIX:raise ValueError('explicit retained battery origin required')
        if instant(ref['issued_at']).replace(minute=0,second=0,microsecond=0)!=issued:raise ValueError('hourly sample binding differs')
        if ref['score_path'] is not None and Path(ref['score_path']).parent!=store:raise ValueError('owned compact score required')
        if ref['retry_after'] is not None and not instant(ref['issued_at'])<=instant(ref['retry_after'])<=now+timedelta(minutes=30):raise ValueError('bounded endpoint retry required')
        samples[hour]=ref
    # Add one previously unsampled original, oldest first. Existing choices never change.
    for path in paths:
        check();hint=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).replace(minute=0,second=0,microsecond=0).isoformat()
        if hint in samples:continue
        plan,original=read_plan(path);issued=instant(plan['inputs']['snapshot']['as_of']);hour=issued.replace(minute=0,second=0,microsecond=0).isoformat()
        if hour in samples or issued>now or issued<now-timedelta(days=7):continue
        if not replay_compatible(plan,runtime=runtime):continue
        value=plan['output']['projections']['energy_persistence']
        if value['status']!='projected_nominal_baseline':continue
        candidate_cohort=_cohort(plan,value)
        if identity(candidate_cohort)!=cohort_id:continue
        previous=score_origin(path,previous=None,reader=lambda **kw:None,clock=clock,guard=check,runtime=runtime) if now<issued+timedelta(hours=1,minutes=5) else None
        # A mature sample is verified below before its reference is committed.
        samples[hour]=dict(plan_path=str(path),plan_sha256=sha256(original[0]).hexdigest(),plan_receipt_sha256=plan['receipt_sha256'],issued_at=issued.isoformat(),cohort_id=cohort_id,score_path=None,retry_after=None)
        if previous is not None:samples[hour]['score_path']=str(retain(store,previous,guard=check))
        break
    scores=[];pending=[];due=[]
    for hour,ref in sorted(samples.items()):
        check()
        if ref['cohort_id']!=cohort_id:continue
        previous=None if ref['score_path'] is None else _score(Path(ref['score_path']))
        if previous is not None:
            if previous['inputs']['plan_receipt_sha256']!=ref['plan_receipt_sha256'] or previous['inputs']['plan_document_sha256']!=ref['plan_sha256'] or previous['output']['cohort_id']!=cohort_id:raise ValueError('retained score original binding differs')
            scores.append(previous)
        issue=instant(ref['issued_at']);mature=[]
        for hours in (HORIZONS if previous is None else map(int,previous['output']['by_horizon'])):
            if previous is not None and str(hours) in previous['inputs']['endpoint_sources']:continue
            at=issue+timedelta(hours=hours,minutes=5)
            if ref['retry_after'] is not None:at=max(at,instant(ref['retry_after']))
            pending.append(at)
            if at<=now:mature.append(at)
        if mature:
            plan,_=read_plan(Path(ref['plan_path']));check()
            if replay_compatible(plan,runtime=runtime):due.append((min(mature),hour,ref,previous))
    if due:
        _,hour,ref,previous=min(due)
        if reader is None:
            from household_capture import _connection
            from household_battery_source import fetch_endpoint
            connect=_connection(str(Path.home()/'.config/hex/energy-power-reader.jdbc'),'energy_power_reader')
            def remaining():
                check();value=min(15.,budget-monotonic())
                if value<1:raise TimeoutError('battery endpoint connection budget elapsed')
                return value
            reader=lambda **request:fetch_endpoint(lambda:connect(remaining=remaining),remaining=remaining,clock=clock,**request)
        def bounded_reader(**request):
            try:return reader(**request)
            except Exception:raise EndpointDeferred() from None
        try:
            completed=score_origin(Path(ref['plan_path']),previous=previous,reader=bounded_reader,clock=clock,guard=check,runtime=runtime)
        except EndpointDeferred:
            ref['retry_after']=(utc(clock())+timedelta(minutes=30)).isoformat()
        else:
            if completed['output']['cohort_id']!=cohort_id:raise ValueError('sampled current battery cohort differs')
            ref['score_path']=str(retain(store,completed,guard=check))
            ref['retry_after']=(utc(clock())+timedelta(minutes=30)).isoformat() if any(r['status']=='pending_source' for r in completed['output']['by_horizon'].values()) else None
            scores=[v for v in scores if v['inputs']['plan_receipt_sha256']!=ref['plan_receipt_sha256']]+[completed]
        pending=[]
        for r in samples.values():
            if r['cohort_id']!=cohort_id:continue
            check();saved=None if r['score_path'] is None else _score(Path(r['score_path']))
            for h in (HORIZONS if saved is None else map(int,saved['output']['by_horizon'])):
                if saved is None or str(h) not in saved['inputs']['endpoint_sources']:
                    at=instant(r['issued_at'])+timedelta(hours=h,minutes=5)
                    pending.append(max(at,instant(r['retry_after'])) if r['retry_after'] is not None else at)
    check()
    if battery_runtime_manifest()!=runtime:raise ValueError('battery scoring runtime changed')
    publish(index_path,dict(schema=INDEX_SCHEMA,samples=samples),guard=check)
    report=build_performance(scores,cohort=cohort,generated_at=clock(),next_mature_at=min(pending,default=None))
    publish(root/'battery-performance.json',report,guard=check)
    return dict(status='battery_performance_refreshed',count=sum(row['count'] for row in report['by_horizon'].values()),report_sha256=report['report_sha256'],automatic_actuation=False)
