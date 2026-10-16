"""Chronological original retention and compact report publication."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import importlib
import pytest
from household.codec import canonical,loads
from test_household_battery_outcomes import context,packet


def api():return importlib.import_module('household_battery_score')


def origin(tmp_path,monkeypatch):
    plan,runtime,thermal,target,requested,rows=context(tmp_path,monkeypatch)
    path=tmp_path/(sha256(canonical(plan)).hexdigest()+'.household-model-plan-v6.json');path.write_bytes(canonical(plan));path.chmod(0o600)
    return plan,runtime,thermal,target,requested,rows,path


def test_original_scoring_retains_terminal_evidence_without_requery(tmp_path,monkeypatch):
    plan,runtime,thermal,target,requested,rows,path=origin(tmp_path,monkeypatch);calls=[]
    def read(**kw):calls.append(kw['target_at']);return packet(target,requested,rows)
    first=api().score_origin(path,previous=None,reader=read,clock=lambda:requested+timedelta(seconds=2),guard=lambda:None,
        runtime=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])
    second=api().score_origin(path,previous=first,reader=lambda **kw:pytest.fail('terminal endpoint requeried'),clock=lambda:requested+timedelta(minutes=1),guard=lambda:None,
        runtime=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])
    assert calls==[target] and first['output']['by_horizon']['1']==second['output']['by_horizon']['1']
    assert first['inputs']['endpoint_sources']==second['inputs']['endpoint_sources']


def test_retained_score_cannot_be_rebound_to_another_original(tmp_path,monkeypatch):
    plan,runtime,thermal,target,requested,rows,path=origin(tmp_path,monkeypatch)
    first=api().score_origin(path,previous=None,reader=lambda **kw:packet(target,requested,rows),clock=lambda:requested+timedelta(seconds=2),guard=lambda:None,
        runtime=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])
    first['inputs']['plan_receipt_sha256']='0'*64
    with pytest.raises(ValueError):api().score_origin(path,previous=first,reader=lambda **kw:pytest.fail('changed score read source'),clock=lambda:requested+timedelta(minutes=1),guard=lambda:None,
        runtime=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])


def test_private_publication_never_overwrites_an_unrelated_file(tmp_path):
    tmp_path.chmod(0o700);path=tmp_path/'report.json';path.write_bytes(b'{"other":1}');path.chmod(0o600)
    with pytest.raises(ValueError):api().publish(path,{'schema':'earthship-household-battery-performance/v1'},guard=lambda:None)
    assert path.read_bytes()==b'{"other":1}'


def test_score_cli_refuses_missing_original_without_private_details(tmp_path,capsys):
    module=importlib.import_module('household_battery_outcomes')
    assert module.main(['--receipt',str(tmp_path/'operator-private-score'),'--plan',str(tmp_path/'operator-private-plan')])==1
    output=capsys.readouterr();assert not output.out and 'operator-private' not in output.err


def test_scheduled_runner_publishes_hourly_report_without_requery_or_duplicate_pairs(tmp_path,monkeypatch):
    import os
    plan,runtime,thermal,target,requested,rows,path=origin(tmp_path,monkeypatch)
    stage=tmp_path/'stage';stage.mkdir(mode=0o700);evidence=stage/'evidence';evidence.mkdir(mode=0o700)
    retained=evidence/path.name;path.rename(retained)
    issued=target-timedelta(hours=1);os.utime(retained,(issued.timestamp()+14,issued.timestamp()+14))
    state=tmp_path/'state';state.mkdir(mode=0o700)
    monkeypatch.setattr(api(),'battery_runtime_manifest',lambda:runtime)
    monkeypatch.setattr(api(),'thermal_execution_runtime',lambda *args:thermal.to_dict()['executing_runtime'])
    calls=[]
    def read(**kw):calls.append(kw['target_at']);return packet(target,requested,rows)
    result=api().run(stage=stage,historical=[],guard=lambda:None,clock=lambda:requested+timedelta(seconds=2),monotonic=lambda:0.,deadline=20.,state_root=state,reader=read)
    assert result['status']=='battery_performance_refreshed' and result['count']==1
    report=loads((state/'battery-performance.json').read_bytes())
    assert report['by_horizon']['1']['count']==1 and report['by_horizon']['1']['mae_soc_pct']=={'constant_power':2.55859375,'hold_soc':5.}
    assert report['by_horizon']['6']['count']==0
    index=loads((state/'battery-outcomes/samples.json').read_bytes())
    assert len(index['samples'])==1 and calls==[target]
    second=api().run(stage=stage,historical=[],guard=lambda:None,clock=lambda:requested+timedelta(minutes=1),monotonic=lambda:0.,deadline=20.,state_root=state,reader=lambda **kw:pytest.fail('terminal source requeried'))
    assert second['count']==1 and len(loads((state/'battery-outcomes/samples.json').read_bytes())['samples'])==1
    assert (state/'battery-performance.json').stat().st_mode&0o777==0o600


def test_offline_compact_cli_replays_against_external_original(tmp_path,monkeypatch,capsys):
    plan,runtime,thermal,target,requested,rows,path=origin(tmp_path,monkeypatch)
    score=api().score_origin(path,previous=None,reader=lambda **kw:packet(target,requested,rows),clock=lambda:requested+timedelta(seconds=2),guard=lambda:None,runtime=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])
    module=importlib.import_module('household_battery_outcomes')
    monkeypatch.setattr(module,'battery_runtime_manifest',lambda:runtime)
    monkeypatch.setattr(module,'thermal_execution_runtime',lambda *args:thermal.to_dict()['executing_runtime'])
    score_path=tmp_path/'score.json';score_path.write_bytes(canonical(score));score_path.chmod(0o600)
    assert module.main(['--receipt',str(score_path),'--plan',str(path)])==0
    assert loads(capsys.readouterr().out)==score


def test_transient_endpoint_failure_is_deferred_without_repeatedly_blocking_normal_slots(tmp_path,monkeypatch):
    import os
    plan,runtime,thermal,target,requested,rows,path=origin(tmp_path,monkeypatch)
    stage=tmp_path/'stage';stage.mkdir(mode=0o700);evidence=stage/'evidence';evidence.mkdir(mode=0o700)
    retained=evidence/path.name;path.rename(retained);issued=target-timedelta(hours=1)
    os.utime(retained,(issued.timestamp()+14,issued.timestamp()+14));state=tmp_path/'state';state.mkdir(mode=0o700)
    monkeypatch.setattr(api(),'battery_runtime_manifest',lambda:runtime)
    monkeypatch.setattr(api(),'thermal_execution_runtime',lambda *args:thermal.to_dict()['executing_runtime'])
    def refused(**kw):raise ValueError('ambiguous endpoint originals')
    result=api().run(stage=stage,historical=[],guard=lambda:None,clock=lambda:requested+timedelta(seconds=2),monotonic=lambda:0.,deadline=20.,state_root=state,reader=refused)
    assert result['status']=='battery_performance_refreshed' and result['count']==0
    again=api().run(stage=stage,historical=[],guard=lambda:None,clock=lambda:requested+timedelta(minutes=1),monotonic=lambda:0.,deadline=20.,state_root=state,reader=lambda **kw:pytest.fail('failed origin retried before backoff'))
    assert again['count']==0


def scheduler_case(tmp_path,monkeypatch):
    import os
    plan,runtime,thermal,target,requested,rows,path=origin(tmp_path,monkeypatch)
    stage=tmp_path/'stage';stage.mkdir(mode=0o700);evidence=stage/'evidence';evidence.mkdir(mode=0o700)
    retained=evidence/path.name;path.rename(retained);issued=target-timedelta(hours=1)
    os.utime(retained,(issued.timestamp()+14,issued.timestamp()+14));state=tmp_path/'state';state.mkdir(mode=0o700)
    monkeypatch.setattr(api(),'battery_runtime_manifest',lambda:runtime)
    monkeypatch.setattr(api(),'thermal_execution_runtime',lambda *args:thermal.to_dict()['executing_runtime'])
    kwargs=dict(stage=stage,historical=[],guard=lambda:None,clock=lambda:requested+timedelta(seconds=2),monotonic=lambda:0.,deadline=20.,state_root=state,reader=lambda **kw:packet(target,requested,rows))
    return kwargs,plan,runtime,thermal,target,requested,rows,state,issued


def test_incompatible_historical_origin_cannot_starve_current_compatible_sample(tmp_path,monkeypatch):
    import os
    from household.codec import identity
    kw,plan,_,_,_,_,_,state,issued=scheduler_case(tmp_path,monkeypatch)
    archived=tmp_path/'archived';archived.mkdir(mode=0o700);evidence=archived/'evidence';evidence.mkdir(mode=0o700)
    old=deepcopy(plan);old['runtime_manifest']['openhab/scripts/household/capture.py']='f'*64
    old['receipt_sha256']=identity({k:v for k,v in old.items() if k!='receipt_sha256'})
    raw=canonical(old);path=evidence/(sha256(raw).hexdigest()+api().SUFFIX);path.write_bytes(raw);path.chmod(0o600)
    os.utime(path,(issued.timestamp()-3600,issued.timestamp()-3600))
    kw['historical']=[{'stage':str(archived),'deployment_sha256':'a'*64}]
    result=api().run(**kw)
    assert result['count']==1
    ref=next(iter(loads((state/'battery-outcomes/samples.json').read_bytes())['samples'].values()))
    assert ref['plan_receipt_sha256']==plan['receipt_sha256'] and ref['plan_path'].startswith(str(kw['stage']))


def test_expired_hour_is_pruned_before_removed_stage_membership_validation(tmp_path,monkeypatch):
    kw,_,_,_,_,_,_,state,issued=scheduler_case(tmp_path,monkeypatch)
    store=state/'battery-outcomes';store.mkdir(mode=0o700)
    hour=(issued-timedelta(days=8)).replace(minute=0,second=0,microsecond=0).isoformat()
    old=dict(plan_path=str(tmp_path/'removed/evidence'/('0'*64+api().SUFFIX)),plan_sha256='0'*64,plan_receipt_sha256='1'*64,issued_at=hour,cohort_id='2'*64,score_path=None,retry_after=None)
    index=store/'samples.json';index.write_bytes(canonical(dict(schema=api().INDEX_SCHEMA,samples={hour:old})));index.chmod(0o600)
    result=api().run(**kw)
    assert result['count']==1 and hour not in loads(index.read_bytes())['samples']


def test_later_horizon_failure_retains_earlier_success_and_retries_only_pending_target(tmp_path,monkeypatch):
    plan,runtime,thermal,target,_,rows,path=origin(tmp_path,monkeypatch)
    requested=target+timedelta(hours=5,minutes=5);calls=[]
    def first(**kw):
        calls.append(kw['target_at'])
        if kw['target_at']!=target:raise api().EndpointDeferred()
        return packet(target,requested,rows)
    score=api().score_origin(path,previous=None,reader=first,clock=lambda:requested+timedelta(seconds=2),guard=lambda:None,runtime=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])
    assert score['output']['by_horizon']['1']['status']=='scored'
    assert score['output']['by_horizon']['6']['status']=='pending_source'
    report=importlib.import_module('household.battery_outcomes').build_performance([score],cohort=score['output']['cohort'],generated_at=requested+timedelta(seconds=3),next_mature_at=None)
    assert report['by_horizon']['1']['count']==1 and report['by_horizon']['6']['attempted_count']==0
    def second(**kw):
        assert kw['target_at']==target+timedelta(hours=5)
        return packet(kw['target_at'],requested+timedelta(minutes=31),[(at+timedelta(hours=5),raw) for at,raw in rows])
    again=api().score_origin(path,previous=score,reader=second,clock=lambda:requested+timedelta(minutes=31,seconds=2),guard=lambda:None,runtime=runtime,thermal_runtime=thermal.to_dict()['executing_runtime'])
    assert again['inputs']['endpoint_sources']['1']==score['inputs']['endpoint_sources']['1']
    assert calls==[target,target+timedelta(hours=5)]
