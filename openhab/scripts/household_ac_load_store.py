"""Private original-day storage and compact serving admission for daily loads.

Only refresh_profile builds hourly source accounting. Serving freshly checks the
admitted original file bytes and runtime, then replays the compact hourly model.
"""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from io import BytesIO
import gzip,os,secrets
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from household.evidence import utc,digest
from household_observation import _directory,_private_file,_move_no_replace
from household_ac_load_artifact import build_artifact,verify_compact,runtime_manifest,FIELDS as ARTIFACT_FIELDS,SCHEMA as ARTIFACT_SCHEMA
from household_ac_load_sources import replay_day_source,MAX_DAY_BYTES
from household_ac_load_transport import capture_day
from household_ac_load_model import _zone,POLICY

AC_LOAD_ROOT=Path('/home/sat/.local/state/thermal-intel/native-daily/ac-load')
ENERGY_READER_CONFIG=Path('/home/sat/.config/hex/energy-power-reader.jdbc')
SOURCE_SCHEMA='earthship-ac-load-admitted-source/v1'
ADMISSION_SCHEMA='earthship-ac-load-admission/v1'
CURRENT_SCHEMA='earthship-ac-load-current/v1'


class LoadRuntimeRevalidationRequired(ValueError):
    def __init__(self,sources):
        super().__init__('original load runtime changed; scheduled revalidation required')
        self.sources=tuple((r['name'],r['file_sha256'],r['source_sha256']) for r in sources)



def _json(root,name,maximum=262144):
    raw=_private_file(root/name,maximum)[0];value=loads(raw)
    if canonical(value)!=raw:raise ValueError('exact canonical original load file required')
    return raw,value


def _immutable(path,raw):
    try:current=_private_file(path,len(raw))[0]
    except FileNotFoundError:current=None
    if current is not None:
        if current!=raw:raise ValueError('immutable load original already differs')
        return
    temporary=path.with_name('.load-original-'+secrets.token_hex(16))
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        directory_fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            try:_move_no_replace(directory_fd,temporary.name,path.name)
            except FileExistsError:
                if _private_file(path,len(raw))[0]!=raw:raise ValueError('immutable load original already differs')
            os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:temporary.unlink(missing_ok=True)


def _read_day(path):
    raw=_private_file(path,MAX_DAY_BYTES)[0]
    with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:expanded=stream.read(MAX_DAY_BYTES+1)
    if len(expanded)>MAX_DAY_BYTES:raise ValueError('bounded original load day required')
    value=loads(expanded)
    if canonical(value)!=expanded:raise ValueError('canonical original day required')
    return replay_day_source(value),raw


def _verify_files(root,admission,artifact,guard):
    if len(admission['sources'])!=14 or len(artifact['days'])!=14:raise ValueError('complete admitted source set required')
    for ref,day in zip(admission['sources'],artifact['days']):
        guard();expected=instant(day['window_start']).astimezone(_zone('America/Denver')).date().isoformat()+'.ac-day.json.gz'
        if (not isinstance(ref,dict) or set(ref)!={'name','file_sha256','source_sha256'} or ref['name']!=expected or
            ref['source_sha256']!=day['source_sha256'] or sha256(_private_file(root/expected,MAX_DAY_BYTES)[0]).hexdigest()!=digest(ref['file_sha256'])):
            raise ValueError('admitted original load file differs')


def read_current(root,*,assessed_at,guard):
    root=Path(root);_directory(root);at=utc(assessed_at);guard()
    raw,pointer=_json(root,'current.json',8192)
    if not isinstance(pointer,dict) or set(pointer)!={'schema','admission_name','admission_sha256','artifact_sha256'} or pointer['schema']!=CURRENT_SCHEMA:
        raise ValueError('owned current load admission required')
    pin=digest(pointer['admission_sha256']);artifact_pin=digest(pointer['artifact_sha256'])
    name=pin+'.load-admission.json'
    if pointer['admission_name']!=name:raise ValueError('content-addressed admission required')
    admission_raw,admission=_json(root,name)
    fields={'schema','verified_at','artifact','runtime_sha256','sources','admission_sha256'}
    if (set(admission)!=fields or admission['schema']!=ADMISSION_SCHEMA or admission['admission_sha256']!=pin or
        identity({k:v for k,v in admission.items() if k!='admission_sha256'})!=pin or instant(admission['verified_at'])>at):
        raise ValueError('original load admission differs or is not yet available')
    ref=admission['artifact'];artifact_name=artifact_pin+'.load-model.json'
    if not isinstance(ref,dict) or set(ref)!={'name','document_sha256','artifact_sha256'} or ref['name']!=artifact_name or ref['artifact_sha256']!=artifact_pin:
        raise ValueError('external original load model pin required')
    model_raw,artifact=_json(root,artifact_name);runtime=runtime_manifest()
    if sha256(model_raw).hexdigest()!=digest(ref['document_sha256']) or artifact.get('artifact_sha256')!=artifact_pin:
        raise ValueError('original admitted model bytes differ')
    if identity(runtime)!=admission['runtime_sha256']:
        # Check the previous opaque admission and every original byte before
        # allowing a normal scheduled replacement. Never serve its numerics
        # under changed code, and never treat changed data as runtime drift.
        if (set(artifact)!=ARTIFACT_FIELDS or artifact['schema']!=ARTIFACT_SCHEMA or
            identity({k:v for k,v in artifact.items() if k!='artifact_sha256'})!=artifact_pin or
            identity(artifact['runtime_manifest'])!=admission['runtime_sha256'] or
            instant(artifact['trained_at'])>instant(admission['verified_at'])):
            raise ValueError('previous load admission binding differs')
        _verify_files(root,admission,artifact,guard);guard()
        if _json(root,'current.json',8192)[0]!=raw or _json(root,name)[0]!=admission_raw or _json(root,artifact_name)[0]!=model_raw:
            raise ValueError('load selection changed during revalidation admission')
        raise LoadRuntimeRevalidationRequired(admission['sources'])
    verify_compact(artifact,runtime_manifest=runtime)
    if instant(artifact['trained_at'])>instant(admission['verified_at']):raise ValueError('admission precedes load preparation')
    _verify_files(root,admission,artifact,guard);guard()
    value=dict(schema=SOURCE_SCHEMA,available_at=admission['verified_at'],artifact=artifact,admission=admission,automatic_actuation=False)
    value['source_sha256']=identity(value)
    if (_json(root,'current.json',8192)[0]!=raw or _json(root,name)[0]!=admission_raw or
        _json(root,artifact_name)[0]!=model_raw or runtime_manifest()!=runtime):raise ValueError('load selection changed during verification')
    _verify_files(root,admission,artifact,guard);guard()
    return loads(canonical(value))


def refresh_profile(*,root,connect,cutoff,clock,remaining,guard):
    root=Path(root);root.mkdir(mode=0o700,parents=True,exist_ok=True);_directory(root)
    cutoff=utc(cutoff);local=cutoff.astimezone(_zone('America/Denver'))
    if local!=local.replace(hour=0,minute=0,second=0,microsecond=0):raise ValueError('completed local load cutoff required')
    try:previous=_private_file(root/'current.json',8192)[0]
    except FileNotFoundError:previous=None
    expected_sources={}
    if previous is not None:
        pointer=loads(previous)
        if set(pointer)!={'schema','admission_name','admission_sha256','artifact_sha256'} or pointer['schema']!=CURRENT_SCHEMA:
            raise ValueError('current load target belongs to another producer')
        # A changed runtime refuses serving until this normal scheduled job
        # revalidates the retained original days. It must not block its own
        # replacement indefinitely. All previous immutable files stay intact.
        try:
            current=read_current(root,assessed_at=clock(),guard=guard)
            expected_sources={r['name']:(r['file_sha256'],r['source_sha256']) for r in current['admission']['sources']}
        except LoadRuntimeRevalidationRequired as changed:
            current=None
            expected_sources={name:(file_pin,source_pin) for name,file_pin,source_pin in changed.sources}
        if current is not None and instant(current['artifact']['cutoff'])>=cutoff:
            return dict(status='load_profile_already_current',artifact_sha256=current['artifact']['artifact_sha256'],fit_executed=False,automatic_actuation=False)
    runtime=runtime_manifest();sources=[];refs=[]
    for offset in range(POLICY['lookback_days'],0,-1):
        guard();remaining();start=(local-timedelta(days=offset)).astimezone(cutoff.tzinfo);end=(local-timedelta(days=offset-1)).astimezone(cutoff.tzinfo)
        name=start.astimezone(_zone('America/Denver')).date().isoformat()+'.ac-day.json.gz';path=root/name
        try:source,compressed=_read_day(path)
        except FileNotFoundError:
            if name in expected_sources:raise ValueError('retained original load day is missing') from None
            source=capture_day(connect=connect,start=start,end=end,clock=clock,remaining=remaining)
            compressed=gzip.compress(canonical(source),compresslevel=3,mtime=0);guard();_immutable(path,compressed)
        if name in expected_sources and expected_sources[name]!=(sha256(compressed).hexdigest(),source['source_sha256']):
            raise ValueError('retained original load day changed during preparation')
        sources.append(source);refs.append(dict(name=name,file_sha256=sha256(compressed).hexdigest(),source_sha256=source['source_sha256']))
    guard();trained=utc(clock());artifact=build_artifact(sources=sources,cutoff=cutoff,trained_at=trained,runtime_manifest=runtime)
    guard();model_raw=canonical(artifact);model_name=artifact['artifact_sha256']+'.load-model.json';_immutable(root/model_name,model_raw)
    admission=dict(schema=ADMISSION_SCHEMA,verified_at=utc(clock()).isoformat(),artifact=dict(name=model_name,document_sha256=sha256(model_raw).hexdigest(),artifact_sha256=artifact['artifact_sha256']),
        runtime_sha256=identity(runtime),sources=refs)
    admission['admission_sha256']=identity(admission);admission_name=admission['admission_sha256']+'.load-admission.json'
    _verify_files(root,admission,artifact,guard)
    if runtime_manifest()!=runtime:raise ValueError('load preparation runtime changed')
    _immutable(root/admission_name,canonical(admission));guard()
    pointer=dict(schema=CURRENT_SCHEMA,admission_name=admission_name,admission_sha256=admission['admission_sha256'],artifact_sha256=artifact['artifact_sha256'])
    temporary=root/('.load-current-'+secrets.token_hex(16))
    try:
        _immutable(temporary,canonical(pointer));guard()
        try:actual=_private_file(root/'current.json',8192)[0]
        except FileNotFoundError:actual=None
        if actual!=previous:raise ValueError('load selection changed during preparation')
        os.replace(temporary,root/'current.json')
        read_current(root,assessed_at=clock(),guard=guard)
    finally:temporary.unlink(missing_ok=True)
    return dict(status='load_profile_prepared',artifact_sha256=artifact['artifact_sha256'],dataset_sha256=artifact['dataset_sha256'],
        trained_through=artifact['profile']['latest_qualified_hour_end'],training_cutoff=cutoff.isoformat(),model_status=artifact['profile']['status'],fit_executed=True,automatic_actuation=False)


def verify_admitted_source(source,*,runtime_manifest,as_of):
    """Verify the frozen admission payload; file binding is the capturer's job."""
    if (not isinstance(source,dict) or set(source)!={'schema','available_at','artifact','admission','automatic_actuation','source_sha256'} or
        source['schema']!=SOURCE_SCHEMA or source['automatic_actuation'] is not False or
        identity({k:v for k,v in source.items() if k!='source_sha256'})!=source['source_sha256']):
        raise ValueError('closed original admitted load source required')
    artifact=verify_compact(source['artifact'],runtime_manifest=runtime_manifest);admission=source['admission']
    if (not isinstance(admission,dict) or set(admission)!={'schema','verified_at','artifact','runtime_sha256','sources','admission_sha256'} or
        admission['schema']!=ADMISSION_SCHEMA or identity({k:v for k,v in admission.items() if k!='admission_sha256'})!=admission['admission_sha256'] or
        admission['runtime_sha256']!=identity(runtime_manifest)):
        raise ValueError('original load admission differs')
    if source['available_at']!=admission['verified_at'] or not instant(artifact['trained_at'])<=instant(source['available_at'])<=utc(as_of):
        raise ValueError('original load model is not available at issue')
    if admission['artifact']!=dict(name=artifact['artifact_sha256']+'.load-model.json',document_sha256=identity(artifact),artifact_sha256=artifact['artifact_sha256']):
        raise ValueError('original compact load model pin differs')
    if not isinstance(admission['sources'],list) or len(admission['sources'])!=14 or len(artifact['days'])!=14:
        raise ValueError('complete admitted original load days required')
    for ref,day in zip(admission['sources'],artifact['days']):
        name=instant(day['window_start']).astimezone(_zone('America/Denver')).date().isoformat()+'.ac-day.json.gz'
        if not isinstance(ref,dict) or set(ref)!={'name','file_sha256','source_sha256'} or ref['name']!=name or ref['source_sha256']!=day['source_sha256']:
            raise ValueError('admitted load source pin differs')
        digest(ref['file_sha256'])
    return loads(canonical(source))
