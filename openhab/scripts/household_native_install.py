"""Internal native unit-file transaction behind readiness admission.

The caller must qualify readiness, hold the existing shared lock, quiesce the
relevant timers, and supply an inactivity/source/deadline guard. This internal
layer never reloads units, activates timers, restarts services or grants actions.
"""
import os,stat,secrets
from pathlib import Path
from hashlib import sha256
import household_cycle_deploy as deploy
import household_native_family as family_api
import household_native_handoff as handoff_api


def _create(target,raw,root):
    """Publish complete bytes without replacing a name, anchored to its parent."""
    parent=deploy._path(target.parent)
    if parent!=root:
        parent.mkdir(mode=0o700,exist_ok=True);deploy._directory(parent)
    before=parent.lstat()
    if not stat.S_ISDIR(before.st_mode) or before.st_uid!=os.getuid() or before.st_mode&0o002:
        raise ValueError('owned unit directory required')
    identity=lambda row:(row.st_dev,row.st_ino,row.st_mode,row.st_uid)
    directory_fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    temporary='.native-install-'+secrets.token_hex(16);created=False
    def directory_guard():
        if identity(os.fstat(directory_fd))!=identity(before) or identity(deploy._path(parent).lstat())!=identity(before):
            raise ValueError('unit directory changed')
    try:
        directory_guard()
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory_fd);created=True
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        directory_guard()
        os.link(temporary,target.name,src_dir_fd=directory_fd,dst_dir_fd=directory_fd,follow_symlinks=False)
        os.unlink(temporary,dir_fd=directory_fd);created=False
        directory_guard();os.fsync(directory_fd)
        if deploy._bytes(target,private=True)!=raw:raise ValueError('new unit file readback differs')
    finally:
        if created:os.unlink(temporary,dir_fd=directory_fd)
        os.close(directory_fd)


def _undo(changes):
    pending=[]
    for role,target,previous,replacement in reversed(changes):
        try:
            if deploy._bytes(target,private=True)!=replacement:
                pending.append(role);continue
            if previous is None:target.unlink()
            else:deploy._replace_owned(target,replacement,previous)
        except (OSError,ValueError):pending.append(role)
    return pending


def _install_files(output,*,guard):
    """Apply five reconciled files; admission/activation belongs to the caller."""
    if not callable(guard):raise ValueError('installation epoch guard required')
    record=handoff_api.verify(output,guard=guard)
    family=deploy._directory(record['family']);selected=family_api.verify(family,guard=guard)
    stage=deploy._directory(selected['stage'])
    stages=[stage,deploy._directory(record['previous_forecast_stage']),deploy._directory(record['previous_score_stage'])]
    stage_records=[deploy.verify_stage(path) for path in stages]
    root=deploy._path(record['originals']['forecast_service']['path']).parent
    own=deploy._bytes(Path(__file__));changes=[]
    def unchanged():
        guard()
        if deploy._bytes(Path(__file__))!=own or family_api.verify(family,guard=guard)!=selected:
            raise ValueError('installation source or family changed')
        if any(deploy.verify_stage(path)!=saved for path,saved in zip(stages,stage_records)):
            raise ValueError('installation original stage changed')
        for role,ref in record['originals'].items():
            if role.endswith('override'):continue # These are the two intentional replacements.
            if sha256(deploy._bytes(ref['path'])).hexdigest()!=ref['sha256']:
                raise ValueError('installation base unit or timer changed')
    try:
        unchanged()
        for role in ('forecast','score','score_timer','preparer_service','preparer_timer'):
            row=record['changes'][role];target=deploy._path(row['target'])
            replacement=deploy._bytes(row['desired']['path'],private=True)
            if sha256(replacement).hexdigest()!=row['desired']['sha256']:raise ValueError('desired unit file changed')
            previous=None
            if row['previous'] is not None:
                previous=deploy._bytes(target,private=True)
                if sha256(previous).hexdigest()!=row['previous']['sha256']:raise ValueError('previous owned unit file changed')
            changes.append((role,target,previous,replacement))
            if previous is None:_create(target,replacement,root)
            else:deploy._replace_owned(target,previous,replacement)
            unchanged()
            if any(deploy._bytes(path,private=True)!=raw for _,path,_,raw in changes):
                raise ValueError('installed unit files changed')
    except Exception as error:
        pending=_undo(changes)
        if pending:error.add_note('Concurrent changes or changed parents preserved for roles: '+','.join(pending))
        raise
    return dict(status='native_unit_files_installed',handoff_sha256=record['handoff_sha256'],file_count=len(changes),
        unit_manager_reloaded=False,service_restarted=False,automatic_actuation=False)
