"""Capture integration exercises the current native Google publisher."""
from copy import deepcopy
from datetime import datetime,timedelta
import importlib,json
from pathlib import Path
import pytest
from native_cycle_test_support import fixture,module as live
from test_native_thermal_forecast import ISSUE

def api():return importlib.import_module('household_cycle')

def test_collection_follows_parent_inputs_and_keeps_original_numeric_output(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    direct=live().publish_cycle(settings,backend=parent,guard=lambda:None)
    capture=json.loads(Path(direct['origin_path']).read_bytes());original=capture['output']
    issued=datetime.fromisoformat(capture['issued_at'])
    clock[0]=ISSUE-timedelta(seconds=30);calls=[]
    original_collect=parent.collect
    def collect_parent(**kw):
        value=original_collect(**kw);calls.append('parent');clock[0]+=timedelta(seconds=10);return value
    parent.collect=collect_parent
    def collect_household(*,issue,remaining,guard):
        calls.append('household');assert issue==issued
        assert 0 < remaining() <= 10
        guard();clock[0]+=timedelta(seconds=1)
        return {'original_collection_finished':clock[0].isoformat()}
    adapter=api().ObservingBackend(parent,collector=collect_household,guard=lambda:None,clock=lambda:clock[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert calls==['parent','household']
    assert result['delivery_verified'] is True
    wrapped=json.loads(Path(result['origin_path']).read_bytes())['output']
    assert wrapped==original
    assert adapter.collection['status']=='collected'
    assert adapter.collection['originals']['original_collection_finished']==(issued-timedelta(seconds=19)).isoformat()

def test_collector_failure_does_not_withdraw_or_break_original_delivery(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    def broken(**kwargs):raise ValueError('operator-only diagnostic payload')
    adapter=api().ObservingBackend(parent,collector=broken,guard=lambda:None,clock=lambda:clock[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['status']=='unavailable'
    assert 'operator-only' not in json.dumps(adapter.collection)

def test_late_window_skips_observation_and_keeps_forecast_delivery(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    original=parent.collect
    def late(**kwargs):
        value=original(**kwargs);clock[0]=kwargs['issue']-timedelta(seconds=2);return value
    parent.collect=late
    def forbidden(**kwargs):pytest.fail('late collector started')
    adapter=api().ObservingBackend(parent,collector=forbidden,guard=lambda:None,clock=lambda:clock[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['reason']=='insufficient_preissue_budget'

def test_parent_collection_failure_is_not_hidden(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    def broken(**kwargs):raise ValueError('original collection failed')
    parent.collect=broken
    adapter=api().ObservingBackend(parent,collector=lambda **kw:{},guard=lambda:None,clock=lambda:clock[0])
    with pytest.raises(ValueError,match='original collection failed'):
        live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert parent.puts==[]

def test_collection_cannot_renew_the_total_preissue_budget(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch);ticks=[0.]
    def overrun(**kwargs):
        ticks[0]+=11;clock[0]+=timedelta(seconds=11)
        return {'originals':'not accepted after budget'}
    adapter=api().ObservingBackend(parent,collector=overrun,guard=lambda:None,clock=lambda:clock[0],monotonic=lambda:ticks[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['status']=='unavailable'
    assert 'originals' not in adapter.collection

def test_backward_collection_clock_refuses_household_originals(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch);offset=[0]
    def backward(**kwargs):
        offset[0]=1
        return {'captured_at':clock[0].isoformat()}
    adapter=api().ObservingBackend(parent,collector=backward,guard=lambda:None,clock=lambda:clock[0]-timedelta(seconds=offset[0]))
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['status']=='unavailable'

def derived_fixture(tmp_path,monkeypatch):
    from household.codec import canonical
    from household.control_contracts import instant
    from household.weather_context import prepare_native_weather_context
    from household.energy_configuration import prepare_energy_configuration
    from household.measured_weather import prepare_measured_weather
    from test_household_measured_weather import sources
    from test_household_energy_source_pipeline import make
    from test_household_model_snapshot import source_at
    from test_household_model_pipeline import RUNTIME
    from test_household_models import FIXTURE
    from native_thermal_forecast import publication
    from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM
    base,configuration,prepared,capture=make(tmp_path,monkeypatch)
    issue=instant(capture['issued_at']);collected=issue-timedelta(seconds=1)
    body=configuration.to_dict()
    configuration=prepare_energy_configuration(bank_config_raw=body['bank_source']['raw'],ac_policy_raw=body['load_topology_source']['raw'],
        bank_available_at=collected,topology_available_at=collected,as_of=collected,created_at=collected)
    measured=prepare_measured_weather(sources=sources(collected),as_of=collected,created_at=collected)
    originals=dict(schema='earthship-household-cycle-sources/v1',issue=issue.isoformat(),captured_at=collected.isoformat(),
        power_receipt=source_at(collected),energy_configuration=configuration.to_dict(),measured_weather=measured.to_dict(),
        owner_bindings={'before':{},'after':{}},automatic_actuation=False)
    published=instant(capture['published_at'])
    receipts={item:{'item':item,'time':int(published.timestamp()*1000),'state':canonical(value).decode()}
        for item,value in ((NUMERIC_ITEM,capture['output']),(PUBLICATION_ITEM,publication(capture)))}
    params=dict(collected_at=(issue-timedelta(days=1)).isoformat(),record={'household_energy_inputs':FIXTURE['cases'][0]['inputs']})
    return dict(originals=originals,capture=capture,receipts=receipts,thermal=prepared,weather=prepare_native_weather_context(capture,prepared_thermal=prepared,runtime=capture['candidate']['runtime'],expected_artifact_sha256=capture['candidate']['artifact_sha256'],expected_capture_sha256=capture['capture_sha256']),
        parameter_record=params,runtime_manifest=RUNTIME,code_revision='e'*40,now=published),capture

def test_complete_cycle_derivation_preserves_original_thermal_and_current_source_soc(tmp_path,monkeypatch):
    from household.pipeline import replay_pipeline
    args,capture=derived_fixture(tmp_path,monkeypatch)
    record=api().derive_cycle(**args)
    assert record['schema']=='earthship-household-model-plan-receipt/v5'
    assert record['output']['projections']['thermal']['output']==capture['output']
    assert record['inputs']['snapshot']['as_of']==capture['issued_at']
    assert record['inputs']['snapshot']['domains']['energy']['inverter_output_w']['reason'] is None
    assert record['output']['automatic_actuation'] is False
    assert replay_pipeline(record,runtime_manifest=args['runtime_manifest'],thermal_runtime=args['thermal'].to_dict()['executing_runtime'])==record

@pytest.mark.parametrize('damage',['delivery','issue','late','parameters'])
def test_mismatched_cycle_or_unverified_originals_cannot_produce_plan(damage,tmp_path,monkeypatch):
    args,_=derived_fixture(tmp_path,monkeypatch)
    if damage=='delivery':args['receipts']={}
    if damage=='issue':args['originals']['issue']=(args['now']+timedelta(minutes=5)).isoformat()
    if damage=='late':args['originals']['captured_at']=(args['now']+timedelta(seconds=1)).isoformat()
    if damage=='parameters':args['parameter_record']['collected_at']=(args['now']+timedelta(days=1)).isoformat()
    with pytest.raises(ValueError):api().derive_cycle(**args)


def test_hard_observer_cutoff_prevents_overrun_crossing_original_issue(tmp_path,monkeypatch):
    import signal,time
    settings,parent,clock,_=fixture(tmp_path,monkeypatch)
    original=parent.collect
    def collect_parent(**kw):
        value=original(**kw);clock[0]=kw['issue']-timedelta(seconds=4);return value
    parent.collect=collect_parent;completed=[]
    def overrun(*,issue,**kw):
        # A cooperative post-return check would be too late: this operation
        # would advance the original publication clock beyond its issue.
        time.sleep(1.3);clock[0]=issue+timedelta(seconds=1);completed.append(True)
        return {'late':'source'}
    prior=signal.getsignal(signal.SIGALRM)
    adapter=api().ObservingBackend(parent,collector=overrun,guard=lambda:None,clock=lambda:clock[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['status']=='published' and result['delivery_verified'] is True
    assert completed==[]
    assert adapter.collection['reason']=='source_collection_timed_out'
    assert signal.getitimer(signal.ITIMER_REAL)==(0.,0.)
    assert signal.getsignal(signal.SIGALRM)==prior


def test_source_preflight_does_not_repeat_when_reading_remaining_budget():
    issue=ISSUE;now=issue-timedelta(seconds=20);checks=[];original={'original':'inputs'}
    class Parent:
        def collect(self,**kw):return original
    def guard():checks.append(True)
    def collect(*,remaining,guard,**kw):
        # Each source access explicitly checks its guard and then reads the
        # deadline. Repeated budget inspections must not duplicate expensive
        # cgroup/pressure verification for that same access.
        for _ in range(20):
            guard();assert 0<remaining()<=10
        return {'originals':'retained'}
    adapter=api().ObservingBackend(Parent(),collector=collect,guard=guard,clock=lambda:now)
    assert adapter.collect(issue=issue,known_at=now) is original
    assert adapter.collection['status']=='collected'
    assert len(checks)==23


def test_resource_drift_at_collector_return_still_refuses_observation():
    issue=ISSUE;now=issue-timedelta(seconds=20);changed=[False];original={'original':'inputs'}
    class Parent:
        def collect(self,**kw):return original
    def guard():
        if changed[0]:raise ValueError('resource state changed')
    def collect(**kw):changed[0]=True;return {'originals':'must be refused'}
    adapter=api().ObservingBackend(Parent(),collector=collect,guard=guard,clock=lambda:now)
    assert adapter.collect(issue=issue,known_at=now) is original
    assert adapter.collection['reason']=='source_collection_failed'


def test_healthy_eight_second_collection_fits_existing_preissue_window(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch);ticks=[0.]
    def collect(**kw):
        assert kw['remaining']()>8
        ticks[0]+=8;clock[0]+=timedelta(seconds=8)
        return {'original_collection_finished':clock[0].isoformat()}
    adapter=api().ObservingBackend(parent,collector=collect,guard=lambda:None,clock=lambda:clock[0],monotonic=lambda:ticks[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['status']=='collected'


def test_extended_collection_still_stops_at_issue_minus_three_seconds(tmp_path,monkeypatch):
    settings,parent,clock,_=fixture(tmp_path,monkeypatch);ticks=[0.]
    original=parent.collect
    def collect_parent(**kw):
        value=original(**kw);clock[0]=kw['issue']-timedelta(seconds=5);return value
    parent.collect=collect_parent
    def overrun(**kw):
        assert kw['remaining']()==2
        ticks[0]+=2.1;clock[0]+=timedelta(seconds=2.1)
        return {'after_margin':'refused'}
    adapter=api().ObservingBackend(parent,collector=overrun,guard=lambda:None,clock=lambda:clock[0],monotonic=lambda:ticks[0])
    result=live().publish_cycle(settings,backend=adapter,guard=lambda:None)
    assert result['delivery_verified'] is True
    assert adapter.collection['status']=='unavailable'
    assert 'originals' not in adapter.collection


@pytest.mark.parametrize('reason',['insufficient_preissue_budget','source_collection_timed_out','source_collection_failed','operator-only-private-text'])
def test_observer_reports_only_bounded_original_collection_reason(reason):
    result=api().complete_cycle(publication={'status':'published','delivery_verified':True},collection={'status':'unavailable','reason':reason},parameter_record=None,runtime_manifest=None,code_revision='a'*40,evidence_directory=None,observation_cache=None,guard=lambda:None)
    expected=reason if reason!='operator-only-private-text' else 'unclassified_collection_failure'
    assert result['collection_reason']==expected
    assert result['reason']=='source_collection_unavailable'
    assert 'operator-only-private-text' not in json.dumps(result)
