"""Preparer schedule enablement with mocked manager and temporary user roots."""
import pytest
import household_native_install as api
import household_cycle_deploy as deploy

TIMER='thermal-native-geometry-prepare.timer'


def fixture(tmp_path,monkeypatch):
    root=tmp_path/'user';root.mkdir(mode=0o700)
    (root/TIMER).write_bytes(b'owned timer definition');(root/TIMER).chmod(0o600)
    state={'LoadState':'loaded','ActiveState':'inactive','FragmentPath':str(root/TIMER),'DropInPaths':'',
        'TimersCalendar':['*-*-* *:03/5:05 UTC'],'AccuracyUSec':'1s','RandomizedDelayUSec':'0','Persistent':'no',
        'Unit':'thermal-native-geometry-prepare.service','UnitFileState':'disabled'}
    calls=[]
    monkeypatch.setattr(api,'_timer_state',lambda unit:state.copy())
    def systemctl(*args):
        calls.append(args)
        if args==('daemon-reload',):state['UnitFileState']='enabled' if (root/'timers.target.wants'/TIMER).is_symlink() else 'disabled'
        if args==('start',TIMER):state['ActiveState']='active'
        if args==('stop',TIMER):state['ActiveState']='inactive'
        return ''
    monkeypatch.setattr(deploy,'_systemctl',systemctl)
    return root,state,calls


def test_creates_one_owned_enable_link_and_starts_only_preparer_timer(tmp_path,monkeypatch):
    root,state,calls=fixture(tmp_path,monkeypatch)
    lease=api._enable_preparer(root,guard=lambda:None)
    link=root/'timers.target.wants'/TIMER
    assert link.is_symlink() and link.readlink()==root/TIMER
    assert state['ActiveState']=='active' and calls==[('daemon-reload',),('start',TIMER)]
    assert lease['timer']==TIMER and lease['definition_sha256']


@pytest.mark.parametrize('damage',['active','fragment','calendar','persistent','enabled','collision'])
def test_refuses_unowned_or_already_enabled_preparer_before_mutation(tmp_path,monkeypatch,damage):
    root,state,calls=fixture(tmp_path,monkeypatch)
    if damage=='active':state['ActiveState']='active'
    elif damage=='fragment':state['FragmentPath']='/unowned.timer'
    elif damage=='calendar':state['TimersCalendar']=['hourly']
    elif damage=='persistent':state['Persistent']='yes'
    elif damage=='enabled':state['UnitFileState']='enabled'
    else:
        folder=root/'timers.target.wants';folder.mkdir(mode=0o700);(folder/TIMER).symlink_to('/unowned.timer')
    with pytest.raises((ValueError,OSError)):api._enable_preparer(root,guard=lambda:None)
    assert calls==[]


def test_start_failure_removes_only_our_enable_link(tmp_path,monkeypatch):
    root,state,calls=fixture(tmp_path,monkeypatch);original=deploy._systemctl
    def fail(*args):
        if args==('start',TIMER):raise ValueError('start failed')
        return original(*args)
    monkeypatch.setattr(deploy,'_systemctl',fail)
    with pytest.raises(ValueError,match='start failed'):api._enable_preparer(root,guard=lambda:None)
    link=root/'timers.target.wants'/TIMER
    assert not link.exists() and not link.is_symlink()
    assert state['ActiveState']=='inactive' and calls.count(('daemon-reload',))==2


def test_enable_cleanup_preserves_concurrent_link_replacement(tmp_path,monkeypatch):
    root,state,calls=fixture(tmp_path,monkeypatch);lease=api._enable_preparer(root,guard=lambda:None)
    link=root/'timers.target.wants'/TIMER;link.unlink();link.symlink_to('/operator.timer')
    with pytest.raises(ValueError):api._undo_preparer_enable(lease)
    assert link.readlink().as_posix()=='/operator.timer'
    assert ('stop',TIMER) not in calls


def test_undo_stops_owned_schedule_and_removes_only_exact_link(tmp_path,monkeypatch):
    root,state,calls=fixture(tmp_path,monkeypatch);lease=api._enable_preparer(root,guard=lambda:None)
    api._undo_preparer_enable(lease)
    link=root/'timers.target.wants'/TIMER
    assert not link.exists() and not link.is_symlink() and state['ActiveState']=='inactive'
    assert calls[-2:]==[('stop',TIMER),('daemon-reload',)]


def test_link_publication_failure_removes_created_link(tmp_path,monkeypatch):
    root,state,calls=fixture(tmp_path,monkeypatch)
    def fail(fd):raise OSError('fsync failed')
    monkeypatch.setattr(api.os,'fsync',fail)
    with pytest.raises(OSError,match='fsync failed'):api._enable_preparer(root,guard=lambda:None)
    link=root/'timers.target.wants'/TIMER
    assert not link.is_symlink()
    assert calls==[]


def test_first_reload_failure_cleans_link_even_if_manager_still_disabled(tmp_path,monkeypatch):
    root,state,calls=fixture(tmp_path,monkeypatch);original=deploy._systemctl;attempts=0
    def fail(*args):
        nonlocal attempts
        if args==('daemon-reload',):
            attempts+=1
            if attempts==1:raise ValueError('reload failed')
        return original(*args)
    monkeypatch.setattr(deploy,'_systemctl',fail)
    with pytest.raises(ValueError,match='reload failed'):api._enable_preparer(root,guard=lambda:None)
    assert not (root/'timers.target.wants'/TIMER).is_symlink()
    assert state['ActiveState']=='inactive' and attempts==2


def test_failed_stop_preserves_enablement_for_reconciliation(tmp_path,monkeypatch):
    root,state,calls=fixture(tmp_path,monkeypatch);lease=api._enable_preparer(root,guard=lambda:None);original=deploy._systemctl
    def no_stop(*args):
        if args==('stop',TIMER):return ''
        return original(*args)
    monkeypatch.setattr(deploy,'_systemctl',no_stop)
    with pytest.raises(ValueError,match='inactive'):api._undo_preparer_enable(lease)
    assert (root/'timers.target.wants'/TIMER).is_symlink()
