"""Coordinated file/reload verification in a temporary unit-manager fixture."""
import pytest
from test_household_native_install_files import setup
from test_household_native_install_lifecycle import lifecycle
import household_cycle_deploy as deploy


def fixture(tmp_path,monkeypatch):
    module,out,base,family,previous=setup(tmp_path,monkeypatch)
    calls,current=lifecycle(monkeypatch)
    monkeypatch.setattr(module,'_verify_effective_family',lambda family,guard:guard() or {'status':'native_effective_family_verified'})
    return module,out,base,family,previous,calls,current


def test_installs_reloads_verifies_and_restores_original_schedules(tmp_path,monkeypatch):
    module,out,base,family,previous,calls,current=fixture(tmp_path,monkeypatch)
    result=module._reload_handoff(out,guard=lambda:None)
    assert result['status']=='native_definitions_verified' and result['new_preparer_timer_enabled'] is False
    assert calls.count(('daemon-reload',))==1
    assert ('restart','thermal-provisional-forecast.service') not in calls
    assert all(value=='active' for value in current.values())
    assert (base/'thermal-native-geometry-prepare.service').read_bytes()==(family/'thermal-native-geometry-prepare.service').read_bytes()


def test_bad_effective_definition_restores_files_reloads_and_restores_schedules(tmp_path,monkeypatch):
    module,out,base,family,previous,calls,current=fixture(tmp_path,monkeypatch)
    target=base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf';old=target.read_bytes()
    def refuse(*a,**kw):raise ValueError('effective definition differs')
    monkeypatch.setattr(module,'_verify_effective_family',refuse)
    with pytest.raises(ValueError,match='definition differs'):module._reload_handoff(out,guard=lambda:None)
    assert target.read_bytes()==old and not (base/'thermal-native-geometry-prepare.service').exists()
    assert calls.count(('daemon-reload',))==2 and all(value=='active' for value in current.values())


def test_reload_failure_restores_files_and_attempts_old_definition_reload(tmp_path,monkeypatch):
    module,out,base,family,previous,calls,current=fixture(tmp_path,monkeypatch)
    target=base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf';old=target.read_bytes();original=deploy._systemctl;reloads=[]
    def fail(*args):
        if args==('daemon-reload',):
            reloads.append(1)
            if len(reloads)==1:raise ValueError('reload failed')
        return original(*args)
    monkeypatch.setattr(deploy,'_systemctl',fail)
    with pytest.raises(ValueError,match='reload failed'):module._reload_handoff(out,guard=lambda:None)
    assert target.read_bytes()==old and len(reloads)==2 and all(value=='active' for value in current.values())


def test_effective_failure_preserves_concurrent_operator_change(tmp_path,monkeypatch):
    module,out,base,family,previous,calls,current=fixture(tmp_path,monkeypatch)
    target=base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf'
    def change(*a,**kw):target.write_bytes(b'operator override');raise ValueError('concurrent edit')
    monkeypatch.setattr(module,'_verify_effective_family',change)
    with pytest.raises(ValueError):module._reload_handoff(out,guard=lambda:None)
    assert target.read_bytes()==b'operator override' and all(value=='inactive' for value in current.values())


def test_initial_guard_refusal_has_no_manager_or_file_side_effect(tmp_path,monkeypatch):
    module,out,base,family,previous,calls,current=fixture(tmp_path,monkeypatch)
    def refuse():raise ValueError('admission expired')
    with pytest.raises(ValueError):module._reload_handoff(out,guard=refuse)
    assert not any(isinstance(call,tuple) for call in calls)
    assert not (base/'thermal-native-geometry-prepare.service').exists()


def test_failed_restored_reload_keeps_timers_quiescent(tmp_path,monkeypatch):
    module,out,base,family,previous,calls,current=fixture(tmp_path,monkeypatch);original=deploy._systemctl
    def fail(*args):
        if args==('daemon-reload',):raise ValueError('manager unavailable')
        return original(*args)
    monkeypatch.setattr(deploy,'_systemctl',fail)
    with pytest.raises(ValueError,match='manager unavailable'):module._reload_handoff(out,guard=lambda:None)
    assert all(value=='inactive' for value in current.values())
