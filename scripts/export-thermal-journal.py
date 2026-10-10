#!/usr/bin/env python3
"""Explicit guarded private journal export; never restore, install or release."""
import argparse,json,os,shutil,stat,subprocess,sys
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import psycopg2
from psycopg2.extensions import parse_dsn,make_dsn
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'openhab/scripts'))
from thermal_model import airflow_migration
from thermal_model.capture_guard import verify_resource_limits,verify_host_headroom,run_guarded_capture
from thermal_model.capture_readers import bounded_journal_dsn
from thermal_model.forcing_capture import _private_directory,_canonical
from thermal_model.runtime_bundle import _owned_bytes,_write_private,_sync_directory
from thermal_model.environment_bundle import _pacer
from thermal_model.rollback import _rename_new
from thermal_model.graduation_policy import _utc,_sha
from thermal_journal_export_bounds import bounded_table_proofs
from thermal_journal_dump import dump_journal
from thermal_journal_transfer import prepare_journal_transfer,read_journal_transfer

SCHEMA='earthship-thermal-journal-source-export/v1'
RECEIPT_FIELDS={'status','source_receipt_sha256','restored','installed','release_authorized'}


def _identity(dsn_file,root,version):
    if version not in ('v1','v2'):raise ValueError('explicit journal source schema required')
    path=Path(dsn_file);_private_directory(path.parent);_private_directory(root)
    if not path.is_absolute() or path.resolve()!=path or path.is_relative_to(root) or root==path.parent:
        raise ValueError('separate resolved private journal configuration required')
    raw=_owned_bytes(path,4096);dsn=bounded_journal_dsn(raw.decode().strip())
    info=path.lstat()
    identity=dict(configuration_sha256=sha256(raw).hexdigest(),device=info.st_dev,inode=info.st_ino,
        size=info.st_size,mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns,destination=str(root),source_schema=version)
    return dsn,sha256(_canonical(identity)).hexdigest()


def _context(dsn_file,destination,version):
    root=_private_directory(Path(destination))
    if any(root.iterdir()):raise ValueError('new empty journal export destination required')
    dsn,digest=_identity(dsn_file,root,version);params=parse_dsn(dsn)
    params['options']='-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000 -c idle_in_transaction_session_timeout=70000'
    return make_dsn(**params),params,root,digest


def _source_pin(path,maximum,pace):
    """Enforce remaining code-byte allowance on the descriptor, including EOF."""
    before=path.lstat()
    def metadata(info):
        return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_uid,info.st_mode)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid not in (0,os.getuid()) or
            before.st_mode & 0o022 or before.st_size>maximum or path.resolve()!=path):
        raise ValueError('bounded stable export source required')
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    count=0;digest=sha256()
    try:
        if metadata(os.fstat(descriptor))!=metadata(before):raise ValueError('export source changed before read')
        while True:
            amount=min(65536,before.st_size-count+1);pace.reserve(amount)
            block=os.read(descriptor,amount)
            if not block:break
            count+=len(block)
            if count>before.st_size or count>maximum:raise ValueError('export source grew beyond allowance')
            digest.update(block)
        if (count!=before.st_size or metadata(os.fstat(descriptor))!=metadata(before) or
                metadata(path.lstat())!=metadata(before)):raise ValueError('export source changed during read')
    finally:os.close(descriptor)
    return {'bytes':count,'sha256':digest.hexdigest()}


def _source_revision():
    from thermal_intel import _release_runtime_paths
    names=['openhab/scripts/'+name for name in _release_runtime_paths()]
    names+=['openhab/scripts/thermal_model/'+name+'.py' for name in ('environment_bundle','runtime_bundle','rollback','capture_guard','capture_readers','training_inputs','airflow_migration')]
    names+=['scripts/'+name for name in ('export-thermal-journal.py','thermal_journal_export_bounds.py','thermal_journal_dump.py','thermal_journal_transfer.py')]
    pace=_pacer(1048576);pins=[];total=0
    for name in dict.fromkeys(names):
        path=ROOT/name
        pin=_source_pin(path,min(2000000,4000000-total),pace);total+=pin['bytes']
        if pin['bytes']>2000000 or total>4000000:raise ValueError('bounded journal export source closure required')
        pins.append([name,pin])
    return sha256(_canonical(pins)).hexdigest()


def _worker(dsn_file,destination,version,expected):
    dsn,params,root,digest=_context(dsn_file,destination,version)
    if digest!=expected:raise ValueError('journal export configuration changed')
    revision=_source_revision();_sha(revision)
    stage=root/('.source-export-'+uuid4().hex);stage.mkdir(mode=0o700)
    try:
        source=psycopg2.connect(dsn,connect_timeout=3)
        try:
            source.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
            with source.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout='5s'")
                cursor.execute("SET LOCAL lock_timeout='1s'")
                cursor.execute('LOCK TABLE thermal_intel.action_events, thermal_intel.message_receipts, thermal_intel.mode_events IN ACCESS SHARE MODE')
                cursor.execute("SELECT current_user,pg_get_userbyid(n.nspowner),r.rolsuper,r.rolbypassrls,current_setting('transaction_read_only'),current_setting('transaction_isolation') FROM pg_catalog.pg_namespace n JOIN pg_catalog.pg_roles r ON r.rolname=current_user WHERE n.nspname='thermal_intel'")
                role,owner,superuser,bypass,readonly,isolation=cursor.fetchone()
                if (role!=params['user'] or role==owner or superuser is not False or bypass is not False or
                        readonly!='on' or isolation!='repeatable read'):raise ValueError('restricted read-only journal source required')
                fingerprint=airflow_migration._fingerprint(cursor,runtime_role=role,expected_owner=owner)
                selected=airflow_migration.LEGACY_FINGERPRINT if version=='v1' else airflow_migration.V2_FINGERPRINT
                if fingerprint!=selected:raise ValueError('exact selected journal source schema required')
                cursor.execute('SELECT pg_export_snapshot()');snapshot=cursor.fetchone()[0]
            observed=_utc(datetime.now(timezone.utc));proofs=bounded_table_proofs(source)
            archive=stage/'journal.dump';dump=dump_journal(target=archive,params=params,snapshot=snapshot)
        finally:
            try:source.rollback()
            finally:source.close()
        packages=stage/'transfer';packages.mkdir(mode=0o700)
        package=prepare_journal_transfer(archive=archive,directory=packages,source_schema=version,
            runtime_role=role,table_proofs=proofs,exported_at=observed,source_code_revision=revision)
        transferred=read_journal_transfer(package)
        if transferred['archive_sha256']!=dump['sha256'] or transferred['archive_bytes']!=dump['bytes']:
            raise ValueError('retained archive differs from original dump stream')
        if _source_revision()!=revision or _identity(dsn_file,root,version)[-1]!=expected:
            raise ValueError('journal source code or configuration changed')
        prepared=_utc(datetime.now(timezone.utc))
        if prepared<observed:raise ValueError('journal export clock moved backwards')
        record=dict(schema=SCHEMA,observed_at=observed.isoformat(),prepared_at=prepared.isoformat(),
            source_schema_version=version,source_schema_fingerprint=fingerprint,runtime_role=role,
            snapshot_identity=snapshot,source_code_revision=revision,configuration_binding_sha256=expected,
            archive_sha256=dump['sha256'],archive_bytes=dump['bytes'],table_proofs=proofs,
            transfer_sha256=transferred['transfer_sha256'],source_snapshot_observed=True,
            source_export_authenticated=False,restored=False,installed=False,release_authorized=False,automatic_actuation=False)
        record['source_receipt_sha256']=sha256(_canonical(record)).hexdigest()
        _write_private(stage/'source-receipt.json',_canonical(record));archive.unlink()
        _sync_directory(stage);_rename_new(stage,root/record['source_receipt_sha256']);_sync_directory(root)
        return dict(status='journal_export_prepared',source_receipt_sha256=record['source_receipt_sha256'],restored=False,installed=False,release_authorized=False)
    finally:
        if stage.exists():shutil.rmtree(stage)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal-dsn-file',required=True,type=Path)
    parser.add_argument('--destination',required=True,type=Path)
    parser.add_argument('--source-schema',required=True,choices=('v1','v2'))
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--expected-context-digest',help=argparse.SUPPRESS)
    args=parser.parse_args(argv)
    try:
        if not args.check_only and os.environ.get('EARTHSHIP_THERMAL_JOURNAL_EXPORT')!='1':raise ValueError('explicit journal export intent required')
        verify_resource_limits()
        context=_context(args.journal_dsn_file,args.destination,args.source_schema)
        if args.check_only:
            if args.worker:raise ValueError('invalid check-only worker')
            receipt=dict(status='journal_export_paths_verified',restored=False,installed=False,release_authorized=False)
        elif args.worker:
            if (os.environ.get('EARTHSHIP_GUARDED_CAPTURE_WORKER')!='1' or
                    os.environ.get('EARTHSHIP_REMOTE_QUALIFICATION_FIT')!='0' or os.getpriority(os.PRIO_PROCESS,0)<15):
                raise ValueError('guarded journal source worker required')
            verify_host_headroom()
            receipt=_worker(args.journal_dsn_file,args.destination,args.source_schema,args.expected_context_digest)
            _write_private(args.destination/'export-command-receipt.json',_canonical(receipt));return 0
        else:
            if run_guarded_capture([sys.executable,str(Path(__file__).resolve()),'--journal-dsn-file',str(args.journal_dsn_file),
                '--destination',str(args.destination),'--source-schema',args.source_schema,'--worker','--expected-context-digest',context[-1]],seconds=90)!=0:
                raise ValueError('journal export worker refused')
            from thermal_model.origin_capture import _object
            receipt=json.loads(_owned_bytes(args.destination/'export-command-receipt.json',4096),object_pairs_hook=_object)
            if (set(receipt)!=RECEIPT_FIELDS or receipt['status']!='journal_export_prepared' or
                    any(receipt[key] is not False for key in ('restored','installed','release_authorized'))):raise ValueError('closed journal export command receipt required')
            _sha(receipt['source_receipt_sha256'])
    except (OSError,RuntimeError,TypeError,ValueError,subprocess.SubprocessError,psycopg2.Error):
        print('journal export withheld; check private source configuration, host caps, snapshot and archive bounds',file=sys.stderr);return 2
    print(json.dumps(receipt,sort_keys=True,separators=(',',':')));return 0


if __name__=='__main__':raise SystemExit(main())
