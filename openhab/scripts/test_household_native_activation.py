"""Automatic model cutover cannot select a cold or expired geometry cache."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


def activation_case(tmp_path, monkeypatch):
    import household_native_training as training
    import household_native_handoff as handoff
    import household_native_install as install
    import household_cycle_deploy as deploy
    import household_native_geometry_prepare as preparer
    import native_model_serving_receipt as receipt
    import native_thermal_live as live
    tmp_path.chmod(0o700)
    run=tmp_path/'run';run.mkdir(mode=0o700)
    stage=run/'final';stage.mkdir(mode=0o700)
    units=tmp_path/'units';units.mkdir(mode=0o700)
    geometry=run/'geometry-live';geometry.mkdir(mode=0o700)
    shared=tmp_path/'shared.lock';shared.write_bytes(b'');shared.chmod(0o600)
    previous=dict(stage=str(tmp_path/'old'),deployment_sha256='a'*64,trained_through='2026-10-20T12:00:00+00:00')
    selection=dict(stage=str(stage),deployment_sha256='b'*64,trained_through='2026-10-20T18:00:00+00:00')
    settings=dict(shared_lock=str(shared),geometry_directory=str(geometry),artifact_sha256='c'*64,runtime_sha256='d'*64)
    training.save(run/'activation-input.json',dict(selection=selection,previous=previous))
    training.save(run/'final-config.json',settings)
    import household_native_history as history
    training.save(run/'score-history-window.json',{})
    monkeypatch.setattr(history,'revalidate',lambda *a,**kw:{})
    monkeypatch.setattr(history,'snapshot_guard',lambda *a,**kw:lambda:None)
    training.save(run/'geometry-libraries.json',dict(original_libraries=True))
    marker=units/'selected';marker.write_text('old')
    clock=[datetime(2026,10,20,18,42,tzinfo=timezone.utc)]
    issue=datetime(2026,10,20,18,45,15,tzinfo=timezone.utc)
    packet=geometry/('20261020T184515Z-'+'c'*64+'.native-forecast-geometry-v1.json')
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return clock[0]
    monkeypatch.setattr(training,'datetime',Clock)
    monkeypatch.setattr(training,'RamGuard',lambda **kw:lambda:None)
    monkeypatch.setattr(training.subprocess,'check_output',lambda *args,**kw:'0\n')
    monkeypatch.setattr(training,'effective_selection',lambda:{k:previous[k] for k in ('stage','deployment_sha256')})
    monkeypatch.setattr(handoff,'__file__',str(stage/'sources/openhab/scripts/household_native_handoff.py'))
    monkeypatch.setattr(deploy,'_qualify',lambda *a,**kw:None)
    monkeypatch.setattr(training,'selected_family_interpreter',lambda *a,**kw:{'path':'/private/python3.12'})
    monkeypatch.setattr(deploy,'verify_stage',lambda *a,**kw:dict(service_file=str(units/'thermal-provisional-forecast.service')))
    monkeypatch.setattr(receipt,'load_serving_selection',lambda *a,**kw:object())
    model=SimpleNamespace(candidate=dict(fit=dict(training_end=selection['trained_through'])))
    monkeypatch.setattr(receipt,'read_serving_model',lambda *a,**kw:model)
    timers={name:'active' for name in (*install.TIMERS,install.PREPARER_TIMER)}
    import household_native_lifecycle as lifecycle
    monkeypatch.setenv('EARTHSHIP_NATIVE_RESERVATION',str(run/'reservation'))
    class Owner:
        data={'run':str(run),'previous':previous}
        def check(self):pass
        def quiesce(self,family):
            for name in timers:timers[name]='inactive'
    monkeypatch.setattr(lifecycle,'attach',lambda *a,**kw:Owner())
    actual_activate=training.activate
    def managed_activate(run):
        try:return actual_activate(run)
        finally:
            for name in timers:timers[name]='active'
    monkeypatch.setattr(training,'activate',managed_activate)
    monkeypatch.setattr(install,'_timer_state',lambda unit:dict(ActiveState=timers[unit]))
    monkeypatch.setattr(install,'_services_inactive',lambda root:None)
    monkeypatch.setattr(deploy,'_service_state',lambda path:{})
    monkeypatch.setattr(deploy,'_inactive_capped',lambda state:None)
    def systemctl(action,unit):
        assert action in ('start','stop')
        timers[unit]='active' if action=='start' else 'inactive'
        return ''
    monkeypatch.setattr(deploy,'_systemctl',systemctl)
    def prepare(config,libraries,*,stage:Path,deployment_sha256):
        assert config==run/'final-config.json' and libraries==run/'geometry-libraries.json'
        assert stage==Path(selection['stage']) and deployment_sha256==selection['deployment_sha256']
        assert marker.read_text()=='old' and set(timers.values())=={'active'}
        training.save(packet,dict(issued_at=issue.isoformat(),artifact_sha256=settings['artifact_sha256']))
        clock[0]+=timedelta(seconds=5)
        return dict(status='prepared',path=str(packet),automatic_actuation=False)
    monkeypatch.setattr(preparer,'run',prepare)
    def read_geometry(actual,*,issue:datetime,guard):
        assert actual==settings
        guard()
        value=json.loads(packet.read_bytes())
        if value['issued_at']!=issue.isoformat() or value['artifact_sha256']!=actual['artifact_sha256']:
            raise ValueError('geometry model or issue differs')
        return object()
    monkeypatch.setattr(live,'read_geometry',read_geometry)
    monkeypatch.setattr(handoff,'prepare',lambda *a,**kw:kw['guard']())
    def install_new(output,*,guard,_reservation=None):
        guard()
        assert packet.exists(), 'new-model geometry missing before source cutover'
        assert set(timers.values())=={'inactive'}
        marker.write_text('new')
        return dict(status='native_family_activated',automatic_actuation=False)
    monkeypatch.setattr(install,'_activate_handoff',install_new)
    return SimpleNamespace(training=training,run=run,clock=clock,issue=issue,packet=packet,
        marker=marker,timers=timers,preparer=preparer,install=install,prepare=prepare)


def test_automatic_cutover_prepares_exact_new_model_before_switching_source(tmp_path,monkeypatch):
    case=activation_case(tmp_path,monkeypatch)
    result=case.training.activate(case.run)
    assert result['status']=='native_family_activated'
    assert case.marker.read_text()=='new'
    assert case.packet.exists()
    assert set(case.timers.values())=={'active'}


def test_failed_prewarm_leaves_old_source_and_serving_schedules_untouched(tmp_path,monkeypatch):
    case=activation_case(tmp_path,monkeypatch)
    def failed(*a,**kw):raise ValueError('original model geometry unavailable')
    monkeypatch.setattr(case.preparer,'run',failed)
    with pytest.raises(ValueError,match='geometry unavailable'):case.training.activate(case.run)
    assert case.marker.read_text()=='old' and set(case.timers.values())=={'active'}
    assert not (case.run/'activation-result.json').exists()


@pytest.mark.parametrize('damage',['wrong_path','wrong_issue','wrong_model'])
def test_other_geometry_cannot_authorize_new_selection(tmp_path,monkeypatch,damage):
    case=activation_case(tmp_path,monkeypatch)
    def changed(*a,**kw):
        result=case.prepare(*a,**kw)
        if damage=='wrong_path':result['path']=str(case.run/'another-model.json')
        else:
            body=json.loads(case.packet.read_bytes())
            if damage=='wrong_issue':body['issued_at']='2026-10-20T18:50:15+00:00'
            else:body['artifact_sha256']='f'*64
            case.packet.write_text(json.dumps(body))
        return result
    monkeypatch.setattr(case.preparer,'run',changed)
    with pytest.raises(ValueError,match='geometry'):case.training.activate(case.run)
    assert case.marker.read_text()=='old' and set(case.timers.values())=={'active'}


def test_geometry_expiring_before_cutover_keeps_old_source(tmp_path,monkeypatch):
    case=activation_case(tmp_path,monkeypatch)
    def late(*a,**kw):
        result=case.prepare(*a,**kw)
        case.clock[0]=case.issue-timedelta(seconds=35)
        return result
    monkeypatch.setattr(case.preparer,'run',late)
    with pytest.raises(ValueError,match='window elapsed'):case.training.activate(case.run)
    assert case.marker.read_text()=='old' and set(case.timers.values())=={'active'}


def test_geometry_window_remains_guarded_inside_transaction(tmp_path,monkeypatch):
    import household_native_handoff as handoff
    case=activation_case(tmp_path,monkeypatch)
    def late(*a,**kw):
        kw['guard']()
        case.clock[0]=case.issue-timedelta(seconds=34)
    monkeypatch.setattr(handoff,'prepare',late)
    with pytest.raises(ValueError,match='window elapsed'):case.training.activate(case.run)
    assert case.marker.read_text()=='old' and set(case.timers.values())=={'active'}


def test_geometry_byte_change_during_transaction_refuses_source_switch(tmp_path,monkeypatch):
    case=activation_case(tmp_path,monkeypatch)
    def changed(*a,guard,**kw):
        case.packet.write_bytes(b'changed geometry after validated read')
        guard()
    monkeypatch.setattr(case.install,'_activate_handoff',changed)
    with pytest.raises(ValueError,match='handoff geometry changed'):case.training.activate(case.run)
    assert case.marker.read_text()=='old' and set(case.timers.values())=={'active'}


def test_concurrent_selected_model_change_still_refuses_activation(tmp_path,monkeypatch):
    case=activation_case(tmp_path,monkeypatch)
    def changed(*a,**kw):
        result=case.prepare(*a,**kw)
        monkeypatch.setattr(case.training,'effective_selection',lambda:dict(stage='other',deployment_sha256='f'*64))
        return result
    monkeypatch.setattr(case.preparer,'run',changed)
    with pytest.raises(ValueError,match='active model changed'):case.training.activate(case.run)
    assert case.marker.read_text()=='old' and set(case.timers.values())=={'active'}
