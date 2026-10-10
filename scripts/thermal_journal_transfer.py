"""Bound private journal transfer inputs; never restore, execute or authorize.

Table proofs/schema/role are exporter declarations. This verifies exact file
binding, not their correspondence to a live source or SQL object safety.
"""
from copy import deepcopy
from datetime import datetime,timezone
from hashlib import sha256
import json,os,re,shutil,stat
from pathlib import Path
from uuid import uuid4

from thermal_model.forcing_capture import _canonical,_private_directory
from thermal_model.graduation_policy import _sha,_utc
from thermal_model.origin_capture import _object
from thermal_model.runtime_bundle import _owned_bytes,_write_private,_sync_directory
from thermal_model.rollback import _rename_new
from thermal_model.environment_bundle import _pacer
from thermal_model import airflow_migration

SCHEMA='earthship-thermal-journal-transfer/v1'
TABLES={'message_receipts','action_events','mode_events'}
FLAGS={'disposable_restore_qualified','consumer_qualified','installed','release_authorized'}
FIELDS={'schema','archive_sha256','archive_bytes','source_schema_version','source_schema_fingerprint',
        'runtime_role','table_proofs','exported_at','prepared_at','source_code_revision','transfer_sha256'}|FLAGS
MAX_ARCHIVE_BYTES=32000000
MAX_MANIFEST_BYTES=16000
CHUNK=65536


def _clock():return datetime.now(timezone.utc)


def _fingerprint(version):
    if version=='v1':value=airflow_migration.LEGACY_FINGERPRINT
    elif version=='v2':value=airflow_migration.V2_FINGERPRINT
    else:raise ValueError('explicit journal source schema required')
    return json.loads(_canonical(value))


def _declarations(version,role,proofs,revision):
    fingerprint=_fingerprint(version);_sha(revision)
    if not isinstance(role,str) or re.fullmatch('[a-z_][a-z0-9_]{0,62}',role) is None or role=='postgres':
        raise ValueError('restricted journal reader role required')
    if not isinstance(proofs,dict) or set(proofs)!=TABLES:raise ValueError('all exact journal table proofs required')
    for value in proofs.values():
        if (not isinstance(value,dict) or set(value)!={'rows','sha256'} or
                type(value['rows']) is not int or not 0<=value['rows']<2**63):raise ValueError('bounded table proof required')
        _sha(value['sha256'])
    return fingerprint


def _metadata(info):
    return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)


def _stream(path,pace,output=None,*,expected_metadata=None):
    path=Path(path);_private_directory(path.parent)
    if not path.is_absolute() or path.resolve()!=path:raise ValueError('resolved journal archive path required')
    before=path.lstat()
    if expected_metadata is not None and _metadata(before)!=expected_metadata:
        raise ValueError("journal archive changed since inspection")
    if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or
            stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1 or
            not 5<=before.st_size<=MAX_ARCHIVE_BYTES):raise ValueError('bounded owned private journal archive required')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    count=0;digest=sha256();header=b''
    try:
        if _metadata(os.fstat(descriptor))!=_metadata(before):raise ValueError('journal archive changed before read')
        while True:
            amount=min(CHUNK,before.st_size-count+1);pace.reserve(amount)
            block=os.read(descriptor,amount)
            if not block:break
            count+=len(block)
            if count>before.st_size:raise ValueError('journal archive grew while reading')
            if len(header)<5:header=(header+block)[:5]
            digest.update(block)
            if output is not None:output.write(block)
        if (count!=before.st_size or _metadata(os.fstat(descriptor))!=_metadata(before) or
                _metadata(path.lstat())!=_metadata(before)):raise ValueError('journal archive changed while reading')
        if header!=b'PGDMP':raise ValueError('custom journal archive marker required')
    finally:os.close(descriptor)
    return count,digest.hexdigest(),_metadata(before)


def _rate(value):
    if type(value) is not int or not 1<=value<=1048576:raise ValueError('mandatory bounded journal read pacing required')
    return _pacer(value)


def _verify(directory,pace,*,address_required):
    root=_private_directory(Path(directory))
    if {path.name for path in root.iterdir()}!={'manifest.json','journal.dump'}:raise ValueError('exact transfer membership required')
    def reject(value):raise ValueError('nonfinite journal manifest refused')
    pace.reserve(MAX_MANIFEST_BYTES+1)
    record=json.loads(_owned_bytes(root/'manifest.json',MAX_MANIFEST_BYTES),object_pairs_hook=_object,parse_constant=reject)
    if (not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMA or
            any(record[key] is not False for key in FLAGS)):raise ValueError('closed unqualified journal transfer required')
    fingerprint=_declarations(record['source_schema_version'],record['runtime_role'],record['table_proofs'],record['source_code_revision'])
    if record['source_schema_fingerprint']!=fingerprint:raise ValueError('journal schema declaration differs')
    if not _utc(record['exported_at'])<=_utc(record['prepared_at'])<=_clock():raise ValueError('journal transfer clocks invalid')
    _sha(record['archive_sha256']);_sha(record['transfer_sha256'])
    if type(record['archive_bytes']) is not int:raise ValueError('exact archive size required')
    body={key:value for key,value in record.items() if key!='transfer_sha256'}
    if sha256(_canonical(body)).hexdigest()!=record['transfer_sha256']:raise ValueError('journal transfer manifest changed')
    if address_required and root.name!=record['transfer_sha256']:raise ValueError('journal transfer address differs')
    size,digest,_=_stream(root/'journal.dump',pace)
    if size!=record['archive_bytes'] or digest!=record['archive_sha256']:raise ValueError('journal transfer archive differs')
    return record


def read_journal_transfer(directory,*,max_read_bytes_per_second=1048576):
    return _verify(directory,_rate(max_read_bytes_per_second),address_required=True)


def prepare_journal_transfer(*,archive,directory,source_schema,runtime_role,table_proofs,
                             exported_at,source_code_revision,clock=_clock,max_read_bytes_per_second=1048576):
    pace=_rate(max_read_bytes_per_second)
    fingerprint=_declarations(source_schema,runtime_role,table_proofs,source_code_revision)
    proofs=deepcopy(table_proofs);exported=_utc(exported_at);started=_utc(clock())
    if exported>started:raise ValueError('future journal export declaration refused')
    root=_private_directory(Path(directory));archive=Path(archive)
    # Validate the source stat before creating even a temporary generation.
    info=archive.lstat();_private_directory(archive.parent)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or
            info.st_nlink!=1 or not 5<=info.st_size<=MAX_ARCHIVE_BYTES):raise ValueError('bounded private export required')
    stage=root/('.journal-transfer-'+uuid4().hex);stage.mkdir(mode=0o700)
    try:
        descriptor=os.open(stage/'journal.dump',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(descriptor,'wb') as target:
            size,digest,metadata=_stream(archive,pace,target,expected_metadata=_metadata(info));target.flush();os.fsync(target.fileno())
        prepared=_utc(clock())
        if prepared<started:raise ValueError('journal preparation clock moved backward')
        body=dict(schema=SCHEMA,archive_sha256=digest,archive_bytes=size,source_schema_version=source_schema,
            source_schema_fingerprint=fingerprint,runtime_role=runtime_role,table_proofs=proofs,
            exported_at=exported.isoformat(),prepared_at=prepared.isoformat(),source_code_revision=source_code_revision,
            **{key:False for key in FLAGS})
        body['transfer_sha256']=sha256(_canonical(body)).hexdigest();raw=_canonical(body)
        if len(raw)>MAX_MANIFEST_BYTES:raise ValueError('journal manifest exceeds bound')
        _write_private(stage/'manifest.json',raw);_verify(stage,pace,address_required=False)
        if _metadata(archive.lstat())!=metadata:raise ValueError('original archive changed before transfer publication')
        _sync_directory(stage);target=root/body['transfer_sha256'];_rename_new(stage,target);_sync_directory(root)
        return target
    finally:
        if stage.exists():shutil.rmtree(stage)
