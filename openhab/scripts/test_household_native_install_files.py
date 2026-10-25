"""File transaction tests in temporary unit directories; no live activation."""
import importlib
from pathlib import Path
import pytest
from test_household_native_handoff import fixture


def setup(tmp_path,monkeypatch):
    handoff,args,previous,family,out,base=fixture(tmp_path,monkeypatch)
    handoff.prepare(family,previous_forecast_stage=previous,previous_score_stage=previous,output=out,guard=lambda:None)
    return importlib.import_module('household_native_install'),out,base,family,previous


def test_stages_all_five_files_without_reloading_or_starting_units(tmp_path,monkeypatch):
    module,out,base,family,previous=setup(tmp_path,monkeypatch)
    import household_cycle_deploy as deploy
    monkeypatch.setattr(deploy,'_systemctl',lambda *args:pytest.fail('file transaction activated a unit'))
    result=module._install_files(out,guard=lambda:None)
    assert result['status']=='native_unit_files_installed' and result['unit_manager_reloaded'] is False
    mapping={'forecast.conf':base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf',
        'score.conf':base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf',
        'score-timer.conf':base/'thermal-provisional-score.timer.d'/'zzzz-household-native-timer.conf',
        'thermal-native-geometry-prepare.service':base/'thermal-native-geometry-prepare.service',
        'thermal-native-geometry-prepare.timer':base/'thermal-native-geometry-prepare.timer'}
    for name,target in mapping.items():
        assert target.read_bytes()==(family/name).read_bytes()
        assert target.stat().st_mode&0o777==0o600


def test_failure_restores_only_our_exact_changes(tmp_path,monkeypatch):
    module,out,base,family,previous=setup(tmp_path,monkeypatch)
    targets=[base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf',base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf']
    original={path:path.read_bytes() for path in targets};calls=[]
    def guard():
        calls.append(1)
        if targets[0].read_bytes()!=original[targets[0]]:raise ValueError('qualification epoch changed')
    with pytest.raises(ValueError,match='epoch changed'):module._install_files(out,guard=guard)
    assert all(path.read_bytes()==raw for path,raw in original.items())
    assert not (base/'thermal-native-geometry-prepare.service').exists()


def test_failure_preserves_concurrent_operator_override(tmp_path,monkeypatch):
    module,out,base,family,previous=setup(tmp_path,monkeypatch)
    path=base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf';old=path.read_bytes()
    def guard():
        if path.read_bytes()!=old:
            path.write_bytes(b'concurrent operator edit');raise ValueError('concurrent edit')
    with pytest.raises(ValueError):module._install_files(out,guard=guard)
    assert path.read_bytes()==b'concurrent operator edit'


def test_new_target_collision_never_overwrites_other_contents(tmp_path,monkeypatch):
    module,out,base,family,previous=setup(tmp_path,monkeypatch)
    target=base/'thermal-native-geometry-prepare.service'
    def guard():
        if (base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf').read_bytes()==(family/'forecast.conf').read_bytes() and not target.exists():
            target.write_bytes(b'concurrent unit');target.chmod(0o600)
    with pytest.raises((ValueError,OSError)):module._install_files(out,guard=guard)
    assert target.read_bytes()==b'concurrent unit'
    assert (base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf').read_bytes()==(previous/'service.conf').read_bytes()


def test_late_failure_removes_new_files_and_restores_both_overrides(tmp_path,monkeypatch):
    module,out,base,family,previous=setup(tmp_path,monkeypatch)
    forecast=base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf'
    score=base/'thermal-provisional-score.service.d'/'zzzz-household-score.conf'
    original={forecast:forecast.read_bytes(),score:score.read_bytes()}
    timer=base/'thermal-native-geometry-prepare.timer'
    def guard():
        if timer.exists():raise ValueError('late admission epoch expired')
    with pytest.raises(ValueError,match='epoch expired'):module._install_files(out,guard=guard)
    assert all(path.read_bytes()==raw for path,raw in original.items())
    assert not timer.exists() and not (base/'thermal-native-geometry-prepare.service').exists()
    assert not (base/'thermal-provisional-score.timer.d'/'zzzz-household-native-timer.conf').exists()


def test_base_unit_drift_during_install_refuses_and_preserves_operator_change(tmp_path,monkeypatch):
    module,out,base,family,previous=setup(tmp_path,monkeypatch)
    forecast=base/'thermal-provisional-forecast.service.d'/'zzzz-household-cycle.conf';old=forecast.read_bytes()
    base_timer=base/'thermal-provisional-score.timer'
    def guard():
        if forecast.read_bytes()!=old:base_timer.write_bytes(b'operator timer change')
    with pytest.raises(ValueError):module._install_files(out,guard=guard)
    assert forecast.read_bytes()==old and base_timer.read_bytes()==b'operator timer change'


@pytest.mark.parametrize('damage',['unchanged','before_handoff','before_install','delete_before_install','during_install'])
def test_install_preserves_superseded_history_obligations(tmp_path,monkeypatch,damage):
    """Real handoff/installation must keep old score pins through replacement."""
    from datetime import datetime,timedelta
    from hashlib import sha256
    import json,os
    import household_native_history as history
    import household_native_install as install
    from household_native_training import save,directory
    from test_household_native_handoff import retirement_upgrade_fixture
    handoff,family,kwargs,proof,refs,binding,selected=retirement_upgrade_fixture(tmp_path,monkeypatch)
    now=datetime.fromisoformat(proof['assessed_at']);at=now.replace(minute=0,second=0,microsecond=0)-timedelta(hours=1)
    evidence=Path(refs[1]['stage'])/'evidence'
    plan={'inputs':{'snapshot':{'as_of':at.isoformat()}},'receipt_sha256':'a'*64}
    raw=json.dumps(plan,sort_keys=True,separators=(',',':')).encode();pin=sha256(raw).hexdigest()
    source=evidence/(pin+'.household-model-plan-v6.json');source.write_bytes(raw);source.chmod(0o600)
    os.utime(source,(at.timestamp(),at.timestamp()))
    store=directory(Path(proof['state_root'])/'battery-outcomes')
    old=store/'old-partial-score.json';save(old,{'horizon':'partial'})
    row=dict(plan_path=str(source),plan_sha256=pin,plan_receipt_sha256='a'*64,
        issued_at=at.isoformat(),cohort_id='b'*64,retry_after=None,score_path=str(old))
    index=dict(schema='earthship-household-battery-sample-index/v1',samples={at.isoformat():row})
    save(store/'samples.json',index)
    original=history.assess(proof['references'],now=now,guard=lambda:None,state_root=proof['state_root'])
    completed=store/'completed-score.json';save(completed,{'horizon':'completed'})
    row['score_path']=str(completed);save(store/'samples.json',index)
    fresh=history.refresh(original,now=now,guard=lambda:None)
    save(kwargs['history_proof'],fresh)
    def mutate():old.write_bytes(old.read_bytes().replace(b'partial',b'changed'))
    if damage=='before_handoff':
        mutate()
        with pytest.raises(ValueError,match='dependency changed'):
            handoff.prepare(family,**kwargs)
        assert not kwargs['output'].exists()
        return
    handoff.prepare(family,**kwargs)
    record=handoff.verify(kwargs['output'],guard=lambda:None)
    targets={role:Path(row['target']) for role,row in record['changes'].items()}
    before={path:path.read_bytes() for path in targets.values()}
    if damage=='before_install':mutate()
    elif damage=='delete_before_install':old.unlink()
    mutated=False
    def guard():
        nonlocal mutated
        if damage=='during_install' and not mutated and targets['forecast'].read_bytes()!=before[targets['forecast']]:
            mutate();mutated=True
    if damage=='unchanged':
        assert install._install_files(kwargs['output'],guard=guard)['file_count']==5
        assert old.read_bytes()==b'{"horizon":"partial"}'
        assert all(path.read_bytes()==Path(record['changes'][role]['desired']['path']).read_bytes() for role,path in targets.items())
    else:
        with pytest.raises((ValueError,OSError)):
            install._install_files(kwargs['output'],guard=guard)
        assert all(path.read_bytes()==raw for path,raw in before.items())
        if damage=='during_install':assert mutated
