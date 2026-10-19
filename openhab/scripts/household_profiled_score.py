"""Scheduled bounded load/storage outcomes with immutable originals and samples."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from hashlib import sha256
from io import BytesIO
import gzip,os,time
from household.codec import canonical,loads,identity
from household.evidence import utc,digest
from household.control_contracts import instant
from household_observation import _directory,_private_file
from household_solar_score import read_forecast as read_energy,unchanged as energy_unchanged
from household_energy_forecast import forecast_runtime_manifest
from household_profiled_forecast import replay_profiled_forecast,profiled_runtime_manifest
from household_ac_load_artifact import runtime_manifest as load_runtime_manifest
from household_ac_load_store import _immutable
from household_profiled_outcomes import seal_profiled_outcomes,validate_score,cohort_for_profiled,outcome_runtime_manifest,MAX_BYTES,HORIZONS
from household_profiled_samples import summarize_verified_score,validate_sample,build_performance
from household_profiled_state import publish_owned,INDEX

SUFFIX='.household-profiled-energy-v1.json'
RAW_SUFFIX='.profiled-energy-outcome-v1.json.gz'
SAMPLE_SUFFIX='.profiled-energy-sample-v1.json'
REF_FIELDS={'forecast_path','forecast_sha256','forecast_receipt_sha256','issued_at','cohort_id','sample_sha256','score_file_sha256','retry_after'}


def producer_runtime():
    return outcome_runtime_manifest()


def read_forecast(path):
    path=Path(path);raw=_private_file(path,262144);value=loads(raw[0])
    if path.name!=sha256(raw[0]).hexdigest()+SUFFIX:raise ValueError('original profiled forecast filename differs')
    pin=digest(value['inputs']['original_energy_document_sha256']);energy,plan,original=read_energy(path.parent/(pin+'.household-energy-forecast-v1.json'))
    if value['inputs']['original_energy_receipt_sha256']!=energy['receipt_sha256']:raise ValueError('original profiled energy binding differs')
    return value,energy,plan,(path,raw,original)


def unchanged(original):
    path,raw,energy_original=original
    if _private_file(path,262144)!=raw:raise ValueError('original profiled forecast changed')
    energy_unchanged(energy_original)


def candidates(stages,*,now,guard):
    rows={};floor=now-timedelta(days=7)
    for stage in stages:
        directory=Path(stage)/'evidence';_directory(directory)
        with os.scandir(directory) as entries:
            for i,entry in enumerate(entries):
                guard()
                if i>=20000:raise ValueError('bounded original profile inventory required')
                if not entry.name.endswith(SUFFIX):continue
                if not entry.is_file(follow_symlinks=False):raise ValueError('regular profiled origin required')
                at=datetime.fromtimestamp(entry.stat(follow_symlinks=False).st_mtime,timezone.utc)
                if not floor<=at<=now:continue
                hour=at.replace(minute=0,second=0,microsecond=0);group=rows.setdefault(hour,[]);group.append((at,str(directory/entry.name)));group.sort()
                if len(group)>3:group[1:-2]=[]
    return [Path(path) for _,group in sorted(rows.items()) for _,path in group]


def _read_sample(store,ref):
    sample_pin=digest(ref['sample_sha256']);score_pin=digest(ref['score_file_sha256'])
    raw=_private_file(store/(sample_pin+SAMPLE_SUFFIX),32768)[0]
    if sha256(raw).hexdigest()!=sample_pin:raise ValueError('original verified profile sample bytes differ')
    sample=validate_sample(loads(raw))
    if sample['profiled_receipt_sha256']!=ref['forecast_receipt_sha256'] or sample['output']['cohort_id']!=ref['cohort_id'] or sample['output']['origin']['issued_at']!=ref['issued_at']:
        raise ValueError('original verified profile sample binding differs')
    if sha256(_private_file(store/(score_pin+RAW_SUFFIX),MAX_BYTES+65536)[0]).hexdigest()!=score_pin:raise ValueError('original full profile score bytes differ')
    return sample


def _read_full_score(store,ref,sample):
    raw=_private_file(store/(ref['score_file_sha256']+RAW_SUFFIX),MAX_BYTES+65536)[0]
    with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:expanded=stream.read(MAX_BYTES+1)
    if len(expanded)>MAX_BYTES or sha256(expanded).hexdigest()!=sample['score_document_sha256']:raise ValueError('original complete profile score differs')
    score=validate_score(loads(expanded))
    if score['receipt_sha256']!=sample['score_receipt_sha256']:raise ValueError('original complete profile score pin differs')
    return score


def run(*,stage,historical,guard,deadline,clock=lambda:datetime.now(timezone.utc),monotonic=time.monotonic,state_root=None,hour_reader=None,endpoint_reader=None):
    now=utc(clock());stop=min(deadline,monotonic()+15.)
    def check():
        guard()
        if monotonic()>=stop:raise TimeoutError('profiled outcome opportunity elapsed')
    check();runtime=producer_runtime();fr=profiled_runtime_manifest();er=forecast_runtime_manifest();lr=load_runtime_manifest()
    stages=[Path(stage)]+[Path(row['stage']) for row in historical]
    if len(stages)>64 or len(set(stages))!=len(stages):raise ValueError('bounded unique retained profiled stages required')
    paths=candidates(stages,now=now,guard=check);current=[p for p in paths if p.parent==Path(stage)/'evidence']
    cohort=None
    if current:
        latest=max(current,key=lambda p:p.stat().st_mtime);forecast,energy,plan,original=read_forecast(latest)
        replay_profiled_forecast(forecast,energy_receipt=energy,plan_receipt=plan,runtime_manifest=fr,energy_runtime_manifest=er,load_runtime_manifest={} if forecast['inputs']['load_source'] is None else lr)
        unchanged(original);check();cohort=cohort_for_profiled(forecast,energy,plan)
    root=Path(state_root) if state_root is not None else Path.home()/'.local/state/household-intel';_directory(root)
    store=root/'profiled-energy-outcomes';store.mkdir(mode=0o700,exist_ok=True);_directory(store);index_path=store/'samples.json'
    try:index=loads(_private_file(index_path,262144)[0])
    except FileNotFoundError:index=dict(schema=INDEX,samples={})
    if set(index)!={'schema','samples'} or index['schema']!=INDEX or not isinstance(index['samples'],dict) or len(index['samples'])>192:raise ValueError('bounded original profile sample index required')
    allowed={s/'evidence' for s in stages};refs={}
    for hour,ref in index['samples'].items():
        check();at=instant(hour)
        if at!=at.replace(minute=0,second=0,microsecond=0) or at>now:raise ValueError('original UTC profile sample hour required')
        if at<now-timedelta(days=7):continue
        if not isinstance(ref,dict) or set(ref)!=REF_FIELDS:raise ValueError('closed original profile sample reference required')
        path=Path(ref['forecast_path'])
        for k in ('forecast_sha256','forecast_receipt_sha256','cohort_id'):digest(ref[k])
        if path.parent not in allowed or path.name!=ref['forecast_sha256']+SUFFIX or instant(ref['issued_at']).replace(minute=0,second=0,microsecond=0)!=at:
            raise ValueError('owned original profile sample differs')
        if (ref['sample_sha256'] is None)!=(ref['score_file_sha256'] is None):raise ValueError('complete original profile score/sample pair required')
        if ref['retry_after'] is not None and not instant(ref['issued_at'])<=instant(ref['retry_after'])<=now+timedelta(minutes=30):raise ValueError('bounded profile source retry required')
        refs[hour]=ref
    # An unavailable newest origin does not revoke earlier issued predictions.
    if cohort is None:
        for ref in sorted(refs.values(),key=lambda r:r['issued_at'],reverse=True):
            check();saved,saved_energy,saved_plan,original=read_forecast(Path(ref['forecast_path']))
            if saved['runtime_manifest']!=fr or saved['load_runtime_manifest']!=lr or saved_energy['runtime_manifest']!=er:continue
            if saved['receipt_sha256']!=ref['forecast_receipt_sha256'] or sha256(original[1][0]).hexdigest()!=ref['forecast_sha256']:raise ValueError('original sampled profile forecast differs')
            replay_profiled_forecast(saved,energy_receipt=saved_energy,plan_receipt=saved_plan,runtime_manifest=fr,energy_runtime_manifest=er,load_runtime_manifest=lr)
            candidate=cohort_for_profiled(saved,saved_energy,saved_plan);unchanged(original)
            if candidate is not None:
                if identity(candidate)!=ref['cohort_id']:raise ValueError('original sampled profile cohort differs')
                cohort=candidate;break
    if cohort is None:
        for path in sorted(paths,key=lambda p:p.stat().st_mtime,reverse=True):
            check();saved,saved_energy,saved_plan,original=read_forecast(path)
            if saved['runtime_manifest']!=fr or saved['load_runtime_manifest']!=lr or saved_energy['runtime_manifest']!=er:continue
            replay_profiled_forecast(saved,energy_receipt=saved_energy,plan_receipt=saved_plan,runtime_manifest=fr,energy_runtime_manifest=er,load_runtime_manifest=lr)
            candidate=cohort_for_profiled(saved,saved_energy,saved_plan);unchanged(original)
            if candidate is not None:cohort=candidate;break
    if cohort is None:return dict(status='waiting',reason='current_load_profile_unavailable',automatic_actuation=False)
    cohort_id=identity(cohort)
    for path in paths:
        check();hint=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).replace(minute=0,second=0,microsecond=0).isoformat()
        if hint in refs:continue
        saved,saved_energy,saved_plan,original=read_forecast(path);issued=instant(saved['output']['issued_at']);hour=issued.replace(minute=0,second=0,microsecond=0).isoformat()
        if hour in refs or not now-timedelta(days=7)<=issued<=now or saved['runtime_manifest']!=fr or saved['load_runtime_manifest']!=lr or saved_energy['runtime_manifest']!=er:continue
        replay_profiled_forecast(saved,energy_receipt=saved_energy,plan_receipt=saved_plan,runtime_manifest=fr,energy_runtime_manifest=er,load_runtime_manifest=lr)
        if cohort_for_profiled(saved,saved_energy,saved_plan)!=cohort:continue
        unchanged(original)
        refs[hour]=dict(forecast_path=str(path),forecast_sha256=sha256(original[1][0]).hexdigest(),forecast_receipt_sha256=saved['receipt_sha256'],issued_at=issued.isoformat(),cohort_id=cohort_id,sample_sha256=None,score_file_sha256=None,retry_after=None)
        break
    samples=[];due=[]
    def pending_for(ref,sample):
        pins=({}, {}) if sample is None else (sample['hour_source_pins'],sample['endpoint_source_pins'])
        return [max(instant(ref['issued_at'])+timedelta(hours=h,minutes=5),instant(ref['retry_after'])) if ref['retry_after'] is not None else instant(ref['issued_at'])+timedelta(hours=h,minutes=5)
            for h in HORIZONS if str(h) not in pins[0] or str(h) not in pins[1]]
    by_hour={}
    for hour,ref in refs.items():
        check()
        sample=None if ref['sample_sha256'] is None else _read_sample(store,ref)
        if sample is not None:
            by_hour[hour]=sample
            if ref['cohort_id']==cohort_id:samples.append(sample)
        pending=pending_for(ref,sample)
        if pending and min(pending)<=now:due.append((min(pending),hour,ref,sample))
    selected=None
    for entry in sorted(due):
        check();_,hour,ref,previous_sample=entry;saved,saved_energy,saved_plan,original=read_forecast(Path(ref['forecast_path']))
        if saved['runtime_manifest']!=fr or saved['load_runtime_manifest']!=lr or saved_energy['runtime_manifest']!=er:continue
        selected=entry;break
    if selected is not None:
        if saved['receipt_sha256']!=ref['forecast_receipt_sha256'] or sha256(original[1][0]).hexdigest()!=ref['forecast_sha256']:raise ValueError('original sampled profile forecast differs')
        previous=None if previous_sample is None else _read_full_score(store,ref,previous_sample)
        hour_sources={} if previous is None else loads(canonical(previous['inputs']['hour_sources']))
        endpoints={} if previous is None else loads(canonical(previous['reference_score']['inputs']['endpoint_sources']))
        read_stop=stop-5.
        if hour_reader is None or endpoint_reader is None:
            from household_capture import _connection
            from household_ac_load_window import capture_hour
            from household_battery_source import fetch_endpoint
            connect=_connection(str(Path.home()/'.config/hex/energy-power-reader.jdbc'),'energy_power_reader')
            def remaining():
                check();value=min(4.,read_stop-monotonic(),stop-monotonic()-5.)
                if value<1:raise TimeoutError('profile source opportunity elapsed')
                return value
            if hour_reader is None:hour_reader=lambda **request:capture_hour(connect=connect,remaining=remaining,clock=clock,**request)
            if endpoint_reader is None:endpoint_reader=lambda **request:fetch_endpoint(lambda:connect(remaining=remaining),remaining=remaining,clock=clock,**request)
        deferred=False;attempts=0;issue=instant(ref['issued_at'])
        for h in HORIZONS:
            key=str(h);target=issue+timedelta(hours=h)
            if now<target+timedelta(minutes=5):continue
            for mapping,reader,request in ((hour_sources,hour_reader,dict(start=target-timedelta(hours=1),end=target)),(endpoints,endpoint_reader,dict(target_at=target))):
                if key in mapping:continue
                if attempts>=2 or stop-monotonic()<5.:break
                check();attempts+=1;read_stop=min(stop-5.,monotonic()+4.)
                try:value=reader(**request)
                except Exception:value=None;deferred=True
                if value is not None:mapping[key]=value
                else:deferred=True
                check()
        score=seal_profiled_outcomes(profiled_receipt=saved,energy_receipt=saved_energy,plan_receipt=saved_plan,hour_sources=hour_sources,endpoint_sources=endpoints,assessed_at=clock(),
            runtime_manifest=runtime,forecast_runtime_manifest=fr,energy_runtime_manifest=er,load_runtime_manifest=lr)
        if score['output']['cohort_id']!=ref['cohort_id']:raise ValueError('original sampled profile cohort differs')
        sample=summarize_verified_score(score,verified_at=clock());unchanged(original);check()
        compressed=gzip.compress(canonical(score),compresslevel=3,mtime=0);raw_pin=sha256(compressed).hexdigest();sample_raw=canonical(sample);sample_pin=sha256(sample_raw).hexdigest()
        _immutable(store/(raw_pin+RAW_SUFFIX),compressed);_immutable(store/(sample_pin+SAMPLE_SUFFIX),sample_raw)
        ref.update(sample_sha256=sample_pin,score_file_sha256=raw_pin,retry_after=(utc(clock())+timedelta(minutes=10)).isoformat() if deferred else None)
        by_hour[hour]=sample
        if ref['cohort_id']==cohort_id:samples=[s for s in samples if s['profiled_receipt_sha256']!=sample['profiled_receipt_sha256']]+[sample]
    pending=[at for hour,ref in refs.items() if ref['cohort_id']==cohort_id for at in pending_for(ref,by_hour.get(hour))]
    check()
    if producer_runtime()!=runtime or profiled_runtime_manifest()!=fr or forecast_runtime_manifest()!=er or load_runtime_manifest()!=lr:raise ValueError('profile score runtime changed')
    report=build_performance(samples,cohort=cohort,generated_at=clock(),next_mature_at=min(pending,default=None))
    publish_owned(index_path,dict(schema=INDEX,samples=refs),guard=check,maximum=262144)
    publish_owned(root/'profiled-energy-performance.json',report,guard=check)
    return dict(status='profiled_energy_performance_refreshed',count=sum(r['load']['count']+r['soc']['count'] for r in report['by_horizon'].values()),report_sha256=report['report_sha256'],automatic_actuation=False)
