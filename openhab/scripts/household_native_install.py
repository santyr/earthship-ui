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


from contextlib import contextmanager
import re

TIMERS=('thermal-provisional-forecast.timer','thermal-provisional-score.timer')


def _effective_state(unit):
    keys=('LoadState','ActiveState','MainPID','ExecStart','TimeoutStartUSec','FragmentPath','DropInPaths',
        'TimersCalendar','AccuracyUSec','RandomizedDelayUSec','Persistent','Unit',*deploy.EFFECTIVE_LIMITS)
    raw=deploy._systemctl('show',unit,*['--property='+key for key in keys])
    result={};calendars=[]
    for row in raw.splitlines():
        if '=' not in row:continue
        key,value=row.split('=',1)
        if key=='TimersCalendar':
            match=re.fullmatch(r'\{ OnCalendar=(.*?) ; next_elapse=.*? \}',value)
            if match is None:raise ValueError('explicit effective calendar required')
            calendars.append(match.group(1))
        else:
            if key in result:raise ValueError('duplicate effective unit property')
            result[key]=value
    result['TimersCalendar']=calendars
    return result


def _timer_state(unit):return _effective_state(unit)


def _services_inactive(root):
    for name in ('thermal-provisional-forecast.service','thermal-provisional-score.service'):
        deploy._inactive_capped(deploy._service_state(root/name))


@contextmanager
def _quiesce_timers(root,*,guard):
    """Stop only active owned schedules and restore them on every exit."""
    guard();_services_inactive(root)
    original={unit:_timer_state(unit).get('ActiveState') for unit in TIMERS}
    if any(state not in ('active','inactive') for state in original.values()):
        raise ValueError('explicit stable original timer states required')
    stopped=[]
    try:
        for unit in TIMERS:
            if original[unit]=='active':
                stopped.append(unit);deploy._systemctl('stop',unit)
        guard();_services_inactive(root)
        if any(_timer_state(unit).get('ActiveState')!='inactive' for unit in TIMERS):
            raise ValueError('owned timer quiescence changed')
        yield
    finally:
        failures=[]
        for unit in stopped:
            try:
                state=_timer_state(unit).get('ActiveState')
                if state=='inactive':deploy._systemctl('start',unit)
                elif state!='active':raise ValueError('timer state changed during restoration')
            except Exception:failures.append(unit)
        if failures:raise ValueError('original timer schedule restoration incomplete: '+','.join(failures))


def _verify_effective_family(family,*,guard):
    """Read-only postconditions after the caller's coordinated manager reload."""
    family=deploy._directory(family);selected=family_api.verify(family,guard=guard)
    stage=deploy._directory(selected['stage']);record=deploy.verify_stage(stage)
    root=deploy._path(record['service_file']).parent
    services=(('thermal-provisional-forecast.service','forecast.conf','1min 30s',['zzzz-household-cycle.conf']),
        ('thermal-provisional-score.service','score.conf','1min',['zzzz-household-score.conf']),
        ('thermal-native-geometry-prepare.service','thermal-native-geometry-prepare.service','1min 30s',[]))
    for name,source,timeout,dropins in services:
        guard();state=_effective_state(name);deploy._inactive_capped(state)
        expected_paths=[str(root/(name+'.d')/file) for file in dropins]
        if (state.get('LoadState')!='loaded' or state.get('FragmentPath')!=str(root/name) or
            state.get('DropInPaths','').split()!=expected_paths or state.get('TimeoutStartUSec')!=timeout or
            not deploy._entry_matches(state,deploy._bytes(family/source,private=True))):
            raise ValueError('effective native service definition differs')
    timers=(('thermal-provisional-forecast.timer',[selected['original_forecast_warm_clock']],[]),
        ('thermal-provisional-score.timer',['*-*-* *:01/5:00 UTC','*-*-* *:02/5:00 UTC'],['zzzz-household-native-timer.conf']),
        ('thermal-native-geometry-prepare.timer',['*-*-* *:03/5:05 UTC'],[]))
    for name,calendars,dropins in timers:
        guard();state=_effective_state(name)
        expected_paths=[str(root/(name+'.d')/file) for file in dropins]
        if (state.get('LoadState')!='loaded' or state.get('ActiveState')!='inactive' or
            state.get('FragmentPath')!=str(root/name) or state.get('DropInPaths','').split()!=expected_paths or
            sorted(state.get('TimersCalendar',[]))!=sorted(calendars) or state.get('Unit')!=name.removesuffix('.timer')+'.service' or
            state.get('AccuracyUSec')!='1s' or state.get('RandomizedDelayUSec')!='0' or state.get('Persistent')!='no'):
            raise ValueError('effective native timer definition differs')
    guard()
    if family_api.verify(family,guard=guard)!=selected:raise ValueError('native family changed during effective verification')
    return dict(status='native_effective_family_verified',deployment_sha256=selected['deployment_sha256'],
        services_inactive=True,timers_inactive=True,automatic_actuation=False)
