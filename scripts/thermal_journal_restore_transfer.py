"""Explicit off-host disposable journal/consumer rehearsal; no source connection.

Exporter declarations and the complete cold environment remain unqualified.
Only owned disposable database work is performed; never install or release.
"""
from datetime import datetime,timezone
from functools import lru_cache
from hashlib import sha256
import importlib.util,json,os,re,subprocess,sys
from pathlib import Path
from uuid import uuid4

from thermal_journal_transfer import read_journal_transfer
from thermal_model.forcing_capture import _canonical,_private_directory
from thermal_model.graduation_policy import _sha,_utc
from thermal_model.origin_capture import _source_bytes
from thermal_model.runtime_bundle import _write_private,_sync_directory
from thermal_model.rollback import _rename_new

SCHEMA='earthship-thermal-journal-restore-report/v1'
ROOT=Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _live():
    path=ROOT/'scripts/qualify-thermal-journal-live-restore.py'
    spec=importlib.util.spec_from_file_location('journal_restore_backend',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def _docker(command):
    return subprocess.run(['docker',*command],capture_output=True,check=False,timeout=30)


class DisposableBackend:
    def check_archive(self,path):_live().backup._check_journal_archive(path)
    def start(self,name,password,role,token):
        result=_docker(['ps','-a','--filter','name=^/'+name+'$','--format','{{.Names}}'])
        if result.returncode or result.stdout.strip():raise ValueError('disposable name is not unused')
        return _live().disposable_database(name,password,role,ownership_token=token)
    def restore(self,path,params,role,source_schema):
        return _live().restore_and_rehearse(path,params,role,source_schema=source_schema)
    def consumer(self,params,role,runtime,revision):
        return _live().qualify_consumer(params,role,runtime,revision)
    def cleanup(self,name,token):
        if re.fullmatch('thermal-transfer-[0-9a-f]{32}',name) is None or re.fullmatch('[0-9a-f]{32}',token) is None:
            raise ValueError('owned disposable identity required')
        listing=['ps','-a','--filter','name=^/'+name+'$','--format','{{.Names}}']
        result=_docker(listing)
        if result.returncode:raise ValueError('disposable cleanup cannot be observed')
        if not result.stdout.strip():return
        if result.stdout.strip()!=name.encode():raise ValueError('disposable name differs')
        observed=_docker(['inspect','--format','{{.Id}} {{.Name}} {{index .Config.Labels "earthship.thermal.restore-token"}}',name])
        if observed.returncode or len(observed.stdout)>256:raise ValueError('disposable ownership cannot be observed')
        fields=observed.stdout.decode('ascii').split()
        if (len(fields)!=3 or re.fullmatch('[0-9a-f]{64}',fields[0]) is None or
                fields[1]!='/'+name or fields[2]!=token):raise ValueError('disposable ownership label differs')
        identifier=fields[0]
        # Names can be replaced after inspection. Remove only this immutable ID.
        removed=_docker(['rm','--force','--volumes',identifier])
        remaining=_docker(['ps','-a','--no-trunc','--filter','id='+identifier,'--format','{{.ID}}'])
        if removed.returncode or remaining.returncode or remaining.stdout.strip():raise ValueError('owned disposable cleanup incomplete')
        replacement=_docker(listing)
        if replacement.returncode or replacement.stdout.strip():raise ValueError('disposable name replaced during cleanup')


def _interpreter_digest():
    return sha256(_source_bytes(Path(sys.executable).resolve(),maximum=64000000)).hexdigest()


def _consumer(proof,revision):
    if (not isinstance(proof,dict) or proof.get('status')!='installed_consumer_qualified' or
            proof.get('runtime_revision')!=revision or proof.get('connection_read_only') is not True or
            proof.get('runtime_role_verified') is not True or proof.get('legacy_samples_unchanged') is not True or
            type(proof.get('distinct_fixture_observations')) is not int or proof['distinct_fixture_observations']!=6 or
            type(proof.get('legacy_support_rows')) is not int or proof['legacy_support_rows']!=1):
        raise ValueError('complete pinned disposable consumer proof required')
    _sha(proof.get('sample_sha256'))
    return {key:proof[key] for key in ('status','runtime_revision','connection_read_only','runtime_role_verified',
        'legacy_samples_unchanged','distinct_fixture_observations','legacy_support_rows','sample_sha256')}


def qualify_journal_transfer(*,package,consumer_runtime,expected_consumer_revision,
                             expected_interpreter_sha256,proof_directory,clock=lambda:datetime.now(timezone.utc),backend=None):
    # Intent, not proof of location. Select the approved off-host worker first.
    if os.environ.get('EARTHSHIP_REMOTE_JOURNAL_RESTORE')!='1':raise ValueError('explicit off-host journal restore intent required')
    revision=_sha(expected_consumer_revision);interpreter=_sha(expected_interpreter_sha256)
    runtime=_private_directory(Path(consumer_runtime));root=_private_directory(Path(proof_directory))
    package=Path(package)
    if (root==runtime or root.is_relative_to(runtime) or runtime.is_relative_to(root) or
            root==package or root.is_relative_to(package) or package.is_relative_to(root) or any(root.iterdir())):
        raise ValueError('new separate private proof directory required')
    if _interpreter_digest()!=interpreter:raise ValueError('pinned consumer interpreter differs')
    record=read_journal_transfer(package);archive=package/'journal.dump'
    service=DisposableBackend() if backend is None else backend
    service.check_archive(archive)
    name='thermal-transfer-'+uuid4().hex;token=uuid4().hex;attempted=False
    try:
        attempted=True
        params=service.start(name,uuid4().hex,record['runtime_role'],token)
        if service.restore(archive,params,record['runtime_role'],record['source_schema_version'])!=record['table_proofs']:
            raise ValueError('restored rows differ from exporter declarations')
        consumer=_consumer(service.consumer(params,record['runtime_role'],runtime,revision),revision)
        if _interpreter_digest()!=interpreter:raise ValueError('consumer interpreter changed during rehearsal')
    finally:
        if attempted:service.cleanup(name,token)
    if read_journal_transfer(package)!=record:raise ValueError('journal package changed during rehearsal')
    assessed=_utc(clock())
    if assessed<_utc(record['prepared_at']):raise ValueError('restore clock predates its inputs')
    report=dict(schema=SCHEMA,assessed_at=assessed.isoformat(),transfer_sha256=record['transfer_sha256'],
        archive_sha256=record['archive_sha256'],source_schema_version=record['source_schema_version'],
        source_schema_fingerprint=record['source_schema_fingerprint'],consumer_revision=revision,
        consumer_interpreter_sha256=interpreter,consumer_probe=consumer,disposable_cleanup_verified=True,
        restored_rows_match_exporter_declarations=True,disposable_restore_qualified=True,consumer_qualified=True,
        source_export_authenticated=False,cold_environment_qualified=False,journal_recovery_qualified=False,
        installed=False,release_authorized=False,automatic_actuation=False)
    report['report_sha256']=sha256(_canonical(report)).hexdigest()
    target=root/(report['report_sha256']+'.journal-restore-report-v1.json');temporary=root/('.journal-proof-'+uuid4().hex)
    try:
        _write_private(temporary,_canonical(report));_rename_new(temporary,target);_sync_directory(root)
    finally:
        if temporary.exists():temporary.unlink()
    return target
