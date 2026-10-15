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
