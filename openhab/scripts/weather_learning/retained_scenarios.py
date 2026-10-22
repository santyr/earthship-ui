"""Read-only native thermal bridge into an explicitly pinned original producer."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
import base64,gzip,io,json,os,subprocess,sys
from household_cycle_deploy import verify_stage
from .contracts import canonical,identity,digest
from .source_bundle import capture_sources

ROOT=Path(__file__).resolve().parents[3]
PRODUCER_SCHEMA='earthship-retained-native-scenario-producer/v1'
SCHEMA='earthship-retained-native-scenario-context/v1'
REQUEST_SCHEMA='earthship-retained-native-scenario-request/v1'
REPLY_SCHEMA='earthship-retained-native-scenario-reply/v1'
FIELDS={'schema','producer','owned_sources','prepared','native_context_sha256','artifact_sha256','original_source_manifest','original_source_package','adapter_source_sha256','native_environment','native_binary_files','context_sha256'}
_CACHE=ContextVar('retained_native_scenario_opportunity',default=None)
_SEAL=object()


def producer_reference(value):
    if (not isinstance(value,dict) or set(value)!={'schema','stage','deployment_sha256'} or value['schema']!=PRODUCER_SCHEMA or
            not isinstance(value['stage'],str) or not Path(value['stage']).is_absolute()):raise ValueError('closed explicit original producer required')
    digest(value['deployment_sha256']);return value


@contextmanager
def retained_cache():
    token=_CACHE.set({})
    try:yield
    finally:_CACHE.reset(token)


def _binary_inventory():
    from .probabilistic_artifacts import numerical_environment
    environment=numerical_environment()
    paths=[Path(sys.executable).resolve()]+[Path(sys.modules[name].__file__).resolve() for name in ('numpy.linalg._umath_linalg','numpy._core._multiarray_umath','scipy.optimize._lbfgsb','scipy.special._ufuncs')]
    return environment,{str(p):sha256(p.read_bytes()).hexdigest() for p in paths}


def _check_binaries(environment,files):
    if (not isinstance(environment,dict) or set(environment)!={'python','numpy','scipy','binary_sha256s'} or
            not isinstance(files,dict) or not 1<=len(files)<=8 or
            {Path(p).name:pin for p,pin in files.items()}!=environment['binary_sha256s']):raise ValueError('exact original numerical binary inventory required')
    for name,pin in files.items():
        path=Path(name);digest(pin)
        if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved original numerical binary required')
        total=0;hash_=sha256()
        with path.open('rb') as stream:
            while raw:=stream.read(1024**2):
                total+=len(raw)
                if total>128*1024**2:raise ValueError('bounded original numerical binary required')
                hash_.update(raw)
        if hash_.hexdigest()!=pin:raise ValueError('original numerical binary changed')


def _stage_sources(producer):
    producer_reference(producer);stage=Path(producer['stage']);verify_stage(stage,expected_deployment_sha256=producer['deployment_sha256'])
    return capture_sources(stage/'sources')


def _adapter_sha():return identity({n:sha256(raw).hexdigest() for n,raw in capture_sources(ROOT).items()})


def _launch(request,*,guard):
    producer=request['producer'];stage=Path(producer['stage'])
    import earthship_energy.power_evidence as companion
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(stage/'sources/openhab/scripts')+':'+str(Path(companion.__file__).resolve().parents[1]),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1')
    # run_path avoids placing the new script directory before original imports.
    bootstrap="import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_path(sys.argv[2],run_name='__main__')"
    guard();run=subprocess.run(['/usr/bin/python3','-c',bootstrap,str(stage/'sources/openhab/scripts'),str(ROOT/'openhab/scripts/weather_learning/retained_scenario_child.py')],cwd=stage,env=env,input=canonical(request),capture_output=True,timeout=80)
    guard()
    if run.returncode:raise ValueError('original native scenario process refused: '+run.stderr.decode(errors='replace')[-512:])
    return run.stdout


def _request(*,producer,energy,plan,action,scenario=None,positions=None,guard=lambda:None):
    producer=producer_reference(producer);sources=_stage_sources(producer);guard()
    request=dict(schema=REQUEST_SCHEMA,producer=producer,energy=energy,plan=plan,action=action,scenario=scenario,positions=positions,adapter_source_sha256=_adapter_sha())
    if len(canonical(request))>16*1024**2:raise ValueError('bounded original native request required')
    key=identity(request);cache=_CACHE.get()
    if cache is not None and key in cache:reply=json.loads(cache[key])
    else:
        raw=_launch(request,guard=guard)
        if not isinstance(raw,bytes) or len(raw)>16*1024**2:raise ValueError('bounded original native reply required')
        reply=json.loads(raw)
    if (not isinstance(reply,dict) or set(reply)!={'schema','request_sha256','deployment_sha256','environment','binary_files','result','reply_sha256'} or
            reply['schema']!=REPLY_SCHEMA or reply['request_sha256']!=key or reply['deployment_sha256']!=producer['deployment_sha256'] or
            reply['reply_sha256']!=identity({k:v for k,v in reply.items() if k!='reply_sha256'})):raise ValueError('original native reply binding differs')
    _check_binaries(reply['environment'],reply['binary_files']);guard()
    if _stage_sources(producer)!=sources or _adapter_sha()!=request['adapter_source_sha256']:raise ValueError('original producer or adapter changed during projection')
    if cache is not None and key not in cache:
        if len(cache)>=16:raise ValueError('bounded per-opportunity native reply cache required')
        cache[key]=canonical(reply)
    return reply,sources,request['adapter_source_sha256']


class RetainedNativeContext:
    __slots__=('_content','_seal')
    def __init__(self,*args,**kwargs):raise TypeError('prepare a verified retained native context')
    def __setattr__(self,name,value):raise AttributeError('retained native context is immutable')
    def to_dict(self):
        if getattr(self,'_seal',None) is not _SEAL:raise ValueError('verified retained native context required')
        return json.loads(self._content)


def prepare_retained_inputs(*,energy,plan,producer,guard=lambda:None):
    from .native_forecast import validate_native_forecast
    reply,sources,adapter=_request(producer=producer,energy=energy,plan=plan,action='prepare',guard=guard);result=reply['result']
    if not isinstance(result,dict) or set(result)!={'prepared','native_context_sha256','artifact_sha256'}:raise ValueError('closed original native preparation required')
    digest(result['native_context_sha256']);digest(result['artifact_sha256']);prepared=result['prepared'];validate_native_forecast(prepared['forcing'])
    if prepared['household_inputs'].get('thermal_context') is not None:raise ValueError('native result must remain in its original process')
    value=dict(schema=SCHEMA,producer=producer,owned_sources=dict(energy=energy,plan=plan),prepared=prepared,native_context_sha256=result['native_context_sha256'],artifact_sha256=result['artifact_sha256'],original_source_manifest={n:sha256(b).hexdigest() for n,b in sources.items()},original_source_package={n:base64.b64encode(gzip.compress(b,mtime=0)).decode() for n,b in sources.items()},adapter_source_sha256=adapter,native_environment=reply['environment'],native_binary_files=reply['binary_files'])
    value['context_sha256']=identity(value)
    if len(canonical(value))>16*1024**2:raise ValueError('bounded original retained native context required')
    return dict(forcing=prepared['forcing'],household_inputs=dict(prepared['household_inputs'],thermal_context=value))


def _context_sources(value):
    sources=_stage_sources(value['producer']);manifest={n:sha256(raw).hexdigest() for n,raw in sources.items()}
    if manifest!=value['original_source_manifest'] or set(manifest)!=set(value['original_source_package']) or _adapter_sha()!=value['adapter_source_sha256']:raise ValueError('retained native source package differs')
    for name,encoded in value['original_source_package'].items():
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(base64.b64decode(encoded,validate=True))) as stream:raw=stream.read(1024**2+1)
        except (ValueError,OSError,EOFError) as error:raise ValueError('literal original native source required') from error
        if raw!=sources[name]:raise ValueError('retained original native bytes differ')
    _check_binaries(value['native_environment'],value['native_binary_files'])


def restore_retained_context(value,*,guard=lambda:None):
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or len(canonical(value))>16*1024**2 or value['context_sha256']!=identity({k:v for k,v in value.items() if k!='context_sha256'})):raise ValueError('closed original retained native context required')
    _context_sources(value);expected=prepare_retained_inputs(**value['owned_sources'],producer=value['producer'],guard=guard)['household_inputs']['thermal_context']
    if canonical(expected)!=canonical(value):raise ValueError('retained native preparation differs from original inputs')
    context=object.__new__(RetainedNativeContext);object.__setattr__(context,'_content',canonical(value));object.__setattr__(context,'_seal',_SEAL);return context


def project_retained_scenario(scenario,context,*,positions,guard=lambda:None):
    from .scenarios import validate_scenario
    if type(context) is not RetainedNativeContext:raise ValueError('verified retained native context required')
    value=context.to_dict();_context_sources(value);case=validate_scenario(scenario)
    reply,sources,adapter=_request(**value['owned_sources'],producer=value['producer'],action='project',scenario=case,positions=positions,guard=guard);result=reply['result']
    if (not isinstance(result,dict) or set(result)!={'native_context_sha256','projection'} or result['native_context_sha256']!=value['native_context_sha256'] or
            reply['environment']!=value['native_environment'] or reply['binary_files']!=value['native_binary_files'] or result['projection'].get('model_sha256')!=value['artifact_sha256']):raise ValueError('native projection must retain original model and numerical environment')
    _context_sources(value);guard();return result['projection']
