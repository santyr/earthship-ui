"""Battery freshness must not depend on growing thermal report replay cost."""
from datetime import timedelta
import pytest
from test_native_serving_score_driver import fixture


@pytest.mark.parametrize('fails',[False,True])
def test_battery_slot_refreshes_without_reading_or_scoring_thermal_model(tmp_path,monkeypatch,fails):
    c,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,8)
    import household_battery_score as battery
    monkeypatch.setattr(c,'score_with_report',lambda *a,**kw:pytest.fail('independent battery slot ran thermal work'))
    class Pressure:
        def check(self):pass
    monkeypatch.setattr(c,'production_pressure_monitor',lambda:Pressure())
    def work(**kwargs):
        assert kwargs['stage']==stage and kwargs['historical']==[] and kwargs['deadline']==120
        kwargs['guard']();calls.append('battery')
        if fails:raise ValueError('private connection detail')
        return {'status':'battery_performance_refreshed','count':12,'automatic_actuation':False}
    monkeypatch.setattr(battery,'run',work)
    result=c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100.)
    assert result['status']==('waiting' if fails else 'monitoring_refreshed')
    assert calls.count('battery')==1 and 'read_model' not in calls and 'selected' not in calls and calls[-1]=='unlocked'
    assert result['battery_outcomes']['status']==('deferred' if fails else 'battery_performance_refreshed')
    assert 'private connection detail' not in str(result)


def test_new_timer_role_preserves_thermal_slots_and_uses_only_its_extra_opportunity():
    import household_forecast_score as c
    from datetime import datetime,timezone
    roles={m:c.score_role(datetime(2026,10,15,12,m,20,tzinfo=timezone.utc)) for m in range(20)}
    assert [m for m,r in roles.items() if r=='current']==[1,11]
    assert [m for m,r in roles.items() if r=='historical']==[16]
    assert [m for m,r in roles.items() if r=='legacy']==[6]
    assert [m for m,r in roles.items() if r=='battery']==[8,18]


def test_independent_slot_detects_changed_configuration_before_return(tmp_path,monkeypatch):
    c,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,8)
    import household_battery_score as battery
    class Pressure:
        def check(self):pass
    monkeypatch.setattr(c,'production_pressure_monitor',lambda:Pressure())
    def changed(**kw):config.write_text('{}');return {'status':'battery_performance_refreshed','count':1}
    monkeypatch.setattr(battery,'run',changed)
    with pytest.raises(ValueError):c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100.)


def test_effective_family_requires_independent_calendar_when_current_stage_declares_it(tmp_path,monkeypatch):
    import household_native_family as family
    from test_native_serving_effective import fixture as effective
    monkeypatch.setattr(family,'_extended_score_window',lambda stage:True)
    monkeypatch.setattr(family,'_independent_battery_slot',lambda stage:True,raising=False)
    install,output,pin,states=effective(tmp_path,monkeypatch)
    states['thermal-provisional-score.service']['TimeoutStartUSec']='2min 10s'
    states['thermal-provisional-score.timer']['TimersCalendar']=['*-*-* *:01/5:00 UTC','*-*-* *:08/10:20 UTC']
    assert install._verify_effective_family(output,guard=lambda:None)['deployment_sha256']==pin
    states['thermal-provisional-score.timer']['TimersCalendar']=['*-*-* *:01/5:00 UTC']
    with pytest.raises(ValueError):install._verify_effective_family(output,guard=lambda:None)


def test_only_explicit_new_stages_add_the_battery_alarm_and_preserve_forecast_definitions(tmp_path):
    import household_native_family as family
    stage=tmp_path/'stage';scripts=stage/'sources/openhab/scripts';scripts.mkdir(parents=True)
    source=scripts/'household_forecast_score.py';source.write_text('SCORE_LIFETIME_SECONDS = 120\nSCORE_CURRENT_PERIOD_MINUTES = 10\n')
    (scripts/'household_cycle.py').write_text('# original driver\n')
    template=stage/'service.conf';template.write_text('[Service]\nExecStart=/usr/bin/python3 driver.py --stage '+str(stage)+'\n');template.chmod(0o600)
    old=family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64)
    assert old['score-timer.conf']==b'[Timer]\nOnCalendar=\nOnCalendar=*-*-* *:01/5:00 UTC\n'
    source.write_text(source.read_text()+'BATTERY_SCORE_PERIOD_MINUTES = 10\nBATTERY_SCORE_OFFSET_MINUTE = 8\nBATTERY_SCORE_OFFSET_SECOND = 20\n')
    with pytest.raises(ValueError):family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64)
    (scripts/'household_battery_score.py').write_text('# sealed producer\n')
    new=family._render(stage,stage/'config.json',stage/'libraries.json',deployment_sha256='a'*64)
    assert new['score-timer.conf']==b'[Timer]\nOnCalendar=\nOnCalendar=*-*-* *:01/5:00 UTC\nOnCalendar=*-*-* *:08/10:20 UTC\n'
    assert {k:v for k,v in new.items() if k!='score-timer.conf'}=={k:v for k,v in old.items() if k!='score-timer.conf'}


@pytest.mark.parametrize('damage',['elapsed','forecast_warm'])
def test_independent_work_cannot_escape_its_final_deadline_or_forecast_margin(tmp_path,monkeypatch,damage):
    c,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,8)
    import household_battery_score as battery
    ticks=[100.];wall=[now]
    class Pressure:
        def check(self):pass
    monkeypatch.setattr(c,'production_pressure_monitor',lambda:Pressure())
    def overrun(**kw):
        if damage=='elapsed':ticks[0]=146.
        else:wall[0]=now+timedelta(seconds=76)
        return {'status':'battery_performance_refreshed','count':1}
    monkeypatch.setattr(battery,'run',overrun)
    with pytest.raises(ValueError,match='battery opportunity elapsed'):
        c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:wall[0],monotonic=lambda:ticks[0])


@pytest.mark.parametrize('setup',['stage','dispatch'])
@pytest.mark.parametrize('elapsed',[20.,46.])
def test_setup_uses_original_battery_deadline_without_renewing_it(tmp_path,monkeypatch,setup,elapsed):
    c,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,8)
    import household_battery_score as battery
    import household_cycle_deploy as deploy
    ticks=[100.]
    class Pressure:
        def check(self):pass
    monkeypatch.setattr(c,'production_pressure_monitor',lambda:Pressure())
    if setup=='stage':
        original=deploy.verify_stage
        def slow(*a,**kw):
            result=original(*a,**kw)
            if calls.count('stage_verified')==1:ticks[0]+=elapsed
            return result
        monkeypatch.setattr(deploy,'verify_stage',slow)
    else:
        original=c.read_score_dispatch
        def slow(*a,**kw):
            result=original(*a,**kw);ticks[0]+=elapsed;kw['guard']();return result
        monkeypatch.setattr(c,'read_score_dispatch',slow)
    def work(**kw):
        assert kw['deadline']==135.,'battery budget restarted after setup'
        calls.append('battery');kw['guard']()
        return {'status':'battery_performance_refreshed','count':1}
    monkeypatch.setattr(battery,'run',work)
    if elapsed>45:
        with pytest.raises(ValueError):
            c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:ticks[0])
        assert 'battery' not in calls and 'locked' not in calls
    else:
        assert c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:ticks[0])['status']=='monitoring_refreshed'
        assert calls.count('battery')==1


@pytest.mark.parametrize('fails',[False,True])
def test_optional_captured_PV_failure_preserves_existing_battery_result(tmp_path,monkeypatch,fails):
    c,config,stage,calls,model,now,dispatch=fixture(tmp_path,monkeypatch,8)
    import household_battery_score as battery
    import household_pv_score as pv
    (stage/'sources/openhab/scripts/household_pv_score.py').write_text('# optional captured-PV producer\n')
    class Pressure:
        def check(self):pass
    monkeypatch.setattr(c,'production_pressure_monitor',lambda:Pressure())
    monkeypatch.setattr(battery,'run',lambda **kw:{'status':'battery_performance_refreshed','count':2,'automatic_actuation':False})
    def work(**kw):
        assert kw['stage']==stage and kw['deadline']<=135
        kw['guard']()
        if fails:raise ValueError('private meter connection details')
        return dict(status='captured_pv_performance_refreshed',count=1,automatic_actuation=False)
    monkeypatch.setattr(pv,'run',work)
    result=c.run(config,stage=stage,deployment_sha256='a'*64,clock=lambda:now,monotonic=lambda:100.)
    assert result['battery_outcomes']['count']==2 and result['status']=='monitoring_refreshed'
    assert result['captured_pv_outcomes']['status']==('deferred' if fails else 'captured_pv_performance_refreshed')
    assert 'private meter connection details' not in str(result) and result['automatic_actuation'] is False
