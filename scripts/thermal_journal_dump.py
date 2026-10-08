"""Bound and pace one custom journal dump for a trusted guarded source worker.

The caller owns the audited repeatable-read snapshot. This transport alone does
not authenticate source rows, inspect SQL objects or qualify recovery/release.
"""
from hashlib import sha256
from pathlib import Path
import os,re,selectors,signal,stat,subprocess
from time import monotonic,sleep
from psycopg2.extensions import make_dsn,parse_dsn
from thermal_model.capture_readers import bounded_journal_dsn
from thermal_model.forcing_capture import _private_directory
from thermal_model.environment_bundle import _pacer

MAX_ARCHIVE_BYTES=32000000
DUMP_SECONDS=70
CHUNK=65536


def _request(params,snapshot):
    if not isinstance(params,dict):raise ValueError('restricted journal dump parameters required')
    checked=parse_dsn(bounded_journal_dsn(make_dsn(**params)))
    if (re.fullmatch('[a-z_][a-z0-9_]{0,62}',checked['user']) is None or
            not isinstance(snapshot,str) or re.fullmatch('[0-9A-F]{8}-[0-9A-F]{8}-[1-9][0-9]{0,9}',snapshot) is None or
            len(checked['password'])>4096):raise ValueError('bounded journal role and snapshot required')
    return {'PATH':'/usr/bin:/bin','PGHOST':'127.0.0.1','PGHOSTADDR':'127.0.0.1',
            'PGPORT':'5432','PGDATABASE':'openhab','PGUSER':checked['user'],'PGPASSWORD':checked['password'],
            'PGCONNECT_TIMEOUT':'3','PGCLIENTENCODING':'UTF8',
            'PGOPTIONS':'-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000'}


def dump_journal(*,target,params,snapshot):
    """Retain at most 32 MB; abort before writing any overflowing chunk."""
    env=_request(params,snapshot);target=Path(target);_private_directory(target.parent)
    if not target.is_absolute() or target.resolve()!=target:raise ValueError('resolved private dump target required')
    descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    identity=os.fstat(descriptor);process=None;success=False;deadline=monotonic()+DUMP_SECONDS
    count=0;header=b'';digest=sha256();pace=_pacer(1048576)
    def remaining():
        value=deadline-monotonic()
        if value<=0:raise ValueError('journal dump deadline exceeded')
        return value
    try:
        with os.fdopen(descriptor,'wb') as output:
            try:
                process=subprocess.Popen(['/usr/bin/pg_dump','--format=custom','--schema=thermal_intel',
                    '--lock-wait-timeout=1000','--snapshot='+snapshot],env=env,
                    stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                    start_new_session=True,close_fds=True)
                os.set_blocking(process.stdout.fileno(),False)
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout,selectors.EVENT_READ)
                    while True:
                        if not selector.select(min(1,remaining())):continue
                        amount=min(CHUNK,MAX_ARCHIVE_BYTES-count+1)
                        pace.reserve(amount);remaining()
                        try:block=os.read(process.stdout.fileno(),amount)
                        except BlockingIOError:continue
                        if not block:break
                        if count+len(block)>MAX_ARCHIVE_BYTES:raise ValueError('journal dump exceeds byte bound')
                        count+=len(block);header=(header+block)[:5] if len(header)<5 else header
                        output.write(block);digest.update(block)
                while True:
                    remaining()
                    # Do not reap the leader until its owned group is cleaned.
                    exited=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                    if exited is not None:break
                    sleep(min(.02,remaining()))
                if exited.si_code!=os.CLD_EXITED or exited.si_status!=0 or header!=b'PGDMP':
                    raise ValueError('journal dump failed or custom marker unavailable')
                output.flush();os.fsync(output.fileno());remaining()
            finally:
                if process is not None:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait(timeout=2)
                    if process.stdout is not None:process.stdout.close()
        observed=target.lstat()
        if ((observed.st_dev,observed.st_ino)!=(identity.st_dev,identity.st_ino) or
                not stat.S_ISREG(observed.st_mode) or observed.st_size!=count or
                observed.st_nlink!=1 or stat.S_IMODE(observed.st_mode)!=0o600):raise ValueError('journal dump target changed')
        success=True
        return {'bytes':count,'sha256':digest.hexdigest()}
    finally:
        if not success:
            try:
                observed=target.lstat()
                if (observed.st_dev,observed.st_ino)==(identity.st_dev,identity.st_ino):target.unlink()
            except FileNotFoundError:pass
