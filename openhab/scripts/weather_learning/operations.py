"""Private operational projections. No cloud queries, fitting or serving authority."""
from datetime import timedelta
from pathlib import Path
import json,logging,os,stat,tempfile
from .contracts import canonical,identity,instant,digest
from .capabilities import enabled_profiles
from .shadow import _read
from household_job_budget import AdmissionDeferred

MAX_BYTES=128*1024
INGEST_SCHEMA='earthship-weathernext-ingest-operations/v1'
OPS_SCHEMA='earthship-weathernext-operations/v1'


def ingestion_diagnostic(archive,result,*,profiles,now):
    now=instant(now.isoformat());snapshot=None
    if result.get('status')=='ARCHIVED':snapshot=archive.read(digest(result['snapshot_sha256']))
    available=None if snapshot is None else instant(snapshot['ingestion_completed_at'])
    initialized=None if snapshot is None else instant(snapshot['initialized_at'])
    if available is not None and available>now:raise ValueError('future operational original refused')
    budget=result.get('acquisition_budget',{})
    groups=[{k:g.get(k) for k in ('profile','profile_sha256','horizon','initialized_at','snapshot_sha256','status','reason','retry_at','available_at','normalized','consumed')} for g in result.get('capabilities',[])]
    if len(groups)>6:raise ValueError('bounded declared optional groups required')
    value=dict(schema=INGEST_SCHEMA,generated_at=now.isoformat(),valid_until=(now+timedelta(hours=2)).isoformat(),
        status=result['status'],reason=result.get('reason'),provider='weathernext3',provider_revision=None,
        provider_revision_status='not_exposed_by_retained_native_contract',
        run_id=None if snapshot is None else snapshot['run_id'],
        collections=[] if snapshot is None else sorted({s['collection'] for s in snapshot['source_originals']}),
        source_sha256=None if snapshot is None else result['snapshot_sha256'],
        initialized_at=None if initialized is None else initialized.isoformat(),
        source_available_at=None if available is None else available.isoformat(),
        original_ingestion_lag_seconds=None if available is None else (available-initialized).total_seconds(),
        source_age_seconds=None if available is None else (now-available).total_seconds(),
        enabled_groups=[p.name for p in enabled_profiles(profiles)],optional_groups=groups,
        accounting=dict(requests=result.get('requests',budget.get('requests_used')),response_bytes=result.get('bytes_received',budget.get('response_bytes_used')),
            collection_wall_seconds=result.get('elapsed_seconds'),peak_rss_kib=result.get('peak_rss_kib'),
            request_basis='counted_transport_and_sdk_query_boundaries_not_eecu',limits={k:budget.get(k) for k in ('maximum_requests','maximum_response_bytes','maximum_seconds')}),
        archive_capacity=result.get('archive_capacity'),eecu_used=None,eecu_remaining=None,eecu_status='not_observable',
        paid_access_allowed=False,requester_billing_project=None,full_ensemble_allowed=False,automatic_actuation=False)
    value['report_sha256']=identity(value)
    if len(canonical(value))>MAX_BYTES:raise ValueError('bounded private ingest diagnostic required')
    return value


def _write_private(path,value):
    raw=canonical(value);path=Path(path)
    if len(raw)>MAX_BYTES:raise ValueError('bounded private operational report required')
    parent=path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.getuid() or parent.st_mode&0o077:raise ValueError('private operational directory required')
    if path.exists() or path.is_symlink():
        prior=path.lstat()
        if not stat.S_ISREG(prior.st_mode) or prior.st_uid!=os.getuid() or prior.st_mode&0o077:raise ValueError('private operational file required')
    fd,name=tempfile.mkstemp(prefix='.operations-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as output:output.write(raw);output.flush();os.fsync(output.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if os.path.exists(name):os.unlink(name)


def persist_ingestion(archive,result,*,profiles,now):
    try:_write_private(archive.root/'ingest-status.json',ingestion_diagnostic(archive,result,profiles=profiles,now=now));return True
    except (TimeoutError,AdmissionDeferred,MemoryError):raise
    except (OSError,ValueError,KeyError,TypeError):
        logging.getLogger(__name__).warning('Private ingestion diagnostics unavailable; acquisition outcome retained')
        return False


def _document(path,now,limit=MAX_BYTES,*,expected_schema=INGEST_SCHEMA):
    try:
        value=_read(path,limit)
        if expected_schema is None:
            if 'schema' in value or value.get('status') not in ('applied','preview'):raise ValueError('known refresh diagnostic required')
        elif value.get('schema')!=expected_schema:raise ValueError('known original diagnostic schema required')
        for key in ('pending','expired','prepared_not_confirmed','completed_scores','total_retained_scores','scored'):
            if key in value and (type(value[key]) is not int or value[key]<0):raise ValueError('nonnegative original work count required')
        generated,until=map(instant,(value['generated_at'],value['valid_until']))
        if not generated<=now or not generated<until<=generated+timedelta(hours=2):raise ValueError('bounded original report clocks required')
        if value.get('automatic_actuation') is not False:raise ValueError('read-only original diagnostic required')
        name=identity(value)
        if value.get('schema')==INGEST_SCHEMA and value.get('report_sha256')!=identity({k:v for k,v in value.items() if k!='report_sha256'}):raise ValueError('ingest diagnostic seal differs')
        return dict(status='current' if now<until else 'stale',generated_at=generated.isoformat(),valid_until=until.isoformat(),original_sha256=name,value=value)
    except (TimeoutError,AdmissionDeferred,MemoryError):raise
    except (OSError,ValueError,KeyError,TypeError):return dict(status='unavailable',original_sha256=None,value=None)


def _selection(state,*,now,sensor_epoch,guard):
    from .provenance import issue_provenance
    from .historical_serving import load_selection
    result={}
    try:
        guard();receipt=state.current_model();guard()
        if receipt is None:result['native_temperature']=dict(status='not_selected',model_sha256=None,procedure=None)
        else:
            p=issue_provenance(receipt['model'],training_policy=receipt.get('training_policy'),selection_original_sha256=identity(receipt))
            result['native_temperature']=dict(status='validated_configuration_not_serving_admission',model_sha256=receipt['model']['artifact_sha256'],selection_original_sha256=identity(receipt),
                procedure={k:p[k] for k in ('method_policy_sha256','training_policy_sha256','selection_policy_sha256')})
    except (TimeoutError,AdmissionDeferred,MemoryError):raise
    except (OSError,ValueError,KeyError,TypeError):result['native_temperature']=dict(status='unavailable',model_sha256=None,procedure=None)
    for name,filename,kind,epoch in [('historical_temperature','historical-outdoor.json','outdoor_temperature_c',sensor_epoch),('historical_wind','historical-wind.json','wind_m_s',None)]:
        path=state.root/filename
        if not path.exists():result[name]=dict(status='not_selected',model_sha256=None,procedure=None);continue
        try:
            guard();model,selection=load_selection(path,kind=kind,now=now,sensor_epoch=epoch);guard()
            p=issue_provenance(model,historical=True,selection_original_sha256=selection['selection_sha256'])
            result[name]=dict(status='validated_configuration_not_serving_admission',model_sha256=selection['model_sha256'],selection_original_sha256=selection['selection_sha256'],
                experiment_receipt_sha256=selection['experiment_receipt_sha256'],procedure={k:p[k] for k in ('method_policy_sha256','training_policy_sha256','selection_policy_sha256')})
        except (TimeoutError,AdmissionDeferred,MemoryError):raise
        except (OSError,ValueError,KeyError,TypeError):result[name]=dict(status='unavailable',model_sha256=None,procedure=None)
    return result


def monitor_diagnostic(archive,state,performance,*,now,sensor_epoch,guard,accounting=None):
    now=instant(now.isoformat());guard()
    ingest=_document(archive.root/'ingest-status.json',now) if archive is not None else dict(status='unavailable',value=None)
    corrections=performance.get('corrections') or {}
    evaluation=dict(source_report_sha256=performance['report_sha256'],generated_at=performance['generated_at'],
        temperature_states=performance['temperature']['work']['states'],temperature_backlog=performance['temperature']['work']['backlog'],
        pending_daily_windows=performance['pending'],rain_intervals=performance.get('rain_intervals'),
        correction_states=corrections.get('states'),correction_backlog=corrections.get('known_work_backlog'),
        correction_coverage=corrections.get('projection_coverage'),
        artifact_cohorts=corrections.get('cohorts',[])[:16],procedure_cohorts=corrections.get('policy_cohorts',[])[:16],
        cohort_projection=dict(artifact_total=len(corrections.get('cohorts',[])),procedure_total=len(corrections.get('policy_cohorts',[])),maximum_included_per_kind=16),
        observation_accounting=accounting,source_withheld=performance['source_withheld'])
    auxiliary={}
    for kind,filename in [('capability','capability-performance.json'),('refresh','refresh-performance.json'),('marginal','marginal-performance.json'),('rain','rain-performance.json')]:
        guard();original=_document(state.root/filename,now,512*1024,expected_schema=None if kind=='refresh' else {'capability':'earthship-capability-performance/v1','marginal':'earthship-marginal-performance/v1','rain':'earthship-rain-performance/v1'}[kind]);value=original.pop('value')
        original['counts']=None if value is None else {k:value[k] for k in ('scope_sha256','pending','expired','prepared_not_confirmed','completed_scores','total_retained_scores','scored','withheld','capacity','database','summary_truncated') if k in value}
        auxiliary[kind]=original
    result=dict(schema=OPS_SCHEMA,generated_at=now.isoformat(),valid_until=(now+timedelta(hours=2)).isoformat(),
        ingestion=ingest,evaluation=evaluation,auxiliary_scores=auxiliary,
        selected_models=_selection(state,now=now,sensor_epoch=sensor_epoch,guard=guard),
        selection_basis='validated_configurations_and_original_scoring_cohorts_not_proof_of_effective_serving',
        counts_are_not_pooled_across_scopes=True,release_authorized=False,automatic_actuation=False)
    result['report_sha256']=identity(result)
    if len(canonical(result))>MAX_BYTES:raise ValueError('bounded operational projection required; detailed originals retained')
    guard();return result


def persist_monitor(archive,state,performance,*,now,sensor_epoch,guard,accounting=None):
    try:
        result=monitor_diagnostic(archive,state,performance,now=now,sensor_epoch=sensor_epoch,guard=guard,accounting=accounting)
        state._write(state.root/'operations.json',result);return True
    except (TimeoutError,AdmissionDeferred,MemoryError):raise
    except (OSError,ValueError,KeyError,TypeError):
        logging.getLogger(__name__).warning('Private operational projection unavailable; original performance retained')
        return False
