"""Internal native installation helpers behind source-backed readiness admission.

The caller must qualify readiness, hold the existing shared lock and supply an
inactivity/source/deadline guard. Helpers mutate exact reconciled files, quiesce
owned schedules, reload and verify definitions. There is no live CLI or complete
public activation entry point; source-backed admission remains unfinished.
"""
import os,stat,secrets,json
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


def _install_files(output,*,guard,_undo_log=None):
    """Apply five reconciled files; admission/activation belongs to the caller."""
    if not callable(guard):raise ValueError('installation epoch guard required')
    if _undo_log is not None and (type(_undo_log) is not list or _undo_log):raise ValueError('empty private undo log required')
    record=handoff_api.verify(output,guard=guard)
    family=deploy._directory(record['family']);selected=family_api.verify(family,guard=guard)
    stage=deploy._directory(selected['stage'])
    stages=[stage,deploy._directory(record['previous_forecast_stage']),deploy._directory(record['previous_score_stage'])]
    serving=selected['schema']=='earthship-native-thermal-service-family/v2'
    def stage_record(path):
        if record['schema']=='earthship-native-thermal-handoff/v3' and path==stages[1]:
            pin=record['previous_deployment_sha256']['forecast']
            baseline=deploy.verify_handoff_baseline(path,expected_deployment_sha256=pin)
            cycle=json.loads(deploy._bytes(path/'cycle.json',private=True))
            settings=json.loads(deploy._bytes(cycle['forecast_config'],private=True,maximum=8192))
            if settings.get('schema') not in deploy.GOOGLE_SCHEMAS:return baseline
            return deploy.verify_stage(path,expected_deployment_sha256=pin)
        if path==stage:return deploy.verify_stage(path,**({'expected_deployment_sha256':selected['deployment_sha256']} if serving else {}))
        return deploy.verify_handoff_baseline(path)
    stage_records=[stage_record(path) for path in stages]
    root=deploy._path(record['originals']['forecast_service']['path']).parent
    own=deploy._bytes(Path(__file__));changes=[]
    def unchanged():
        guard()
        if deploy._bytes(Path(__file__))!=own or family_api.verify(family,guard=guard)!=selected:
            raise ValueError('installation source or family changed')
        if any(stage_record(path)!=saved for path,saved in zip(stages,stage_records)):
            raise ValueError('installation original stage changed')
        for role,ref in record['originals'].items():
            if role.endswith('override'):continue # These are intentional owned replacements.
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
    if _undo_log is not None:_undo_log.extend(changes)
    return dict(status='native_unit_files_installed',handoff_sha256=record['handoff_sha256'],file_count=len(changes),
        unit_manager_reloaded=False,service_restarted=False,automatic_actuation=False)


from contextlib import contextmanager
import re

TIMERS=('thermal-provisional-forecast.timer','thermal-provisional-score.timer')


def _effective_state(unit):
    keys=('LoadState','ActiveState','MainPID','ExecStart','TimeoutStartUSec','FragmentPath','DropInPaths',
        'TimersCalendar','AccuracyUSec','RandomizedDelayUSec','Persistent','Unit','UnitFileState',*deploy.EFFECTIVE_LIMITS)
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
def _quiesce_timers(root,*,guard,include_preparer=False):
    """Restore owned schedules on exit unless cleanup leaves definitions unsafe."""
    timers=(*TIMERS,'thermal-native-geometry-prepare.timer') if include_preparer else TIMERS
    def inactive():
        _services_inactive(root)
        if include_preparer:deploy._inactive_capped(deploy._service_state(root/'thermal-native-geometry-prepare.service'))
    guard();inactive()
    original={unit:_timer_state(unit).get('ActiveState') for unit in timers}
    if any(state not in ('active','inactive') for state in original.values()):
        raise ValueError('explicit stable original timer states required')
    stopped=[];restoration={'safe':True}
    try:
        for unit in timers:
            if original[unit]=='active':
                stopped.append(unit);deploy._systemctl('stop',unit)
        guard();inactive()
        if any(_timer_state(unit).get('ActiveState')!='inactive' for unit in timers):
            raise ValueError('owned timer quiescence changed')
        yield restoration
    finally:
        failures=[]
        for unit in stopped if restoration['safe'] else []:
            try:
                state=_timer_state(unit).get('ActiveState')
                if state=='inactive':deploy._systemctl('start',unit)
                elif state!='active':raise ValueError('timer state changed during restoration')
            except Exception:failures.append(unit)
        if failures:raise ValueError('original timer schedule restoration incomplete: '+','.join(failures))


def _verify_shared_pool():
    import os
    from household_job_pool import read_pool
    uid=os.getuid()
    root=Path('/sys/fs/cgroup')/f'user.slice/user-{uid}.slice/user@{uid}.service/earthship.slice/earthship-work.slice'
    read_pool(root)


def _verify_effective_family(family,*,guard):
    """Read-only postconditions after the caller's coordinated manager reload."""
    family=deploy._directory(family);selected=family_api.verify(family,guard=guard)
    stage=deploy._directory(selected['stage'])
    serving=selected['schema']=='earthship-native-thermal-service-family/v2'
    record=deploy.verify_stage(stage,expected_deployment_sha256=selected['deployment_sha256']) if serving else deploy.verify_stage(stage)
    root=deploy._path(record['service_file']).parent
    if serving and family_api._shared_job_pool(stage):_verify_shared_pool()
    services=(('thermal-provisional-forecast.service','forecast.conf','1min 30s',['zzzz-household-cycle.conf']),
        ('thermal-provisional-score.service','score.conf',
            '2min 10s' if selected['score_service_timeout_seconds']==130 else '1min',['zzzz-household-score.conf']),
        ('thermal-native-geometry-prepare.service','thermal-native-geometry-prepare.service','1min 30s',[]))
    for name,source,timeout,dropins in services:
        guard();state=_effective_state(name);deploy._inactive_capped(state)
        expected_cpu='1s' if source in ('forecast.conf','score.conf') and b'CPUQuota=100%\n' in deploy._bytes(family/source,private=True) else '200ms'
        if state.get('CPUQuotaPerSecUSec')!=expected_cpu:raise ValueError('effective role CPU budget differs')
        expected_paths=[str(root/(name+'.d')/file) for file in dropins]
        if (state.get('LoadState')!='loaded' or state.get('FragmentPath')!=str(root/name) or
            state.get('DropInPaths','').split()!=expected_paths or state.get('TimeoutStartUSec')!=timeout or
            not deploy._entry_matches(state,deploy._bytes(family/source,private=True))):
            raise ValueError('effective native service definition differs')
    score_calendars=['*-*-* *:'+minute+'/5:10 UTC' for minute in ('00','01','02','03')] if serving else ['*-*-* *:01/5:00 UTC','*-*-* *:02/5:00 UTC']
    if serving and selected['score_service_timeout_seconds']==130:
        score_calendars=['*-*-* *:01/5:00 UTC']
        if family_api._independent_battery_slot(stage):score_calendars.append('*-*-* *:08/10:20 UTC')
    timers=(('thermal-provisional-forecast.timer',[selected['original_forecast_warm_clock']],[]),
        ('thermal-provisional-score.timer',score_calendars,['zzzz-household-native-timer.conf']),
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


def _reload_handoff(output,*,guard,_activate_preparer=False):
    """Compose internal admitted installation with optional preparer activation.

    A source-backed admission caller must already hold the shared lock. Its
    guard must preserve readiness/source/deadline epochs through intentional
    output changes; it must not treat the replaced overrides as old originals.
    This function is not exposed as a live command or an admission substitute.
    """
    record=handoff_api.verify(output,guard=guard)
    root=deploy._path(record['originals']['forecast_service']['path']).parent
    family=deploy._directory(record['family']);own=deploy._bytes(Path(__file__))
    changes=[];installed=False;preparer_lease=None
    upgrade=record['schema']=='earthship-native-thermal-handoff/v3'
    enable_link=root/'timers.target.wants'/'thermal-native-geometry-prepare.timer'
    enabled_identity=_enable_link_identity(enable_link) if upgrade else None
    if upgrade and enabled_identity[-1]!=str(root/'thermal-native-geometry-prepare.timer'):
        raise ValueError('exact previous preparer timer enablement required')
    def checked():
        guard()
        if deploy._bytes(Path(__file__))!=own:raise ValueError('installer source changed')
        if upgrade:
            try:unchanged=_enable_link_identity(enable_link)==enabled_identity
            except (OSError,ValueError):unchanged=False
            if not unchanged:raise PreparerReconciliationRequired('existing preparer enablement changed')
    with _quiesce_timers(root,guard=checked,include_preparer=upgrade) as restoration:
        try:
            result=_install_files(output,guard=checked,_undo_log=changes);installed=True
            checked();deploy._systemctl('daemon-reload');checked()
            effective=_verify_effective_family(family,guard=checked)
            checked()
            if _activate_preparer and not upgrade:
                preparer_lease=_enable_preparer(root,guard=checked)
                checked()
        except Exception as error:
            uncertain=isinstance(error,PreparerReconciliationRequired)
            if preparer_lease is not None:
                try:_undo_preparer_enable(preparer_lease)
                except Exception as cleanup_error:
                    uncertain=True
                    error.add_note('Preparer cleanup unproven; installed definitions retained: '+type(cleanup_error).__name__)
            if uncertain:
                restoration['safe']=False
                error.add_note('Native definitions retained and original schedules remain quiescent for preparer reconciliation')
            if installed and not uncertain:
                pending=_undo(changes)
                if pending:
                    restoration['safe']=False
                    error.add_note('Concurrent unit edits preserved; schedules remain quiescent for roles: '+','.join(pending))
                try:deploy._systemctl('daemon-reload')
                except Exception as reload_error:
                    restoration['safe']=False
                    error.add_note('Restored definition reload failed; schedules remain quiescent: '+type(reload_error).__name__)
            raise
    return dict(status='native_family_activated' if _activate_preparer else 'native_definitions_verified',handoff_sha256=result['handoff_sha256'],
        effective_definition_status=effective['status'],unit_manager_reloaded=True,
        new_preparer_timer_enabled=_activate_preparer and not upgrade,existing_preparer_timer_preserved=upgrade,
        service_restarted=False,automatic_actuation=False)


def _activate_handoff(output,*,guard):
    """Internal activation only; caller must hold shared lock and qualify sources."""
    return _reload_handoff(output,guard=guard,_activate_preparer=True)


class PreparerReconciliationRequired(ValueError):
    """Preparer ownership/inactivity is unproven; keep its definitions intact."""


PREPARER_TIMER='thermal-native-geometry-prepare.timer'


def _preparer_definition(root,state,*,active,enabled):
    if (state.get('LoadState')!='loaded' or state.get('ActiveState')!=active or
        state.get('FragmentPath')!=str(root/PREPARER_TIMER) or state.get('DropInPaths','') or
        state.get('TimersCalendar')!=['*-*-* *:03/5:05 UTC'] or state.get('AccuracyUSec')!='1s' or
        state.get('RandomizedDelayUSec')!='0' or state.get('Persistent')!='no' or
        state.get('Unit')!='thermal-native-geometry-prepare.service' or state.get('UnitFileState')!=enabled):
        raise ValueError('owned preparer timer definition or state differs')


def _enable_link_identity(path):
    info=path.lstat()
    if not stat.S_ISLNK(info.st_mode) or info.st_uid!=os.getuid():raise ValueError('owned timer enablement link required')
    return (info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_mtime_ns,info.st_ctime_ns,str(path.readlink()))


def _publish_enable_link(root):
    parent=deploy._path(root/'timers.target.wants');parent.mkdir(mode=0o700,exist_ok=True)
    before=parent.lstat()
    if not stat.S_ISDIR(before.st_mode) or before.st_uid!=os.getuid() or before.st_mode&0o002:
        raise ValueError('owned user timer target directory required')
    identity=lambda row:(row.st_dev,row.st_ino,row.st_mode,row.st_uid)
    fd=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    link=parent/PREPARER_TIMER;created_identity=None
    def fd_identity():
        row=os.stat(PREPARER_TIMER,dir_fd=fd,follow_symlinks=False)
        return (row.st_dev,row.st_ino,row.st_mode,row.st_uid,row.st_mtime_ns,row.st_ctime_ns,
            os.readlink(PREPARER_TIMER,dir_fd=fd))
    try:
        if identity(os.fstat(fd))!=identity(before):raise ValueError('timer target directory changed')
        os.symlink(str(root/PREPARER_TIMER),PREPARER_TIMER,dir_fd=fd)
        created_identity=fd_identity()
        if identity(deploy._path(parent).lstat())!=identity(before):raise ValueError('timer target directory changed')
        os.fsync(fd)
        if _enable_link_identity(link)!=created_identity:raise ValueError('timer enablement link changed')
        return link,created_identity
    except Exception as error:
        if created_identity is not None:
            try:
                if fd_identity()!=created_identity:raise ValueError('concurrent timer enablement preserved')
                os.unlink(PREPARER_TIMER,dir_fd=fd)
            except Exception as cleanup_error:
                raise PreparerReconciliationRequired('Enablement link publication cleanup requires reconciliation: '+type(cleanup_error).__name__) from error
        raise
    finally:os.close(fd)


def _undo_preparer_enable(lease):
    root=deploy._path(lease['root']);link=root/'timers.target.wants'/PREPARER_TIMER
    if (_enable_link_identity(link)!=lease['link_identity'] or
        sha256(deploy._bytes(root/PREPARER_TIMER,private=True)).hexdigest()!=lease['definition_sha256']):
        raise ValueError('concurrent preparer definition or enablement change preserved')
    state=_timer_state(PREPARER_TIMER)
    if state.get('ActiveState') not in ('active','inactive'):raise ValueError('preparer timer transition requires reconciliation')
    enabled=state.get('UnitFileState')
    if enabled not in ('enabled','disabled'):raise ValueError('preparer enablement state requires reconciliation')
    _preparer_definition(root,state,active=state['ActiveState'],enabled=enabled)
    if state['ActiveState']=='active':deploy._systemctl('stop',PREPARER_TIMER)
    stopped=_timer_state(PREPARER_TIMER)
    if stopped.get('ActiveState')!='inactive':raise ValueError('preparer timer is not inactive after stop')
    _preparer_definition(root,stopped,active='inactive',enabled=enabled)
    if (_enable_link_identity(link)!=lease['link_identity'] or
        sha256(deploy._bytes(root/PREPARER_TIMER,private=True)).hexdigest()!=lease['definition_sha256']):
        raise ValueError('concurrent preparer enablement change preserved after stop')
    link.unlink();deploy._systemctl('daemon-reload')


def _enable_preparer(root,*,guard):
    """Enable/start only the verified new schedule; return an exact private lease."""
    root=deploy._path(root);guard()
    definition=deploy._bytes(root/PREPARER_TIMER,private=True)
    _preparer_definition(root,_timer_state(PREPARER_TIMER),active='inactive',enabled='disabled')
    link=root/'timers.target.wants'/PREPARER_TIMER
    if link.exists() or link.is_symlink():raise ValueError('preparer timer enablement already exists')
    lease=None
    try:
        guard();link,identity=_publish_enable_link(root)
        lease=dict(root=str(root),timer=PREPARER_TIMER,link_identity=identity,definition_sha256=sha256(definition).hexdigest())
        deploy._systemctl('daemon-reload');guard()
        if _enable_link_identity(link)!=identity or deploy._bytes(root/PREPARER_TIMER,private=True)!=definition:
            raise ValueError('preparer enablement changed')
        _preparer_definition(root,_timer_state(PREPARER_TIMER),active='inactive',enabled='enabled')
        deploy._systemctl('start',PREPARER_TIMER);guard()
        _preparer_definition(root,_timer_state(PREPARER_TIMER),active='active',enabled='enabled')
        if _enable_link_identity(link)!=identity or deploy._bytes(root/PREPARER_TIMER,private=True)!=definition:
            raise ValueError('started preparer enablement changed')
        return lease
    except Exception as error:
        if lease is not None:
            try:_undo_preparer_enable(lease)
            except Exception as cleanup_error:
                raise PreparerReconciliationRequired('Preparer enablement cleanup requires reconciliation: '+type(cleanup_error).__name__) from error
        raise
