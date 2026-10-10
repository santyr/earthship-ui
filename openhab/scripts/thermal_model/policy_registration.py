"""Immutable local preregistration backed by complete original source packets.

Registration proves how development thresholds were derived, not model fitness,
weather qualification, action causality or production permission. Raw captures
and receipts remain necessary for every replay. The operator-owned archive is
not a cryptographic timestamp service or an authority against its owner.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path,PurePosixPath
import stat
from uuid import uuid4

from thermal_model.graduation_policy import validate_policy,RECORD_FIELDS,_utc
from thermal_model.forcing_capture import _canonical,_private_directory
from thermal_model.origin_capture import read_observed_origin_capture as read_origin_capture
from thermal_model.origin_capture import write_observed_origin_capture as write_origin_capture
from thermal_model.graduation_evidence import _score_origin_record

SCHEMA='earthship-thermal-policy-registration/v1'
SENSOR_SCHEMA='earthship-thermal-policy-registration/v2'
INSTALLED_SCHEMA='earthship-installed-shade-policy-registration/v1'
INSTALLED_CANDIDATE_SCHEMA='earthship-installed-shade-candidate/v1'
CALIBRATED_SCHEMA='earthship-installed-shade-policy-registration/v2'
CALIBRATED_CANDIDATE_SCHEMA='earthship-installed-shade-candidate/v2'
RAW_CALIBRATED_SCHEMA='earthship-installed-shade-policy-registration/v3'
RAW_CALIBRATED_CANDIDATE_SCHEMA='earthship-installed-shade-candidate/v3'
RAW_DEVELOPMENT_CONTRACT='earthship-installed-shade-score-sources/v2'
SENSOR_SEMANTICS='declared_hardware_phase'
SOURCE_FIELDS={'origin_path','publication','horizon_hours','outcome','recent_cycle_grid'}
FIELDS={'schema','registered_at','policy','development_sources','development_origins',
        'release_authorized','registration_sha256'}
MAX_BYTES=4000000


def _clock():return datetime.now(timezone.utc)


def _digest(value):return sha256(_canonical(value)).hexdigest()


def _chronology(policy,registered):
    if not _utc(policy['declared_at'])<=registered<_utc(policy['intervals']['holdout_start']):
        raise ValueError('actual registration must follow declaration and precede untouched holdout')
    if registered>=_utc(policy['intervals']['prospective_start']):
        raise ValueError('prospective release interval must follow actual registration')


def _relative(name):
    if not isinstance(name,str):raise ValueError('relative archived source path required')
    path=PurePosixPath(name)
    if path.is_absolute() or str(path)!=name or '..' in path.parts or not name.startswith('sources/'):
        raise ValueError('relative archived source path invalid')
    return name


def _read_calibrated_development_origin(path):
    from .installed_shade_origin import read_issued_capture
    from .installed_shade_calibrated_origin import read_calibrated_capture
    if path.name.endswith('.installed-shade-origin-v1.json'):return read_issued_capture(path)
    if path.name.endswith('.installed-shade-origin-v2.json'):return read_calibrated_capture(path)
    raise ValueError('explicit original installed-domain development source required')


def _score_calibrated_development_origin(record,**values):
    from .installed_shade_origin import score_issued_capture
    from .installed_shade_calibrated_origin import score_calibrated_capture
    if record['schema']=='earthship-installed-shade-origin/v1':return score_issued_capture(record,**values)
    if record['schema']=='earthship-installed-shade-origin/v2':return score_calibrated_capture(record,**values)
    raise ValueError('original installed-domain development schema unsupported')


def _write_calibrated_development_origin(directory,record):
    from .installed_shade_origin import write_issued_capture
    from .installed_shade_calibrated_origin import write_calibrated_capture
    if record['schema']=='earthship-installed-shade-origin/v1':return write_issued_capture(directory,record)
    if record['schema']=='earthship-installed-shade-origin/v2':return write_calibrated_capture(directory,record)
    raise ValueError('original installed-domain development schema unsupported')


def _registration_schema(version):
    return {1:SCHEMA,2:SENSOR_SCHEMA,3:INSTALLED_SCHEMA,4:CALIBRATED_SCHEMA}[version]


def _candidate_schema(version):
    return CALIBRATED_CANDIDATE_SCHEMA if version==4 else INSTALLED_CANDIDATE_SCHEMA


def _score_sources(sources,policy,registered,*,root=None,version=1):
    if not isinstance(sources,list) or not 1<=len(sources)<=10000:
        raise ValueError('bounded raw development source packets required')
    if len(_canonical(sources))>MAX_BYTES:raise ValueError('development source index exceeds bound')
    reader=read_origin_capture;scorer=_score_origin_record
    if version==3:
        from .installed_shade_origin import read_issued_capture,score_issued_capture
        reader=read_issued_capture;scorer=score_issued_capture
    elif version==4:
        reader=_read_calibrated_development_origin;scorer=_score_calibrated_development_origin
    origins={};scored=[];total_origin_bytes=0
    expected_by_key={(row['issue_at'],row['target_at'],row['horizon_hours']):row for row in policy['development']}
    seen=set()
    for packet in sources:
        if not isinstance(packet,dict) or set(packet)!=SOURCE_FIELDS:
            raise ValueError('complete closed development source packet required')
        name=packet['origin_path']
        if not isinstance(name,str):raise ValueError('original source archive path required')
        if root is not None:name=str(root/_relative(name))
        if name not in origins:
            if len(origins)>=128:raise ValueError('development origin count exceeds bound')
            try:origins[name]=reader(Path(name))
            except (OSError,TypeError):raise ValueError('original development capture unavailable') from None
            total_origin_bytes+=len(_canonical(origins[name]))
            if total_origin_bytes>64000000:raise ValueError('development origin bytes exceed bound')
        record=origins[name]
        supported=({'earthship-installed-shade-origin/v1','earthship-installed-shade-origin/v2'} if version==4 else
            {'earthship-installed-shade-origin/v1'} if version==3 else
            {'earthship-thermal-origin-capture/v3','earthship-thermal-origin-capture/v4'} if version==2 else
            {'earthship-thermal-origin-capture/v1','earthship-thermal-origin-capture/v2'})
        if record['schema'] not in supported:raise ValueError('development origin sensor contract differs')
        result=scorer(record,**{key:packet[key] for key in SOURCE_FIELDS-{'origin_path'}},assessed_at=registered)
        expected_schema=('earthship-installed-shade-source-scored-pair/v2' if version==4 and record['schema'].endswith('/v2') else
            'earthship-installed-shade-source-scored-pair/v1' if version>=3 else 'earthship-thermal-source-scored-pair/v2')
        if version>1 and result.get('schema')!=expected_schema:
            raise ValueError('development score sensor contract differs')
        row=result['scored_pair']
        if row['sensor_epochs']!=policy['candidate']['sensor_epochs']:
            raise ValueError('development source epochs differ from frozen candidate')
        baseline={key:row[key] for key in RECORD_FIELDS}
        identity=(row['issue_at'],row['target_at'],row['horizon_hours'])
        if identity in seen or _canonical(expected_by_key.get(identity))!=_canonical(baseline):
            raise ValueError('policy development differs from original source-derived baselines')
        seen.add(identity);scored.append(baseline)
    expected=sorted(policy['development'],key=lambda row:(row['issue_at'],row['horizon_hours']))
    actual=sorted(scored,key=lambda row:(row['issue_at'],row['horizon_hours']))
    if _canonical(expected)!=_canonical(actual):
        raise ValueError('policy development differs from original source-derived baselines')
    return origins


def _read_private(path):
    _private_directory(path.parent)
    try:info=path.lstat()
    except OSError:raise ValueError('private policy receipt unavailable') from None
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or
            stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size>MAX_BYTES):
        raise ValueError('owned bounded private policy receipt required')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if (before.st_dev,before.st_ino)!=(info.st_dev,info.st_ino):raise ValueError('policy receipt changed')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(MAX_BYTES+1)
        after=os.fstat(fd)
    finally:os.close(fd)
    if len(raw)!=info.st_size or (before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(
            after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('policy receipt changed during read')
    from .replay_budget import observe_source_bytes
    observe_source_bytes(path,raw)
    def object_pairs(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate policy receipt key')
            result[key]=value
        return result
    def constant(_):raise ValueError('nonfinite policy receipt')
    try:return json.loads(raw,object_pairs_hook=object_pairs,parse_constant=constant)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('policy receipt JSON invalid') from None


def read_registered_policy(path):
    return _read_registered_policy(path,version=1)


def read_sensor_registered_policy(path):
    return _read_registered_policy(path,version=2)


def read_installed_shade_registered_policy(path):
    return _read_registered_policy(path,version=3)


def read_calibrated_installed_shade_registered_policy(path):
    return _read_registered_policy(path,version=4)


def _installed_contract(policy):
    if type(policy['candidate']['active_parameter_count']) is not int or policy['candidate']['active_parameter_count']!=10:
        raise ValueError('installed candidate requires its exact ten-parameter contract')


def _read_registered_policy(path,*,version):
    """Reproduce thresholds from sealed original captures and native receipts."""
    path=Path(path);record=_read_private(path)
    expected_fields=FIELDS|({'sensor_epoch_semantics'} if version>1 else set())|({'candidate_schema'} if version>=3 else set())
    schema=_registration_schema(version)
    if (not isinstance(record,dict) or set(record)!=expected_fields or record['schema']!=schema or
            record['release_authorized'] is not False):raise ValueError('closed preregistration receipt required')
    if version>1 and record['sensor_epoch_semantics']!=SENSOR_SEMANTICS:raise ValueError('native preregistration phase semantics required')
    body={key:value for key,value in record.items() if key!='registration_sha256'}
    if _digest(body)!=record['registration_sha256']:raise ValueError('policy receipt digest differs')
    policy=validate_policy(record['policy']);registered=_utc(record['registered_at'])
    if version>=3:
        _installed_contract(policy)
        if record['candidate_schema']!=_candidate_schema(version):raise ValueError('installed candidate namespace differs')
    _chronology(policy,registered)
    if registered>_clock():raise ValueError('policy registration is in the future')
    origins=_score_sources(record['development_sources'],policy,registered,root=path.parent,version=version)
    actual={str(Path(name).relative_to(path.parent)):_digest(value) for name,value in origins.items()}
    if actual!=record['development_origins']:raise ValueError('archived origin manifest differs')
    return record


def register_policy(directory,policy,development_sources):
    return _register_policy(directory,policy,development_sources,version=1)


def register_sensor_policy(directory,policy,development_sources):
    return _register_policy(directory,policy,development_sources,version=2)


def register_installed_shade_policy(directory,policy,development_sources):
    return _register_policy(directory,policy,development_sources,version=3)


def register_calibrated_installed_shade_policy(directory,policy,development_sources):
    return _register_policy(directory,policy,development_sources,version=4)


def _register_policy(directory,policy,development_sources,*,version):
    """Seal a policy before release intervals using the actual registration clock.

    No date/active override argument is accepted. Existing content can only be
    repeated unchanged; a failed attempt never publishes a registration receipt.
    """
    root=_private_directory(Path(directory));validate_policy(policy)
    if version>=3:_installed_contract(policy)
    registered=_clock();_chronology(policy,registered)
    origins=_score_sources(development_sources,policy,registered,version=version)
    source_root=root/'sources'
    try:source_root.mkdir(mode=0o700)
    except FileExistsError:pass
    _private_directory(source_root)
    writer=write_origin_capture
    if version==3:
        from .installed_shade_origin import write_issued_capture
        writer=write_issued_capture
    elif version==4:writer=_write_calibrated_development_origin
    copied={name:writer(source_root,record) for name,record in origins.items()}
    packets=[{**packet,'origin_path':str(copied[packet['origin_path']].relative_to(root))} for packet in development_sources]
    body=dict(schema=_registration_schema(version),**({} if version==1 else dict(sensor_epoch_semantics=SENSOR_SEMANTICS)),**(dict(candidate_schema=_candidate_schema(version)) if version>=3 else {}),registered_at=registered.isoformat(),policy=policy,
        development_sources=packets,
        development_origins={str(copied[name].relative_to(root)):_digest(record) for name,record in origins.items()},
        release_authorized=False)
    # Refuse a holdout that began while source verification/copying ran.
    _chronology(policy,_clock())
    target=root/(policy['policy_sha256']+('.installed-shade-registration-v2.json' if version==4 else '.installed-shade-registration-v1.json' if version==3 else '.registration-v2.json' if version==2 else '.registration.json'))
    body['registration_sha256']=_digest(body);raw=_canonical(body)
    if len(raw)>MAX_BYTES:raise ValueError('policy receipt exceeds bounded size')
    temporary=root/('.registration-'+uuid4().hex+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        _chronology(policy,_clock())
        try:os.link(temporary,target,follow_symlinks=False)
        except FileExistsError:
            previous=_read_registered_policy(target,version=version)
            def content(record):return {key:value for key,value in record.items() if key not in ('registered_at','registration_sha256')}
            if content(previous)!=content(body):raise ValueError('existing policy receipt has different content')
        fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temporary.unlink(missing_ok=True)
    return target



RAW_REGISTRATION_FIELDS=FIELDS|{'sensor_epoch_semantics','candidate_schema','source_contract','development_source_bindings'}
RAW_REGISTRATION_SUFFIX='.installed-shade-registration-v3.json'


def _score_raw_development_sources(sources,policy,registered):
    """Reproduce development baselines from original query archives.

    Baselines may precede the final candidate freeze. Only same-phase original
    persistence/recent-cycle errors are used to derive thresholds, never release
    scores from another revision. Raw query replay is mandatory.
    """
    from .installed_shade_qualification import _score_packets
    if len(_canonical(sources))>MAX_BYTES:
        raise ValueError('bounded original raw development index required')
    scored=_score_packets(sources,assessed_at=registered,version=4)
    if scored.get('raw_native_score_sources') is not True:
        raise ValueError('original raw development query sources required')
    actual=[]
    for row in scored['rows']:
        if row['sensor_epochs']!=policy['candidate']['sensor_epochs']:
            raise ValueError('raw development hardware phase differs from frozen candidate')
        actual.append({key:row[key] for key in RECORD_FIELDS})
    order=lambda row:(row['issue_at'],row['horizon_hours'])
    if _canonical(sorted(actual,key=order))!=_canonical(sorted(policy['development'],key=order)):
        raise ValueError('policy development differs from original raw source-derived baselines')
    bindings=scored['bindings']
    if len({binding['original_capture_sha256'] for binding in bindings})>128:
        raise ValueError('development origin count exceeds bound')
    manifest={Path(reference['raw_score_sources_path']).name:binding['raw_score_sources_sha256']
        for reference,binding in zip(sources,bindings)}
    if len(manifest)!=len(sources):raise ValueError('duplicate original raw development source address')
    return dict(development_origins=manifest,development_source_bindings=bindings)


def _raw_registration_path(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:
        raise ValueError('resolved private raw preregistration path required')
    return path


def _read_raw_installed_registration(path,*,_version=3):
    """Replay the sealed original development queries, never a support cache."""
    schema,candidate_schema,contract,suffix,scorer=_raw_registration_profile(_version)
    path=_raw_registration_path(path);record=_read_private(path)
    if (not isinstance(record,dict) or set(record)!=RAW_REGISTRATION_FIELDS or
            record['schema']!=schema or record['candidate_schema']!=candidate_schema or
            record['source_contract']!=contract or record['sensor_epoch_semantics']!=SENSOR_SEMANTICS or
            record['release_authorized'] is not False or
            _digest({k:v for k,v in record.items() if k!='registration_sha256'})!=record['registration_sha256']):
        raise ValueError('closed original raw preregistration receipt required')
    policy=validate_policy(record['policy']);_installed_contract(policy)
    if path.name!=policy['policy_sha256']+suffix:
        raise ValueError('raw preregistration address differs')
    registered=_utc(record['registered_at']);_chronology(policy,registered)
    if registered>_utc(_clock()):raise ValueError('raw registration is in the future')
    proof=scorer(record['development_sources'],policy,registered)
    if any(_canonical(proof[key])!=_canonical(record[key]) for key in
            ('development_origins','development_source_bindings')):
        raise ValueError('sealed raw development bindings differ from original replay')
    return record


def _register_raw_installed_policy(directory,policy,development_sources,*,_version=3):
    """Seal raw-derived thresholds before release using the actual clock.

    Original archive locators remain absolute and unchanged. They grant no
    authority themselves: readback must replay the original retained bytes.
    """
    from .installed_shade_calibration import _persist
    schema,candidate_schema,contract,suffix,scorer=_raw_registration_profile(_version)
    root=_private_directory(Path(directory));policy,sources=deepcopy((policy,development_sources))
    validate_policy(policy);_installed_contract(policy)
    registered=_utc(_clock());_chronology(policy,registered)
    proof=scorer(sources,policy,registered)
    body=dict(schema=schema,sensor_epoch_semantics=SENSOR_SEMANTICS,
        candidate_schema=candidate_schema,source_contract=contract,
        registered_at=registered.isoformat(),policy=policy,development_sources=sources,
        **proof,release_authorized=False)
    body['registration_sha256']=_digest(body)
    if len(_canonical(body))>MAX_BYTES:raise ValueError('raw preregistration receipt exceeds bound')
    target=root/(policy['policy_sha256']+suffix)
    _chronology(policy,_utc(_clock()))
    def guard():
        _chronology(policy,_utc(_clock()))
        if _version==4:
            actual=scorer(sources,policy,registered)
            if _canonical(actual)!=_canonical(proof):raise ValueError('original development sources changed during sealing')
            _chronology(policy,_utc(_clock()))
            from .replay_budget import check_shared_budget
            check_shared_budget()
    if target.exists():
        previous=_read_raw_installed_registration(target,_version=_version)
        def content(record):return {key:value for key,value in record.items() if key not in ('registered_at','registration_sha256')}
        if _canonical(content(previous))!=_canonical(content(body)):
            raise ValueError('existing raw preregistration has different original content')
        guard()
        return target
    # This uses the existing immutable owned-private writer. No source files are
    # relocated/rewritten, and no release/active state is produced.
    _chronology(policy,_utc(_clock()))
    target=_persist(root,body,policy['policy_sha256'],suffix,before_publish=guard)
    if _version==4:guard()
    return target


COMPRESSED_REGISTRATION_SCHEMA='earthship-installed-shade-policy-registration/v4'
COMPRESSED_REGISTRATION_CANDIDATE_SCHEMA='earthship-installed-shade-candidate/v5'
COMPRESSED_DEVELOPMENT_CONTRACT='earthship-installed-shade-score-sources/v6'


def _score_compressed_development_sources(sources,policy,registered):
    """Replay same-phase original base development baselines before final freeze."""
    from .installed_shade_qualification import score_compressed_source_base_packets
    scored=score_compressed_source_base_packets(sources,assessed_at=registered)
    if scored.get('raw_native_score_sources') is not True or scored.get('raw_native_issue_sources') is not True:
        raise ValueError('complete original development query sources required')
    actual=[]
    for row in scored['rows']:
        if row['sensor_epochs']!=policy['candidate']['sensor_epochs']:
            raise ValueError('development hardware phase differs from frozen candidate')
        actual.append({key:row[key] for key in RECORD_FIELDS})
    order=lambda row:(row['issue_at'],row['horizon_hours'])
    if _canonical(sorted(actual,key=order))!=_canonical(sorted(policy['development'],key=order)):
        raise ValueError('policy development differs from original source-derived baselines')
    bindings=scored['bindings']
    if len({binding['original_capture_sha256'] for binding in bindings})>128:
        raise ValueError('development origin count exceeds bound')
    manifest={Path(reference['raw_score_sources_path']).name:binding['raw_score_sources_sha256']
        for reference,binding in zip(sources,bindings)}
    if len(manifest)!=len(sources):raise ValueError('duplicate original development source address')
    return dict(development_origins=manifest,development_source_bindings=bindings)


def _raw_registration_profile(version):
    if type(version) is not int or version not in (3,4):raise ValueError('explicit original development registration profile required')
    if version==3:return RAW_CALIBRATED_SCHEMA,RAW_CALIBRATED_CANDIDATE_SCHEMA,RAW_DEVELOPMENT_CONTRACT,RAW_REGISTRATION_SUFFIX,_score_raw_development_sources
    return (COMPRESSED_REGISTRATION_SCHEMA,COMPRESSED_REGISTRATION_CANDIDATE_SCHEMA,COMPRESSED_DEVELOPMENT_CONTRACT,
        '.installed-shade-registration-v4.json',_score_compressed_development_sources)


def read_raw_calibrated_installed_shade_registered_policy(path):
    return _read_raw_installed_registration(path,_version=3)


def register_raw_calibrated_installed_shade_policy(directory,policy,development_sources):
    return _register_raw_installed_policy(directory,policy,development_sources,_version=3)


def read_compressed_installed_shade_registered_policy(path):
    from .installed_shade_calibration import _source_operation
    return _source_operation(_read_raw_installed_registration,path,_version=4)


def register_compressed_installed_shade_policy(directory,policy,development_sources):
    from .installed_shade_calibration import _raw_packet_digest,_source_operation
    _raw_packet_digest(development_sources)
    return _source_operation(_register_raw_installed_policy,directory,policy,development_sources,_version=4)
