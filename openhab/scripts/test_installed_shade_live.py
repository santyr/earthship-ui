"""Live cycle orchestration with synthetic source/clock/transport ports.

Nothing here is a genuine source qualification or household publication.
"""
from copy import deepcopy
from datetime import datetime,timedelta
import json
from pathlib import Path
import pytest
from test_installed_shade_publication import release_case,candidate
from test_installed_shade_origin import native,weather,actions
from thermal_model.forcing_capture import _canonical


def module():
    from thermal_model import installed_shade_live
    return installed_shade_live


class FakeBackend:
    def __init__(self,m,issue,damage=None):self.m=m;self.issue=issue;self.damage=damage;self.states={};self.rows={};self.puts=[];self.collected=False
    def collect(self,*,issue,known_at):
        self.collected=True;current,proof=native(known_at)
        self.m._test_time=self.issue+timedelta(seconds=1) if self.damage=='late_collection' else self.issue-timedelta(seconds=10)
        return dict(current=current,origin_temperatures=proof,forecast=weather(issue),action_snapshot=actions(issue))
    def verify_unchanged(self):
        if self.damage=='config_drift' and self.collected:raise ValueError('synthetic drift')
    def put(self,item,state,*,preflight=None):
        assert item in ('Thermal_OriginalForecast_JSON','Thermal_Model_JSON')
        if self.damage in ('numeric_delay','main_delay','runtime_delay') and json.loads(state).get('status')!='unavailable':
            if item==('Thermal_OriginalForecast_JSON' if self.damage=='numeric_delay' else 'Thermal_Model_JSON'):
                self.m._test_time=self.issue+timedelta(seconds=55)
        if preflight is not None:preflight()
        self.puts.append((item,json.loads(state)))
        if self.damage=='failed_withdrawal' and json.loads(state).get('status')=='unavailable':raise OSError('synthetic unavailable transport')
        self.states[item]=state;self.rows[item]=dict(item=item,time=int(self.m._test_time.timestamp()*1000),state=state)
        self.m._test_time+=timedelta(milliseconds=100)
    def persisted(self,item,state,*,since):
        if (self.damage=='numeric_receipt' and item=='Thermal_OriginalForecast_JSON' or
                self.damage in ('failed_withdrawal','withdrawal_receipt') and item=='Thermal_Model_JSON' or
                self.damage=='main_receipt' and item=='Thermal_Model_JSON' and json.loads(state)['status']!='unavailable'):
            raise ValueError('synthetic missing actual receipt')
        return self.rows[item]


@pytest.fixture
def cycle(tmp_path,release_case,monkeypatch):
    m=module();issue=datetime.fromisoformat(release_case[2]['issued_at'])
    m._test_time=issue-timedelta(seconds=45);tmp_path.chmod(0o700)
    monkeypatch.setattr(m,'_clock',lambda:m._test_time)
    monkeypatch.setattr(m,'_wait_until',lambda at:setattr(m,'_test_time',at))
    from thermal_model.graduation_statistics import assess_current_predictive_skill
    from thermal_model.installed_shade_artifact import _digest
    from thermal_model.installed_shade_publication import PreparedInstalledQualification
    report=deepcopy(release_case[1]);report['assessed_at']=(issue-timedelta(seconds=45)).isoformat()
    report['statistics']=assess_current_predictive_skill(report['policy'],report['scored_pairs'],now=report['assessed_at'])
    report['report_sha256']=_digest({k:v for k,v in report.items() if k!='report_sha256'})
    source=PreparedInstalledQualification(_canonical(report),_canonical(release_case[0]),True,False,('thermal_intel.py','thermal_model/installed_shade_publication.py'))
    monkeypatch.setattr(m,'prepare_installed_qualification',lambda _:source)
    monkeypatch.setattr(m,'build_runtime_binding',lambda *args:release_case[0]['runtime'])
    from thermal_model import installed_shade_publication as publisher
    from thermal_model import installed_shade_published_origin as captures
    monkeypatch.setattr(publisher,'_clock',lambda:m._test_time)
    monkeypatch.setattr(publisher,'build_runtime_binding',lambda *args:release_case[0]['runtime'])
    monkeypatch.setattr(captures,'_clock',lambda:m._test_time)
    return m,tmp_path,issue


def test_cycle_retains_only_real_numeric_then_main_persistence_evidence(cycle,monkeypatch):
    from thermal_model.installed_shade_published_origin import read_publication_capture
    m,root,issue=cycle;backend=FakeBackend(m,issue)
    import sys
    def expose(_):raise sys.exc_info()[1]
    monkeypatch.setattr(m,'_withdraw',expose)
    result=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='published' and result['mode']=='forecast_active'
    assert [item for item,_ in backend.puts]==['Thermal_OriginalForecast_JSON','Thermal_Model_JSON']
    record=read_publication_capture(Path(result['capture_path']))
    assert record['numeric_capture']['inputs_available_at']==(issue-timedelta(seconds=10)).isoformat()
    assert record['numeric_capture']['issued_at']==issue.isoformat()
    assert record['numeric_publication']==backend.rows['Thermal_OriginalForecast_JSON']
    assert record['publication']==backend.rows['Thermal_Model_JSON']
    assert json.loads(record['publication']['state'])['release']['automaticActuation'] is False


@pytest.mark.parametrize('damage',['late_collection','config_drift','numeric_receipt','main_receipt','failed_withdrawal'])
def test_failed_input_or_actual_receipt_withdraws_without_manufacturing_capture(cycle,damage):
    m,root,issue=cycle;backend=FakeBackend(m,issue,damage)
    result=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn' if damage!='failed_withdrawal' else result['status']=='unverified_failure'
    assert not list(root.glob('*.installed-shade-origin-v3.json'))
    assert sum(item=='Thermal_OriginalForecast_JSON' for item,_ in backend.puts)<=1
    if damage in ('late_collection','config_drift'):assert all(item=='Thermal_Model_JSON' for item,_ in backend.puts)
    assert backend.puts[-1][1]['status']=='unavailable'


def test_failed_source_preparation_collects_no_inputs_and_cannot_bootstrap(cycle,monkeypatch):
    from thermal_model.installed_shade_publication import PreparedInstalledQualification
    m,root,issue=cycle;backend=FakeBackend(m,issue)
    monkeypatch.setattr(m,'prepare_installed_qualification',lambda _:PreparedInstalledQualification(None,None,False))
    result=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn' and backend.collected is False
    assert len(backend.puts)==1 and backend.puts[0][1]['status']=='unavailable'


def test_unavailable_put_acceptance_without_jdbc_proof_is_not_verified_withdrawal(cycle,monkeypatch):
    from thermal_model.installed_shade_publication import PreparedInstalledQualification
    m,root,issue=cycle;backend=FakeBackend(m,issue,'withdrawal_receipt')
    monkeypatch.setattr(m,'prepare_installed_qualification',lambda _:PreparedInstalledQualification(None,None,False))
    result=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='unverified_failure' and result['delivery_verified'] is False



def test_second_attempt_for_same_issue_never_reposts_accepted_forecast(cycle):
    m,root,issue=cycle;backend=FakeBackend(m,issue)
    first=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert first['status']=='published'
    m._test_time=issue-timedelta(seconds=45);again=FakeBackend(m,issue)
    result=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=again)
    assert result['status']=='duplicate_attempt' and again.puts==[]


def test_concurrent_cycle_lock_does_not_compete_or_withdraw_other_cycle(cycle):
    import fcntl,os
    m,root,issue=cycle;backend=FakeBackend(m,issue)
    fd=os.open(root/'.installed-shade-live.lock',os.O_RDWR|os.O_CREAT,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        result=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
        assert result['status']=='busy' and backend.puts==[] and backend.collected is False
    finally:os.close(fd)


@pytest.mark.parametrize('damage',['numeric_delay','main_delay','runtime_delay'])
def test_guard_after_send_pacing_prevents_expired_numeric_or_main_forecast(cycle,monkeypatch,damage):
    m,root,issue=cycle;backend=FakeBackend(m,issue,damage)
    if damage=='runtime_delay':
        original=m._runtime
        def delayed_runtime(prepared,artifact):
            result=original(prepared,artifact)
            if m._test_time>=issue+timedelta(seconds=55):m._test_time=issue+timedelta(minutes=5)
            return result
        monkeypatch.setattr(m,'_runtime',delayed_runtime)
    result=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='withdrawn'
    assert not list(root.glob('*.installed-shade-origin-v3.json'))
    if damage=='numeric_delay':assert [item for item,_ in backend.puts]==['Thermal_Model_JSON']
    assert all(value['status']=='unavailable' for item,value in backend.puts if item=='Thermal_Model_JSON')


def test_numeric_capture_clock_follows_actual_submillisecond_jdbc_receipt(cycle):
    from thermal_model.installed_shade_published_origin import read_publication_capture
    m,root,issue=cycle
    class MillisecondBackend(FakeBackend):
        def __init__(self,*args):super().__init__(*args);self.send_clocks={}
        def put(self,item,state,*,preflight=None):
            if item=='Thermal_OriginalForecast_JSON':self.m._test_time=self.issue+timedelta(microseconds=158077)
            sent_at=self.m._test_time
            super().put(item,state,preflight=preflight)
            self.send_clocks[item]=sent_at
            # JDBC's millisecond timestamp can fall just after HTTP send time.
            self.rows[item]['time']=int(sent_at.timestamp()*1000)+1
    backend=MillisecondBackend(m,issue)
    result=m.run_live_cycle(reference_path=root/'refs',archive=root,backend=backend)
    assert result['status']=='published' and result['delivery_verified'] is True
    record=read_publication_capture(Path(result['capture_path']))
    stored=issue.replace(microsecond=159000)
    assert backend.send_clocks['Thermal_OriginalForecast_JSON']<stored
    assert stored<=datetime.fromisoformat(record['numeric_capture']['published_at'])
    assert record['numeric_publication']==backend.rows['Thermal_OriginalForecast_JSON']


def test_jdbc_receipt_later_than_confirmation_clock_is_still_refused(monkeypatch):
    from datetime import timezone
    m=module();at=datetime(2026,10,9,21,23,5,158077,tzinfo=timezone.utc)
    monkeypatch.setattr(m,'_clock',lambda:at)
    class Backend:
        def persisted(self,item,state,*,since):
            return dict(item=item,state=state,time=int(at.timestamp()*1000)+1)
    with pytest.raises(ValueError,match='clock/state differs'):
        m._confirmed_receipt(Backend(),'Thermal_Model_JSON','{}',since=at)
