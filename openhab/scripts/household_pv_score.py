"""One bounded captured-PV outcome opportunity; no fitting or forecast issuance."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
from io import BytesIO
import gzip,os,time,secrets
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc,digest
from household_observation import _private_file,_directory
from household_solar_score import candidates,read_forecast,unchanged
from household_solar_outcomes import cohort_for
from household_energy_forecast import replay_energy_forecast,forecast_runtime_manifest
from household_pv_outcomes import seal_pv_outcomes,replay_pv_outcomes,outcome_runtime_manifest,build_performance,MAX_BYTES,HORIZONS,_context
from household_pv_samples import summarize_verified_score,validate_sample,MAX_BYTES as SAMPLE_BYTES

INDEX='earthship-household-captured-pv-samples/v1'
RAW_SUFFIX='.captured-pv-outcome-v1.json.gz'
SAMPLE_SUFFIX='.captured-pv-verified-v1.json'
REF_FIELDS={'forecast_path','forecast_sha256','forecast_receipt_sha256','issued_at','cohort_id','score_file_sha256','sample_sha256','retry_after'}


def _atomic(path,raw,guard,maximum,*,immutable=False):
    if len(raw)>maximum:raise ValueError('bounded captured-PV publication required')
    directory=_directory(path.parent)
    try:previous=_private_file(path,maximum)
    except FileNotFoundError:previous=None
    if previous is not None:
        if immutable:
            if previous[0]!=raw:raise ValueError('immutable PV original already differs')
            return
        if loads(previous[0]).get('schema')!=loads(raw).get('schema'):raise ValueError('PV target belongs to another producer')
    temporary=path.with_name('.captured-pv-'+secrets.token_hex(16))
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        guard()
        try:current=_private_file(path,maximum)
        except FileNotFoundError:current=None
        if current!=previous or _directory(path.parent)!=directory:raise ValueError('PV publication context changed')
        os.replace(temporary,path)
        if _private_file(path,maximum)[0]!=raw:raise ValueError('PV publication readback differs')
    finally:temporary.unlink(missing_ok=True)


def _publish(path,value,guard,maximum):
    guard();_atomic(path,canonical(value),guard,maximum);guard()


def _sample(store,ref):
    pin=ref['sample_sha256'];digest(pin);path=store/(pin+SAMPLE_SUFFIX)
    raw=_private_file(path,SAMPLE_BYTES)[0];sample=validate_sample(loads(raw))
    if sample['sample_sha256']!=pin or sample['inputs']['energy_document_sha256']!=ref['forecast_sha256'] or sample['inputs']['energy_receipt_sha256']!=ref['forecast_receipt_sha256'] or sample['output']['cohort_id']!=ref['cohort_id']:
        raise ValueError('retained verified PV sample binding differs')
    # Verify retained compressed bytes without numerical replay. Raw originals
    # remain pinned while rolling reports use the checked compact admission.
    score_pin=ref['score_file_sha256'];digest(score_pin)
    if sha256(_private_file(store/(score_pin+RAW_SUFFIX),MAX_BYTES+65536)[0]).hexdigest()!=score_pin:raise ValueError('retained full PV score bytes differ')
    return sample


def _full(store,ref,sample):
    raw=_private_file(store/(ref['score_file_sha256']+RAW_SUFFIX),MAX_BYTES+65536)[0]
    with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:expanded=stream.read(MAX_BYTES+1)
    if len(expanded)>MAX_BYTES or sha256(expanded).hexdigest()!=sample['score_document_sha256']:raise ValueError('original full PV score differs')
    value=loads(expanded)
    if value['receipt_sha256']!=sample['score_receipt_sha256']:raise ValueError('original PV receipt pin differs')
    return value


def _profiled(path,energy,guard,pin=None):
    suffix='.household-profiled-energy-v1.json'
    if pin is not None:
        candidates_=[path.parent/(pin+suffix)]
    else:
        candidates_=[]
        with os.scandir(path.parent) as entries:
            for i,entry in enumerate(entries):
                guard()
                if i>=20000:raise ValueError('bounded profiled original inventory required')
                if entry.name.endswith(suffix):candidates_.append(Path(entry.path))
    matches=[]
    for candidate in candidates_:
        guard();raw,metadata=_private_file(candidate,262144);value=loads(raw)
        if sha256(raw).hexdigest()+suffix!=candidate.name:raise ValueError('profiled original filename differs')
        if value['inputs']['original_energy_document_sha256']==identity(energy):matches.append((value,candidate,(raw,metadata)))
    if len(matches)>1:raise ValueError('unique original profiled scenario required')
    if pin is not None and not matches:raise ValueError('original profiled scenario missing')
    return None if not matches else matches[0]


def run(*,stage,historical,guard,deadline,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,state_root=None,hour_reader=None):
    now=utc(clock());stop=min(deadline,monotonic()+15.)
    def check():
        guard()
        if monotonic()>=stop:raise TimeoutError('captured-PV scoring opportunity elapsed')
    check();runtime=outcome_runtime_manifest();er=forecast_runtime_manifest()
    stages=[Path(stage)]+[Path(row['stage']) for row in historical]
    if len(stages)>64 or len(set(stages))!=len(stages):raise ValueError('bounded unique original PV stages required')
    allowed={p/'evidence' for p in stages};current=candidates([Path(stage)],now=now,guard=check)
    if not current:return dict(status='waiting',reason='current_PV_origin_unavailable')
    energy,plan,original=read_forecast(max(current,key=lambda p:p.stat().st_mtime))
    replay_energy_forecast(energy,plan_receipt=plan,runtime_manifest=er);unchanged(original);check()
    cohort=_context(energy,plan,None)['cohort']
    if cohort is None:return dict(status='waiting',reason='captured_PV_scenario_or_reference_unavailable')
    cohort_id=identity(cohort);solar_cohort=identity(cohort_for(energy,plan))
    root=Path(state_root) if state_root is not None else Path.home()/'.local/state/household-intel';_directory(root)
    store=root/'captured-pv-outcomes';store.mkdir(mode=0o700,exist_ok=True);_directory(store)
    index_path=store/'samples.json'
    try:index=loads(_private_file(index_path,262144)[0])
    except FileNotFoundError:index=dict(schema=INDEX,samples={})
    if not isinstance(index,dict) or set(index)!={'schema','samples'} or index['schema']!=INDEX or not isinstance(index['samples'],dict) or len(index['samples'])>192:raise ValueError('bounded original PV index required')
    samples={}
    for hour,ref in index['samples'].items():
        check();at=instant(hour)
        if at!=at.replace(minute=0,second=0,microsecond=0) or at>now:raise ValueError('original UTC PV sample hour required')
        if at<now-timedelta(days=7):continue
        if not isinstance(ref,dict) or set(ref)!=REF_FIELDS:raise ValueError('closed original PV reference required')
        path=Path(ref['forecast_path'])
        for name in ('forecast_sha256','forecast_receipt_sha256','cohort_id'):digest(ref[name])
        if path.parent not in allowed or path.name!=ref['forecast_sha256']+'.household-energy-forecast-v1.json' or instant(ref['issued_at']).replace(minute=0,second=0,microsecond=0)!=at:raise ValueError('retained PV origin differs')
        if (ref['sample_sha256'] is None)!=(ref['score_file_sha256'] is None):raise ValueError('complete verified PV score pins required')
        if ref['retry_after'] is not None and not instant(ref['issued_at'])<=instant(ref['retry_after'])<=now+timedelta(minutes=30):raise ValueError('bounded PV source retry required')
        samples[hour]=ref
    # Reuse the original scorer's as-issued sample selection, never resample a
    # more favorable forecast after observing its outcome.
    try:solar_index=loads(_private_file(root/'energy-outcomes/samples.json',262144)[0])
    except FileNotFoundError:solar_index=dict(schema='earthship-household-solar-storage-samples/v1',samples={})
    if not isinstance(solar_index,dict) or set(solar_index)!={'schema','samples'} or solar_index['schema']!='earthship-household-solar-storage-samples/v1' or not isinstance(solar_index['samples'],dict) or len(solar_index['samples'])>192:raise ValueError('bounded original solar sample index required')
    for hour,ref in sorted(solar_index['samples'].items()):
        check();at=instant(hour)
        if at!=at.replace(minute=0,second=0,microsecond=0) or at>now:raise ValueError('original solar sample hour required')
        if not isinstance(ref,dict) or set(ref)!={'forecast_path','forecast_sha256','forecast_receipt_sha256','issued_at','cohort_id','score_path','retry_after'}:raise ValueError('closed original solar reference required')
        if at<now-timedelta(days=7) or hour in samples or ref['cohort_id']!=solar_cohort:continue
        for name in ('forecast_sha256','forecast_receipt_sha256','cohort_id'):digest(ref[name])
        path=Path(ref['forecast_path'])
        if path.parent not in allowed or path.name!=ref['forecast_sha256']+'.household-energy-forecast-v1.json' or instant(ref['issued_at']).replace(minute=0,second=0,microsecond=0)!=at:raise ValueError('original sampled PV target differs')
        # A solar/SoC cohort does not bind original controller availability or
        # its power-stream epoch. Check the exact chosen original before it can
        # enter this domain's due queue; never choose a replacement forecast.
        candidate,origin_plan,origin_files=read_forecast(path)
        if identity(candidate)!=ref['forecast_sha256'] or candidate['receipt_sha256']!=ref['forecast_receipt_sha256'] or candidate['output']['array_pv']['origin']!=ref['issued_at']:
            raise ValueError('original imported PV reference differs')
        captured_context=_context(candidate,origin_plan,None)['cohort']
        unchanged(origin_files);check()
        if captured_context is None or identity(captured_context)!=cohort_id:continue
        samples[hour]={k:ref[k] for k in ('forecast_path','forecast_sha256','forecast_receipt_sha256','issued_at')}
        samples[hour].update(cohort_id=cohort_id,score_file_sha256=None,sample_sha256=None,retry_after=None)
    verified=[];due=[];pending=[]
    for hour,ref in sorted(samples.items()):
        check()
        if ref['cohort_id']!=cohort_id:continue
        sample=None if ref['sample_sha256'] is None else _sample(store,ref)
        if sample is not None:
            if sample['runtime_sha256']!=identity(runtime):raise ValueError('original PV sample runtime differs')
            verified.append(sample)
        for h in HORIZONS:
            if sample is not None and str(h) in sample['hour_source_pins']:continue
            at=instant(ref['issued_at'])+timedelta(hours=h,minutes=5)
            if ref['retry_after'] is not None:at=max(at,instant(ref['retry_after']))
            pending.append(at)
            if at<=now:due.append((at,hour,h,ref,sample))
    if due:
        _,hour,h,ref,sample=min(due,key=lambda row:(row[0],row[1],row[2]));path=Path(ref['forecast_path'])
        energy,plan,original=read_forecast(path)
        if identity(energy)!=ref['forecast_sha256'] or energy['receipt_sha256']!=ref['forecast_receipt_sha256'] or energy['output']['array_pv']['origin']!=ref['issued_at'] or identity(_context(energy,plan,None)['cohort'])!=cohort_id:
            raise ValueError('original sampled energy context differs')
        previous=None if sample is None else _full(store,ref,sample)
        profile=None if previous is not None and previous['inputs']['profiled_document_sha256'] is None else _profiled(path,energy,check,pin=None if previous is None else previous['inputs']['profiled_document_sha256'])
        from household_profiled_forecast import profiled_runtime_manifest
        from household_ac_load_artifact import runtime_manifest as load_runtime
        profiled=None if profile is None else profile[0];pr=None if profile is None else profiled_runtime_manifest();lr=None if profile is None else ({} if profiled['inputs']['load_source'] is None else load_runtime())
        context=dict(energy_receipt=energy,plan_receipt=plan,profiled_receipt=profiled,runtime_manifest=runtime,energy_runtime_manifest=er,profiled_runtime_manifest=pr,load_runtime_manifest=lr)
        sources={}
        if previous is not None:
            replay_pv_outcomes(previous,**context);sources=loads(canonical(previous['inputs']['hour_sources']))
        end=instant(ref['issued_at'])+timedelta(hours=h);start=end-timedelta(hours=1)
        if hour_reader is None:
            from household_capture import _connection
            from household_pv_window import capture_hour
            connect=_connection(str(Path.home()/'.config/hex/energy-power-reader.jdbc'),'energy_power_reader')
            def remaining():
                check();left=min(15.,stop-monotonic())
                if left<1:raise TimeoutError('PV source collection deadline elapsed')
                return left
            hour_reader=lambda **request:capture_hour(connect=connect,clock=clock,remaining=remaining,policy_path=Path.home()/'Solar_PV/analytics/config/power-evidence.json',**request)
        deferred=False
        try:
            source=hour_reader(start=start,end=end);check()
        except Exception:
            check();source=None;deferred=True
        if source is not None:sources[str(h)]=source
        score=seal_pv_outcomes(**context,hour_sources=sources,assessed_at=clock());check();unchanged(original)
        if profile is not None and _private_file(profile[1],262144)!=profile[2]:raise ValueError('profiled original changed during scoring')
        compact=summarize_verified_score(score,verified_at=clock());encoded=gzip.compress(canonical(score),mtime=0);score_pin=sha256(encoded).hexdigest()
        _atomic(store/(score_pin+RAW_SUFFIX),encoded,check,MAX_BYTES+65536,immutable=True);check()
        _atomic(store/(compact['sample_sha256']+SAMPLE_SUFFIX),canonical(compact),check,SAMPLE_BYTES,immutable=True);check()
        ref.update(score_file_sha256=score_pin,sample_sha256=compact['sample_sha256'],retry_after=(utc(clock())+timedelta(minutes=10)).isoformat() if deferred else None)
        verified=[s for s in verified if s['inputs']['energy_document_sha256']!=ref['forecast_sha256']]+[compact]
    completed={s['inputs']['energy_document_sha256']:s['hour_source_pins'] for s in verified};pending=[]
    for ref in samples.values():
        check()
        if ref['cohort_id']!=cohort_id:continue
        for h in HORIZONS:
            if str(h) in completed.get(ref['forecast_sha256'],{}):continue
            at=instant(ref['issued_at'])+timedelta(hours=h,minutes=5)
            if ref['retry_after'] is not None:at=max(at,instant(ref['retry_after']))
            pending.append(at)
    check();report=build_performance(verified,cohort=cohort,generated_at=clock(),next_mature_at=min(pending,default=None))
    if outcome_runtime_manifest()!=runtime or forecast_runtime_manifest()!=er:raise ValueError('PV producer runtime changed')
    _publish(index_path,dict(schema=INDEX,samples=samples),check,262144)
    _publish(root/'captured-pv-performance.json',report,check,32768)
    return dict(status='captured_pv_performance_refreshed',count=sum(r['models']['constant_load_pv']['count'] for r in report['by_horizon'].values()),report_sha256=report['report_sha256'],automatic_actuation=False)
