"""Versioned original thermal input proof; no release, publication or actuation.

Native origin receipts and publication-runtime identity are captured separately
from the artifact's training revision. Legacy capture contracts remain exact.
"""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
import math
from pathlib import Path,PurePosixPath
import re
import os
import gzip
from io import BytesIO
import stat
from uuid import uuid4

from .forcing_capture import _canonical,_artifact_payload
from .dataset import latent_mass_from_series
from .schema import validate_shadow_output
from .temperature_history import STREAMS,_validate_receipt,_validate_sensor_receipt
from weather_temperature_evidence import sensor_epoch_id

SCHEMA='earthship-thermal-origin-capture/v1'
RELEASE_SCHEMA='earthship-thermal-origin-capture/v2'
SENSOR_SCHEMA='earthship-thermal-origin-capture/v3'
SENSOR_RELEASE_SCHEMA='earthship-thermal-origin-capture/v4'
VALUES={'output','artifact','raw_forecast','forecast_rows','current',
        'origin_temperatures','runtime','known_actions','source_epochs'}
RUNTIME_FIELDS={'schema','code_revision','observer_revision','interpreter_sha256',
                'python_version','dependencies','source_manifest'}


def _utc(value):
    if isinstance(value,str):
        try:value=datetime.fromisoformat(value)
        except ValueError:raise ValueError('aware origin timestamp required') from None
    if not isinstance(value,datetime) or value.utcoffset() is None:
        raise ValueError('aware origin timestamp required')
    return value.astimezone(timezone.utc)


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('finite original state required')
    return float(value)


def _digest(value):
    if not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None:
        raise ValueError('full runtime/source digest required')
    return value


def _runtime(value):
    if (not isinstance(value,dict) or set(value)!=RUNTIME_FIELDS or
            value['schema']!='earthship-thermal-runtime-binding/v1'):
        raise ValueError('closed publication runtime binding required')
    for field in ('code_revision','observer_revision','interpreter_sha256'):_digest(value[field])
    if not isinstance(value['python_version'],str) or re.fullmatch(r'3\.[0-9]+\.[0-9]+',value['python_version']) is None:
        raise ValueError('Python runtime version required')
    dependencies=value['dependencies']
    if not isinstance(dependencies,dict) or set(dependencies)!={'numpy','scipy','psycopg2'}:
        raise ValueError('exact numerical/runtime dependency versions required')
    for version in dependencies.values():
        if not isinstance(version,str) or re.fullmatch(r'[0-9][0-9A-Za-z.+_-]{0,79}',version) is None:
            raise ValueError('runtime dependency version invalid')
    manifest=value['source_manifest']
    if not isinstance(manifest,dict) or not 2<=len(manifest)<=64:
        raise ValueError('bounded runtime source manifest required')
    for name,digest in manifest.items():
        if not isinstance(name,str):raise ValueError('runtime source path invalid')
        path=PurePosixPath(name)
        if (path.is_absolute() or str(path)!=name or not name.endswith('.py') or
                any(part in ('.','..') for part in path.parts)):
            raise ValueError('runtime source path invalid')
        _digest(digest)
    if (manifest.get('thermal_model/origin_capture.py')!=value['observer_revision'] or
            'thermal_intel.py' not in manifest):
        raise ValueError('origin observer/runtime closure incomplete')


def _temperatures(proof,current,*,issued_at,published_at,version=1):
    if (not isinstance(proof,dict) or set(proof)!={'schema','assessed_at','roles'} or
            proof['schema']!=f'earthship-thermal-origin-temperatures/v{version}' or
            not isinstance(proof['roles'],dict) or set(proof['roles'])!=set(STREAMS)):
        raise ValueError('complete native origin temperatures required')
    observed=_utc(proof['assessed_at'])
    if observed>issued_at:raise ValueError('origin observations were unavailable at issue')
    floor=observed.replace(minute=observed.minute//5*5,second=0,microsecond=0)
    targets=[floor-timedelta(minutes=5*i) for i in reversed(range(288))]
    if targets[-1]!=observed:targets.append(observed)
    epochs={}; selected={}
    for role,(stream,model,sensor_id) in STREAMS.items():
        evidence=proof['roles'][role]
        phase=None
        if version==2 and isinstance(evidence,dict):
            identity=evidence.get('identity')
            phase=sensor_epoch_id(identity.get('sensor_epoch') if isinstance(identity,dict) else None)
        if (not isinstance(evidence,dict) or set(evidence)!={'identity','grid'} or
                evidence['identity']!=dict(stream=stream,model=model,sensor_id=sensor_id,**({} if version==1 else dict(sensor_epoch=phase))) or
                type(evidence['identity'].get('sensor_id')) is not int):
            raise ValueError('native origin identity differs')
        rows=evidence['grid']
        if not isinstance(rows,list) or len(rows)!=len(targets):
            raise ValueError('complete native origin grid required')
        history=[]
        for target,row in zip(targets,rows):
            if not isinstance(row,list) or len(row)!=2 or _utc(row[0])!=target:
                raise ValueError('native origin grid target differs')
            receipt=row[1]
            if receipt is not None:
                if version==1:_validate_receipt(receipt,target)
                else:_validate_sensor_receipt(receipt,target,sensor_epoch=phase)
            if target<observed:
                history.append((target,math.nan if receipt is None else receipt['temperatureF']))
        if version==1 and len({row[1]['streamEpoch'] for row in rows if row[1] is not None})>1:
            raise ValueError('mixed native origin sensor epochs')
        latest=rows[-1][1]
        if latest is None:raise ValueError('current native origin receipt unavailable')
        if not _utc(latest['validUntil'])>published_at:
            raise ValueError('current native origin receipt expired before publication')
        reading=current.get(role)
        if (not isinstance(reading,dict) or _utc(reading.get('at'))!=_utc(latest['receivedAt']) or
                _utc(reading.get('validUntil'))!=_utc(latest['validUntil'])):
            raise ValueError('original initial state receipt binding differs')
        received=_utc(latest['receivedAt'])
        if not history or received>history[-1][0]:history.append((received,latest['temperatureF']))
        expected=float(latest['temperatureF'])
        if role=='mass':
            latent=latent_mass_from_series(history)
            if latent is not None:expected=latent[1]
        if not math.isclose(_number(reading.get('value')),expected,rel_tol=0,abs_tol=1e-9):
            raise ValueError('original initial thermal state differs from native source/observer')
        epochs[role]=phase if version==2 else latest['streamEpoch'];selected[role]=expected
    return epochs,selected


def _actions(value,issued_at):
    if value is None:return
    if (not isinstance(value,dict) or set(value)!={'schema','known_at','events','modes','snapshot_sha256'} or
            value['schema']!='earthship-thermal-known-actions/v1' or _utc(value['known_at'])>issued_at):
        raise ValueError('original action knowledge binding required')
    known=_utc(value['known_at'])
    for field in ('events','modes'):
        if not isinstance(value[field],list) or len(value[field])>500:
            raise ValueError('bounded original action knowledge required')
        for event in value[field]:
            if (not isinstance(event,dict) or
                    any(name not in event for name in ('received_at','effective_at','created_at','source')) or
                    not _utc(event['received_at'])<=_utc(event['created_at'])<=known or
                    _utc(event['effective_at'])>known):
                raise ValueError('future or unbound action knowledge')
    body={key:value[key] for key in ('events','modes')}
    if sha256(_canonical(body)).hexdigest()!=_digest(value['snapshot_sha256']):
        raise ValueError('original action snapshot digest differs')


def validate_origin_capture(record):
    return _validate_origin_capture(record, schema=SCHEMA, output_validator=validate_shadow_output)


def validate_sensor_origin_capture(record):
    return _validate_origin_capture(record,schema=SENSOR_SCHEMA,output_validator=validate_shadow_output,temperature_version=2)


def validate_release_origin_capture(record):
    return _validate_release_origin(record,version=1)


def validate_sensor_release_origin_capture(record):
    return _validate_release_origin(record,version=2)


def _validate_release_origin(record,*,version):
    from .release import validate_release_output,validate_sensor_release_output
    _validate_origin_capture(record,schema=SENSOR_RELEASE_SCHEMA if version==2 else RELEASE_SCHEMA,
        output_validator=validate_sensor_release_output if version==2 else validate_release_output,temperature_version=version)
    metadata = record['output']['release']
    if (metadata['artifactSha256'] != record['sha256']['artifact'] or
            metadata['runtimeSha256'] != record['sha256']['runtime'] or
            metadata['sensorEpochs'] != record['source_epochs']):
        raise ValueError('published release identity differs from original inputs')
    published = _utc(record['published_at'])
    if not _utc(metadata['qualifiedAt']) <= published < _utc(metadata['expiresAt']):
        raise ValueError('release qualification unavailable at publication acknowledgement')
    return record


def validate_observed_origin_capture(record):
    if isinstance(record,dict) and record.get('schema')==SENSOR_RELEASE_SCHEMA:
        return validate_sensor_release_origin_capture(record)
    if isinstance(record,dict) and record.get('schema')==SENSOR_SCHEMA:
        return validate_sensor_origin_capture(record)
    if isinstance(record, dict) and record.get('schema') == RELEASE_SCHEMA:
        return validate_release_origin_capture(record)
    return validate_origin_capture(record)


def _validate_origin_capture(record, *, schema, output_validator,temperature_version=1):
    if (not isinstance(record,dict) or set(record)!=VALUES|{
            'schema','issued_at','inputs_available_at','published_at','sha256'} or
            record['schema']!=schema or not isinstance(record['sha256'],dict) or
            set(record['sha256'])!=VALUES):
        raise ValueError('closed origin capture contract required')
    for name in VALUES:
        if sha256(_canonical(record[name])).hexdigest()!=_digest(record['sha256'][name]):
            raise ValueError('origin capture digest differs')
    issue=_utc(record['issued_at']);published=_utc(record['published_at'])
    if not _utc(record['inputs_available_at'])<=issue<=published:
        raise ValueError('original inputs were unavailable at issue')
    output=record['output'];output_validator(output)
    if output['confidence']['grade']=='unavailable' or _utc(output['generatedAt'])!=issue:
        raise ValueError('only actual available issued output can be captured')
    from .artifacts import _artifact_from_payload
    artifact=_artifact_from_payload(record['artifact'])
    expected='earthship-thermal-model/v6' if temperature_version==2 else 'earthship-thermal-model/v5'
    if artifact.schema!=expected:raise ValueError('origin artifact sensor contract differs')
    _artifact_payload(artifact,output)
    _runtime(record['runtime'])
    if not isinstance(record['current'],dict):raise ValueError('original current state required')
    epochs,selected=_temperatures(record['origin_temperatures'],record['current'],
                                 issued_at=issue,published_at=published,version=temperature_version)
    if temperature_version==2 and epochs!={role:info['sensor_epoch'] for role,info in artifact.data_manifest['temperature_evidence']['roles'].items()}:
        raise ValueError('origin hardware phase differs from fitted source')
    if epochs!=record['source_epochs']:raise ValueError('original sensor epochs differ')
    for role,field in (('air','hallwayF'),('mass','massF')):
        if not math.isclose(_number(output['current'][field]),selected[role],rel_tol=0,abs_tol=.00051):
            raise ValueError('issued state differs from selected native initial state')
    _actions(record['known_actions'],issue)
    if len(_canonical(record))>1000000:raise ValueError('origin capture exceeds bound')
    return record


def build_origin_capture(*,output,artifact,snapshot,rows,current,origin_temperatures,
                         runtime,inputs_available_at,published_at,known_actions=None):
    """Detach one original observation with exact source and runtime bindings."""
    return _build_origin_capture(output=output,artifact=artifact,snapshot=snapshot,rows=rows,
        current=current,origin_temperatures=origin_temperatures,runtime=runtime,
        inputs_available_at=inputs_available_at,published_at=published_at,known_actions=known_actions,
        schema=SCHEMA,validator=validate_origin_capture)


def build_sensor_origin_capture(**kwargs):
    return _build_origin_capture(**kwargs,schema=SENSOR_SCHEMA,validator=validate_sensor_origin_capture,temperature_version=2)


def build_sensor_release_origin_capture(**kwargs):
    return _build_origin_capture(**kwargs,schema=SENSOR_RELEASE_SCHEMA,validator=validate_sensor_release_origin_capture,temperature_version=2)


def build_release_origin_capture(**kwargs):
    return _build_origin_capture(**kwargs, schema=RELEASE_SCHEMA, validator=validate_release_origin_capture)


def _build_origin_capture(*,output,artifact,snapshot,rows,current,origin_temperatures,
                         runtime,inputs_available_at,published_at,known_actions=None,schema,validator,temperature_version=1):
    issue=_utc(output['generatedAt']);published=_utc(published_at)
    values=dict(output=output,artifact=_artifact_payload(artifact,output),
        raw_forecast=snapshot,forecast_rows=rows,current=current,
        origin_temperatures=origin_temperatures,runtime=runtime,known_actions=known_actions)
    # Serialize once to detach caller state and normalize all aware clocks.
    values=json.loads(_canonical(values))
    epochs,_=_temperatures(values['origin_temperatures'],values['current'],
                           issued_at=issue,published_at=published,version=temperature_version)
    values['source_epochs']=epochs
    record=dict(schema=schema,issued_at=issue.isoformat(),
        inputs_available_at=_utc(inputs_available_at).isoformat(),published_at=published.isoformat(),
        sha256={name:sha256(_canonical(value)).hexdigest() for name,value in values.items()},**values)
    return validator(record)



def _private_file(path):
    info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
            stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size>256000):
        raise ValueError('owned bounded private origin archive required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        if (opened.st_dev,opened.st_ino)!=(info.st_dev,info.st_ino):
            raise ValueError('origin archive changed during read')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(256001)
    finally:os.close(fd)
    if len(raw)!=info.st_size:raise ValueError('origin archive size changed')
    return raw


def _object(pairs):
    value={}
    for key,entry in pairs:
        if key in value:raise ValueError('duplicate origin archive key')
        value[key]=entry
    return value


def read_origin_capture(path):
    return _read_origin_capture(path, validate_origin_capture)


def read_sensor_origin_capture(path):
    return _read_origin_capture(path,validate_sensor_origin_capture)


def read_sensor_release_origin_capture(path):
    return _read_origin_capture(path,validate_sensor_release_origin_capture)


def read_release_origin_capture(path):
    return _read_origin_capture(path, validate_release_origin_capture)


def read_observed_origin_capture(path):
    return _read_origin_capture(path, validate_observed_origin_capture)


def _read_origin_capture(path, validator):
    from .forcing_capture import _private_directory
    path=Path(path)
    _private_directory(path.parent)
    compressed=_private_file(path)
    try:
        with gzip.GzipFile(fileobj=BytesIO(compressed)) as stream:raw=stream.read(1000001)
    except (OSError,EOFError):raise ValueError('origin archive compression invalid') from None
    if len(raw)>1000000:raise ValueError('origin archive decoded size exceeds bound')
    def reject(_):raise ValueError('nonfinite origin archive JSON')
    try:record=json.loads(raw,object_pairs_hook=_object,parse_constant=reject)
    except (json.JSONDecodeError,UnicodeDecodeError):raise ValueError('origin archive JSON invalid') from None
    return validator(record)


def write_origin_capture(directory,record):
    """Publish immutable private v1 evidence only."""
    return _write_origin_capture(directory, record, validate_origin_capture, 'v1')


def write_sensor_origin_capture(directory,record):
    return _write_origin_capture(directory,record,validate_sensor_origin_capture,'v3')


def write_sensor_release_origin_capture(directory,record):
    return _write_origin_capture(directory,record,validate_sensor_release_origin_capture,'v4')


def write_release_origin_capture(directory, record):
    return _write_origin_capture(directory, record, validate_release_origin_capture, 'v2')


def write_observed_origin_capture(directory, record):
    validate_observed_origin_capture(record)
    if record['schema']==SENSOR_RELEASE_SCHEMA:return write_sensor_release_origin_capture(directory,record)
    if record['schema']==SENSOR_SCHEMA:return write_sensor_origin_capture(directory,record)
    return (write_release_origin_capture(directory, record) if record['schema'] == RELEASE_SCHEMA
        else write_origin_capture(directory, record))


def _write_origin_capture(directory, record, validator, suffix):
    """Publish immutable private evidence only; no household API is called."""
    from .forcing_capture import _private_directory
    root=_private_directory(Path(directory))
    raw=_canonical(validator(record))
    compressed=gzip.compress(raw,mtime=0)
    if len(compressed)>256000:raise ValueError('compressed origin archive exceeds bound')
    issued=_utc(record['issued_at'])
    month=root/issued.strftime('%Y-%m')
    try:month.mkdir(mode=0o700)
    except FileExistsError:pass
    _private_directory(month)
    target=month/(issued.strftime('%Y%m%dT%H%M%SZ')+'-'+record['sha256']['output'][:16]+'-origin-'+suffix+'.json.gz')
    temporary=month/('.origin-'+uuid4().hex+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(compressed);stream.flush();os.fsync(stream.fileno())
        try:os.link(temporary,target,follow_symlinks=False)
        except FileExistsError:
            if _private_file(target)!=compressed:
                raise ValueError('original capture identity has different content')
        directory_fd=os.open(month,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:temporary.unlink(missing_ok=True)
    return target


def _source_bytes(path,*,maximum):
    """Read stable source/executable bytes; never read credentials or configs."""
    try:info=path.lstat()
    except OSError:raise ValueError('runtime source unavailable') from None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0,os.getuid()) or
            info.st_mode & 0o022 or info.st_size>maximum or path.resolve()!=path):
        raise ValueError('bounded non-writable runtime source required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (before.st_dev,before.st_ino)!=(info.st_dev,info.st_ino):
            raise ValueError('runtime source changed')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(maximum+1)
        after=os.fstat(fd)
    finally:os.close(fd)
    if (len(raw)!=info.st_size or len(raw)>maximum or
            (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(
                after.st_size,after.st_mtime_ns,after.st_ctime_ns)):
        raise ValueError('runtime source changed while reading')
    return raw


def build_runtime_binding(runtime_root,revision_paths):
    """Bind the actual executing interpreter/dependencies and publication sources.

    The caller supplies its declared prediction closure. Source code, not a
    mutable artifact's training revision, determines this publication identity.
    """
    import sys
    import numpy
    import scipy
    import psycopg2
    root=Path(runtime_root).resolve(strict=True)
    if (not isinstance(revision_paths,(tuple,list)) or not 1<=len(revision_paths)<=63 or
            any(not isinstance(name,str) for name in revision_paths) or
            len(set(revision_paths))!=len(revision_paths) or 'thermal_intel.py' not in revision_paths):
        raise ValueError('unique declared prediction closure required')
    manifest={};digest=sha256()
    for name in revision_paths:
        relative=PurePosixPath(name)
        if (relative.is_absolute() or str(relative)!=name or not name.endswith('.py') or
                any(part in ('.','..') for part in relative.parts)):
            raise ValueError('runtime source path invalid')
        raw=_source_bytes(root/name,maximum=2000000)
        encoded=name.encode('utf-8')
        digest.update(len(encoded).to_bytes(4,'big'));digest.update(encoded)
        digest.update(len(raw).to_bytes(8,'big'));digest.update(raw)
        manifest[name]=sha256(raw).hexdigest()
    observer='thermal_model/origin_capture.py'
    manifest[observer]=sha256(_source_bytes(root/observer,maximum=2000000)).hexdigest()
    interpreter=Path(sys.executable).resolve(strict=True)
    record=dict(schema='earthship-thermal-runtime-binding/v1',code_revision=digest.hexdigest(),
        observer_revision=manifest[observer],
        interpreter_sha256=sha256(_source_bytes(interpreter,maximum=64000000)).hexdigest(),
        python_version='.'.join(map(str,sys.version_info[:3])),
        dependencies=dict(numpy=numpy.__version__,scipy=scipy.__version__,
                          psycopg2=psycopg2.__version__.split()[0]),source_manifest=manifest)
    _runtime(record)
    # Seal one coherent closure, refusing updates across the collection window.
    for name,expected in manifest.items():
        if sha256(_source_bytes(root/name,maximum=2000000)).hexdigest()!=expected:
            raise ValueError('runtime source changed across binding capture')
    if sha256(_source_bytes(interpreter,maximum=64000000)).hexdigest()!=record['interpreter_sha256']:
        raise ValueError('runtime interpreter changed across binding capture')
    return record
