"""Immutable legacy-v4 shadow diagnostics; never a graduation input.

The executing legacy writer's forcing record is retained verbatim as JSON data.
Native receipt proofs describe inputs observed now, not the artifact's training
hardware qualification. Raw native snapshots and verified delivery still need
separate source binding. This module never opens an artifact registry.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import gzip
from io import BytesIO
from hashlib import sha256
import json,math,re
from pathlib import Path
import sys

from forecast_input_capture import _directory,_instant
from forecast_temperature_origin import _read,_write
from weather_temperature_config import _object,_nonfinite
from thermal_model.temperature_history import STREAMS,_validate_sensor_receipt

SCHEMA='earthship-thermal-legacy-shadow-origin/v1'
VALUES={'output','artifact','raw_forecast','forecast_rows','current'}
FIELDS={'schema','forcing','native_origin','runtime','captured_at','release_authority',
        'artifact_native_phase_fit_claimed','raw_native_source_binding_verified',
        'publication_delivery_verified','runtime_source_bytes_retained'}
MAX_BYTES=4*1024*1024


def _canonical(value):
    def dates(value):
        if isinstance(value,datetime):return _instant(value.isoformat()).isoformat()
        raise TypeError('unsupported diagnostic value')
    return json.dumps(value,default=dates,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def _sha(value):
    if not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None:
        raise ValueError('complete diagnostic digest required')


def _validate_forcing(forcing):
    if (not isinstance(forcing,dict) or set(forcing)!=VALUES|{'schema','decision_at','inputs_available_at','published_at','sha256'}
            or forcing['schema']!='earthship-thermal-shadow-forcing-capture/v2'
            or not isinstance(forcing['sha256'],dict) or set(forcing['sha256'])!=VALUES):
        raise ValueError('original complete legacy forcing capture required')
    for name in VALUES:
        if forcing['sha256'][name]!=sha256(_canonical(forcing[name])).hexdigest():
            raise ValueError('original forcing digest differs')
    artifact=forcing['artifact'];output=forcing['output']
    if (not isinstance(artifact,dict) or artifact.get('schema')!='earthship-thermal-model/v4'
            or not isinstance(output,dict) or output.get('status')!='shadow'
            or output.get('version')!=1 or output.get('confidence',{}).get('grade') in (None,'unavailable')):
        raise ValueError('legacy v4 shadow required, not a qualified replacement')
    model=output.get('model')
    if not isinstance(model,dict) or model.get('codeRevision')!=artifact.get('code_revision'):
        raise ValueError('original published artifact identity differs')
    for key,field in (('createdAt','created_at'),('trainedThrough','trained_through')):
        if _instant(model[key]).replace(microsecond=0)!=_instant(artifact[field]).replace(microsecond=0):
            raise ValueError('original model clock differs')
    issued,available,published=map(_instant,(forcing['decision_at'],forcing['inputs_available_at'],forcing['published_at']))
    if not available<=issued<=published or _instant(output['generatedAt'])!=issued:
        raise ValueError('original issue clocks differ')
    return issued,available,published


def _validate_native(proof,current,available,published):
    if (not isinstance(proof,dict) or set(proof)!={'schema','assessed_at','roles'}
            or proof['schema']!='earthship-thermal-origin-temperatures/v2'
            or not isinstance(proof['roles'],dict) or set(proof['roles'])!=set(STREAMS)):
        raise ValueError('complete original native receipt proof required')
    observed=_instant(proof['assessed_at'])
    if observed>available:raise ValueError('native observations unavailable at original issue')
    floor=observed.replace(minute=observed.minute//5*5,second=0,microsecond=0)
    targets=[floor-timedelta(minutes=5*i) for i in reversed(range(288))]
    if targets[-1]!=observed:targets.append(observed)
    for role,(stream,model,sensor) in STREAMS.items():
        details=proof['roles'][role]
        if not isinstance(details,dict) or set(details)!={'identity','grid'}:
            raise ValueError('original native role required')
        identity=details['identity'];rows=details['grid']
        if (not isinstance(identity,dict) or set(identity)!={'stream','model','sensor_id','sensor_epoch'}
                or (identity['stream'],identity['model'],identity['sensor_id'])!=(stream,model,sensor)
                or type(identity['sensor_id']) is not int
                or not isinstance(rows,list) or len(rows)!=len(targets)):
            raise ValueError('complete original identity/grid required')
        for target,row in zip(targets,rows):
            if not isinstance(row,list) or len(row)!=2 or _instant(row[0])!=target:
                raise ValueError('original native grid target differs')
            if row[1] is not None:_validate_sensor_receipt(row[1],target,sensor_epoch=identity['sensor_epoch'])
        latest=rows[-1][1];reading=current.get(role) if isinstance(current,dict) else None
        if (latest is None or not isinstance(reading,dict)
                or _instant(reading['at'])!=_instant(latest['receivedAt'])
                or _instant(reading['validUntil'])!=_instant(latest['validUntil'])
                or not _instant(reading['at'])<=published<_instant(reading['validUntil'])
                or type(reading.get('value')) not in (int,float) or not math.isfinite(reading['value'])):
            raise ValueError('original initial state receipt differs or expired')
        # The deployed mass smoother's numeric output is retained as issued;
        # its training/model validity is not claimed by this diagnostic schema.
        if role!='mass' and reading['value']!=latest['temperatureF']:
            raise ValueError('original initial value differs')


def _validate_runtime(runtime):
    fields={'code_revision','interpreter_sha256','python_version','dependencies','source_sha256','observer_sha256'}
    if not isinstance(runtime,dict) or set(runtime)!=fields:
        raise ValueError('closed original runtime identity required')
    for key in ('code_revision','interpreter_sha256','observer_sha256'):_sha(runtime[key])
    if not isinstance(runtime['python_version'],str) or re.fullmatch(r'3\.[0-9]+\.[0-9]+',runtime['python_version']) is None:
        raise ValueError('original Python version required')
    deps=runtime['dependencies'];sources=runtime['source_sha256']
    if (not isinstance(deps,dict) or set(deps)!={'numpy','scipy','psycopg2'}
            or any(not isinstance(v,str) or re.fullmatch(r'[0-9][0-9A-Za-z.+_-]{0,79}',v) is None for v in deps.values())
            or not isinstance(sources,dict) or not 2<=len(sources)<=64 or 'thermal_intel.py' not in sources):
        raise ValueError('bounded original source/dependency identity required')
    for name,digest in sources.items():
        if not isinstance(name,str) or not 1<=len(name)<=256:
            raise ValueError('bounded relative original source required')
        p=Path(name)
        if (p.is_absolute() or str(p)!=name or not name.endswith('.py')
                or any(part in ('.','..') for part in p.parts)):
            raise ValueError('bounded relative original source required')
        _sha(digest)


def bind_legacy_runtime(root,paths):
    """Fingerprint declared source bytes and already-loaded dependencies only.

    No sources are imported and no artifact registry is opened. A guarded
    integration supplies the actual legacy/worker closure. This identity alone
    is not a retained compatible replay environment or release qualification.
    """
    root=Path(root)
    if (not root.is_absolute() or root.resolve(strict=True)!=root
            or not isinstance(paths,(list,tuple)) or not 2<=len(paths)<=64
            or any(not isinstance(p,str) for p in paths) or len(set(paths))!=len(paths)
            or 'thermal_intel.py' not in paths):
        raise ValueError('bounded declared original legacy closure required')
    sources={};total=0
    for name in paths:
        p=Path(name)
        if (not 1<=len(name)<=256 or p.is_absolute() or str(p)!=name
                or not name.endswith('.py') or any(part in ('.','..') for part in p.parts)):
            raise ValueError('relative original source required')
        raw=_read(root/p,2000000,source=True);total+=len(raw)
        if total>2000000:raise ValueError('bounded original source bytes required')
        sources[name]=sha256(raw).hexdigest()
    dependencies={}
    for name in ('numpy','scipy','psycopg2'):
        loaded=sys.modules.get(name)
        if loaded is None:raise ValueError('original dependency not already loaded')
        dependencies[name]=loaded.__version__.split()[0]
    interpreter=Path(sys.executable).resolve(strict=True)
    interpreter_digest=sha256(_read(interpreter,64000000,source=True)).hexdigest()
    observer=Path(__file__).resolve(strict=True)
    observer_digest=sha256(_read(observer,2000000,source=True)).hexdigest()
    result=dict(code_revision=sha256(_canonical(sources)).hexdigest(),
        source_sha256=sources,interpreter_sha256=interpreter_digest,
        observer_sha256=observer_digest,python_version='.'.join(map(str,sys.version_info[:3])),
        dependencies=dependencies)
    _validate_runtime(result)
    for name,expected in sources.items():
        if sha256(_read(root/name,2000000,source=True)).hexdigest()!=expected:
            raise ValueError('original source changed across binding')
    if (sha256(_read(interpreter,64000000,source=True)).hexdigest()!=interpreter_digest
            or sha256(_read(observer,2000000,source=True)).hexdigest()!=observer_digest):
        raise ValueError('original interpreter/observer changed across binding')
    return result


def validate_legacy_origin(record):
    if not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMA:
        raise ValueError('closed legacy diagnostic schema required')
    for key in FIELDS-{'schema','forcing','native_origin','runtime','captured_at'}:
        if record[key] is not False:raise ValueError('legacy diagnostic cannot confer qualification authority')
    issued,available,published=_validate_forcing(record['forcing'])
    if _instant(record['captured_at'])<published:raise ValueError('diagnostic capture precedes original publication')
    _validate_native(record['native_origin'],record['forcing']['current'],available,published)
    _validate_runtime(record['runtime'])
    if len(_canonical(record))>MAX_BYTES:raise ValueError('bounded legacy diagnostic required')


def build_legacy_origin(*,forcing,native_origin,runtime,captured_at):
    record=dict(schema=SCHEMA,forcing=forcing,native_origin=native_origin,runtime=runtime,
        captured_at=captured_at,release_authority=False,artifact_native_phase_fit_claimed=False,
        raw_native_source_binding_verified=False,publication_delivery_verified=False,
        runtime_source_bytes_retained=False)
    # JSON normalization freezes datetime values without sharing mutable inputs.
    frozen=json.loads(_canonical(record),object_pairs_hook=_object,parse_constant=_nonfinite)
    validate_legacy_origin(frozen);return frozen


def write_legacy_origin(directory,record):
    validate_legacy_origin(record);raw=_canonical(record)
    return _write(_directory(Path(directory)),sha256(raw).hexdigest()+'.legacy-shadow-origin-v1.json',raw)


def read_legacy_origin(directory,path):
    root=_directory(Path(directory));path=Path(path)
    if path.parent!=root or re.fullmatch('[0-9a-f]{64}\\.legacy-shadow-origin-v1\\.json',path.name) is None:
        raise ValueError('original legacy diagnostic path required')
    raw=_read(path,MAX_BYTES)
    if sha256(raw).hexdigest()!=path.name.split('.')[0]:raise ValueError('legacy diagnostic digest differs')
    record=json.loads(raw,object_pairs_hook=_object,parse_constant=_nonfinite)
    validate_legacy_origin(record)
    if _canonical(record)!=raw:raise ValueError('canonical original legacy diagnostic required')
    return record


class LegacyOriginObserver:
    """Optional wrappers around the deployed reader and existing capture writer.

    Original return values and exceptions are preserved. Only the additional
    diagnostic capture can fail; its error details never reach publication.
    A guarded integration must supply actual source-bound runtime identities.
    """
    def __init__(self,directory,*,runtime_provider,clock=None,on_gap=None):
        self.directory=_directory(Path(directory))
        self.runtime_provider=runtime_provider
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.on_gap=on_gap
        self.runtime=None;self.proof=None

    def _gap(self):
        if self.on_gap is not None:
            try:self.on_gap('legacy_origin_capture_gap')
            except Exception:pass

    def wrap_native(self,reader):
        def observed(*args,**kwargs):
            self.runtime=None;self.proof=None
            try:
                runtime=deepcopy(self.runtime_provider());_validate_runtime(runtime)
                self.runtime=runtime
            except Exception:pass
            caller=kwargs.get('origin_observer')
            def save(proof):
                if caller is not None:caller(proof)
                try:self.proof=deepcopy(proof)
                except Exception:self.proof=None
            return reader(*args,**{**kwargs,'origin_observer':save})
        return observed

    def wrap_capture(self,writer):
        def observed(*args,**kwargs):
            # An original writer failure retains the original semantics.
            path=writer(*args,**kwargs)
            try:
                if self.runtime is None or self.proof is None:
                    raise ValueError('original proof unavailable')
                if self.runtime_provider()!=self.runtime:
                    raise ValueError('original runtime changed across capture')
                compressed=_read(Path(path),256000)
                with gzip.GzipFile(fileobj=BytesIO(compressed)) as source:
                    raw=source.read(1000001)
                if len(raw)>1000000:raise ValueError('bounded original forcing required')
                forcing=json.loads(raw,object_pairs_hook=_object,parse_constant=_nonfinite)
                record=build_legacy_origin(forcing=forcing,native_origin=self.proof,
                    runtime=self.runtime,captured_at=self.clock())
                write_legacy_origin(self.directory,record)
            except Exception:self._gap()
            finally:self.runtime=None;self.proof=None
            return path
        return observed
