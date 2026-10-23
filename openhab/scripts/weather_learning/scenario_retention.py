"""Bounded, lossless scenario originals; private parents and shared source chunks.

The compact representation changes transport only. restore_compact reconstructs
exact canonical original bytes; numerical replay remains scenario_reporting's job.
Never evict originals or move this namespace outside the shared state allowance.
"""
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import base64,gzip,io,json
from .contracts import canonical,identity,digest,instant
from .scenario_reporting import ScenarioReport,MAX_BYTES,CACHE,public_view
from .shadow import ShadowStore,_directory
from .worker import collector_lock
from household_observation import _private_file

OPTIONAL_MAX_BYTES=256*1024**2
CORE_RESERVE_BYTES=384*1024**2
# These are the only factored locations. No sentinel supplied by an input can
# create a reference, and no path comes from the public GET reader.
SOURCE_PATHS=(('runtime','source_package'),('inputs','household_inputs','thermal_context','original_source_package'))
PARENT_PATHS={('inputs','owned_sources','energy'):'energy',('inputs','owned_sources','plan'):'plan',
 ('inputs','household_inputs','thermal_context','owned_sources','energy'):'energy',
 ('inputs','household_inputs','thermal_context','owned_sources','plan'):'plan'}


def _get(value,path):
    for key in path:
        if not isinstance(value,dict) or key not in value:return None
        value=value[key]
    return value


def _set(value,path,replacement):
    for key in path[:-1]:value=value[key]
    value[path[-1]]=replacement


def _zip(raw):return base64.b64encode(gzip.compress(raw,mtime=0)).decode('ascii')


def _unzip(encoded,maximum):
    if not isinstance(encoded,str) or len(encoded)>MAX_BYTES:raise ValueError('bounded compact encoding required')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(base64.b64decode(encoded,validate=True))) as stream:raw=stream.read(maximum+1)
    except (ValueError,OSError,EOFError) as error:raise ValueError('invalid compact original') from error
    if len(raw)>maximum:raise ValueError('compact original expansion bound exceeded')
    return raw


def _read(path,maximum=MAX_BYTES):return json.loads(_private_file(Path(path),maximum)[0])


def _capacity(state,extra,guard):
    own=shared=count=0
    for directory in state.root.iterdir():
        if not directory.is_dir() or directory.is_symlink():continue
        for path in directory.glob('*.json'):
            if count%100==0:guard()
            count+=1;size=path.lstat().st_size;shared+=size
            if directory.name=='scenario-reports':own+=size
            if count>=10000:raise ValueError('shared scenario object capacity exhausted')
    if own+extra>OPTIONAL_MAX_BYTES:raise ValueError('optional scenario capacity exhausted')
    if shared+extra>2*1024**3-CORE_RESERVE_BYTES:raise ValueError('shared core reserve unavailable')


def _write(state,path,value,guard):
    raw=canonical(value)
    try:old=_private_file(path,MAX_BYTES)[0]
    except FileNotFoundError:old=None
    if old is not None:
        if old!=raw:raise ValueError('immutable compact object differs')
        return
    guard();_capacity(state,len(raw),guard);state._write(path,value,immutable=True);guard()
    if _private_file(path,MAX_BYTES)[0]!=raw:raise ValueError('compact original readback differs')


def archive_compact(root,raw,*,parents,guard=lambda:None):
    report=ScenarioReport(raw);value=report.to_dict()
    if raw!=canonical(value):raise ValueError('canonical original scenario bytes required')
    if not isinstance(parents,dict) or not set(parents)<=set(PARENT_PATHS.values()):raise ValueError('closed original parent paths required')
    state=ShadowStore(Path(root));directory=state.root/'scenario-reports';_directory(directory);refs=[]
    for path in SOURCE_PATHS:
        source=_get(value,path)
        if source is None:continue
        encoded=canonical(source);pin=sha256(encoded).hexdigest()
        chunk=dict(schema='earthship-scenario-source-chunk/v1',value_sha256=pin,bytes=len(encoded),gzip_base64=_zip(encoded))
        _write(state,directory/('source-'+pin+'.json'),chunk,guard)
        refs.append(dict(kind='source',path=list(path),sha256=pin));_set(value,path,None)
    for path,key in PARENT_PATHS.items():
        source=_get(value,path)
        if source is None:continue
        if key not in parents:raise ValueError('original parent path required')
        original=Path(parents[key])
        if not original.is_absolute() or original.resolve()!=original:raise ValueError('resolved original parent required')
        parent_raw,_=_private_file(original,2097152)
        if canonical(json.loads(parent_raw))!=canonical(source):raise ValueError('original parent value differs')
        refs.append(dict(kind='parent',path=list(path),file=str(original),bytes=len(parent_raw),bytes_sha256=sha256(parent_raw).hexdigest(),value_sha256=identity(source)))
        _set(value,path,None)
    capsule=dict(schema='earthship-compact-scenario-original/v1',original_report_sha256=report.to_dict()['report_sha256'],original_bytes=len(raw),original_bytes_sha256=sha256(raw).hexdigest(),references=refs,gzip_base64=_zip(canonical(value)))
    capsule['capsule_sha256']=identity(capsule)
    _write(state,directory/('original-'+capsule['original_report_sha256']+'.json'),capsule,guard)
    if restore_compact(root,capsule['original_report_sha256'],guard=guard).content!=raw:raise ValueError('exact original reconstruction differs')
    return capsule


def restore_compact(root,report_sha256,*,guard=lambda:None):
    directory=Path(root)/'scenario-reports';pin=digest(report_sha256)
    capsule=_read(directory/('original-'+pin+'.json'))
    fields={'schema','original_report_sha256','original_bytes','original_bytes_sha256','references','gzip_base64','capsule_sha256'}
    if (set(capsule)!=fields or capsule['schema']!='earthship-compact-scenario-original/v1' or capsule['original_report_sha256']!=pin or
        capsule['capsule_sha256']!=identity({k:v for k,v in capsule.items() if k!='capsule_sha256'}) or
        type(capsule['original_bytes']) is not int or not 0<capsule['original_bytes']<=MAX_BYTES or
        not isinstance(capsule['references'],list) or not 1<=len(capsule['references'])<=6):raise ValueError('closed compact original required')
    value=json.loads(_unzip(capsule['gzip_base64'],MAX_BYTES));seen=set()
    for ref in capsule['references']:
        guard();path=tuple(ref['path'])
        if path in seen or _get(value,path) is not None:raise ValueError('unique empty compact location required')
        seen.add(path)
        if ref['kind']=='source':
            if path not in SOURCE_PATHS or set(ref)!={'kind','path','sha256'}:raise ValueError('closed source reference required')
            source=_read(directory/('source-'+digest(ref['sha256'])+'.json'))
            if set(source)!={'schema','value_sha256','bytes','gzip_base64'} or source['schema']!='earthship-scenario-source-chunk/v1':raise ValueError('closed source chunk required')
            encoded=_unzip(source['gzip_base64'],MAX_BYTES)
            if source['value_sha256']!=ref['sha256'] or len(encoded)!=source['bytes'] or sha256(encoded).hexdigest()!=ref['sha256']:raise ValueError('source chunk changed')
            replacement=json.loads(encoded)
        elif ref['kind']=='parent':
            if path not in PARENT_PATHS or set(ref)!={'kind','path','file','bytes','bytes_sha256','value_sha256'}:raise ValueError('closed parent reference required')
            original=Path(ref['file'])
            if not original.is_absolute() or original.resolve()!=original:raise ValueError('resolved original parent required')
            encoded=_private_file(original,2097152)[0]
            if len(encoded)!=ref['bytes'] or sha256(encoded).hexdigest()!=ref['bytes_sha256']:raise ValueError('original parent bytes changed')
            replacement=json.loads(encoded)
            if identity(replacement)!=ref['value_sha256']:raise ValueError('original parent value changed')
        else:raise ValueError('unknown compact reference')
        _set(value,path,replacement)
    raw=canonical(value)
    if len(raw)!=capsule['original_bytes'] or sha256(raw).hexdigest()!=capsule['original_bytes_sha256']:raise ValueError('original scenario bytes changed')
    report=ScenarioReport(raw)
    if report.to_dict()['report_sha256']!=pin:raise ValueError('original scenario identity changed')
    guard();return report


def production_view(report,*,guard=lambda:None):
    original=report.to_dict();full=public_view(report,guard=guard);inputs=original['inputs'];context=inputs['household_inputs']['thermal_context'];cases=[]
    for projection,row in zip(original['output']['stress'],full['stress'],strict=True):
        thermal={p['at']:p for p in row['thermal_trajectory']}
        cases.append(dict(name=row['name'],temperature_delta_c=projection['recipe']['temperature_delta_c'],solar_multiplier=projection['recipe']['solar_multiplier'],raw_potential_pv_kwh=row['potential_pv_kwh'],modeled_captured_pv_kwh=row['modeled_captured_pv_kwh'],minimum_nominal_soc_pct=row['minimum_nominal_soc_pct'],indoor_air_f=row['indoor_air_f'],north_wall_f=row['north_wall_f'],thermal_status=row['thermal_status'],trajectory=[dict(at=p['at'],nominal_soc_pct=p['nominal_soc_pct'],cumulative_raw_pv_kwh=p['cumulative_potential_pv_kwh'],air_f=thermal.get(p['at'],{}).get('air_f'),north_wall_f=thermal.get(p['at'],{}).get('north_wall_f')) for p in row['trajectory']]))
    household=inputs['household_inputs'];value=dict(schema='earthship-production-weather-sensitivity/v1',generated_at=full['generated_at'],origin=full['origin'],through=full['through'],valid_until=full['valid_until'],source_forecast_sha256=full['source_forecast_sha256'],source_initialized_at=full['source_initialized_at'],original_report_sha256=full['original_report_sha256'],policy_sha256=full['policy_sha256'],source_package_sha256=original['runtime']['source_package_sha256'],thermal_model_sha256=context.get('artifact_sha256') if isinstance(context,dict) else None,producer_deployment_sha256=context.get('producer',{}).get('deployment_sha256') if isinstance(context,dict) else None,initial_soc_pct=household['initial_soc_pct'],nominal_bank_kwh=household['nominal_bank_kwh'],fixed_load_ac_w=household['load_ac_w'],cases=cases,joint_status=full['joint']['status'],probability_claim=False,physical_calibration_qualified=False,automatic_actuation=False)
    value['report_sha256']=identity(value)
    if len(canonical(value))>65536:raise ValueError('bounded production sensitivity view exceeded')
    return value


def retain_compact(root,report,*,parents,clock=lambda:datetime.now(timezone.utc),guard=lambda:None,before_confirm=lambda:None):
    view=production_view(report,guard=guard);state=ShadowStore(Path(root));directory=state.root/'scenario-reports';_directory(directory)
    with collector_lock(state.root/'scenario-publish.lock'):
        capsule=archive_compact(root,report.content,parents=parents,guard=guard)
        now=clock();fresh=instant(view['generated_at'])<=now<instant(view['valid_until'])
        marker=directory/('view-'+view['report_sha256']+'.json')
        if fresh:
            raw=canonical(view)
            if marker.exists():
                previous=_read(marker,32768)
                if previous['cache_bytes_sha256']!=sha256(raw).hexdigest():raise ValueError('confirmed scenario view differs')
                return dict(retained=True,cached=_private_file(state.root/CACHE,256*1024)[0]==raw,report_sha256=view['original_report_sha256'],already_confirmed=True)
            guard();before_confirm();_capacity(state,len(raw)+32768,guard);state._write(state.root/CACHE,view)
            if _private_file(state.root/CACHE,256*1024)[0]!=raw:raise ValueError('scenario cache readback differs')
            guard();before_confirm();published=clock()
            if not now<=published<instant(view['valid_until']):raise ValueError('scenario publication expired or clock regressed')
            receipt=dict(schema='earthship-confirmed-scenario-view/v1',original_report_sha256=view['original_report_sha256'],capsule_sha256=capsule['capsule_sha256'],report_sha256=view['report_sha256'],cache_bytes_sha256=sha256(raw).hexdigest(),origin=view['origin'],generated_at=view['generated_at'],valid_until=view['valid_until'],published_at=published.isoformat(),automatic_actuation=False)
            receipt['receipt_sha256']=identity(receipt);_write(state,marker,receipt,guard)
        return dict(retained=True,cached=fresh,report_sha256=view['original_report_sha256'],already_confirmed=False)
