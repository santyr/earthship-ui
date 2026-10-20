"""Prospective corrections retain original values, not today's model backcasts."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import pytest
from weather_learning.contracts import identity

NOW=datetime(2026,10,20,12,tzinfo=timezone.utc)

def issue(kind='wind_m_s',hours=1):
    body=dict(schema='earthship-issued-correction/v1',kind=kind,issued_at=NOW.isoformat(),
        completed_at=(NOW+timedelta(seconds=30)).isoformat(),timezone='America/Denver',
        source_sha256='a'*64,model_sha256='b'*64,policy_sha256='c'*64,producer_sha256='d'*64,
        evidence={'original':'frozen'},targets=[dict(start=(NOW+timedelta(hours=hours)).isoformat(),
            end=(NOW+timedelta(hours=hours+1)).isoformat(),raw=10.,corrected=8.,regime='all')],automatic_actuation=False)
    return body|dict(issue_sha256=identity(body))

def state(tmp_path):return SimpleNamespace(root=tmp_path)

def outcome(work,now):
    return dict(start=work['start'],end=work['end'],assessed_at=now.isoformat(),available_at=now.isoformat(),
        value=7.,source_sha256='e'*64,measurement_health_qualified=work['kind']=='irradiance_w_m2',original={'receipts':'retained'})

def test_original_issue_is_immutable_and_conflicting_same_decision_fails(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore
    store=CorrectionStore(state(tmp_path)); original=issue();store.retain(original);store.retain(original)
    changed=issue();changed['targets'][0]['corrected']=1.;changed['issue_sha256']=identity({k:v for k,v in changed.items() if k!='issue_sha256'})
    with pytest.raises(ValueError,match='conflicting'):store.retain(changed)
    assert store.read_issue(original['issue_sha256'])==original

def test_long_target_matures_after_report_window_and_restart_is_idempotent(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path); original=issue(hours=336);CorrectionStore(s).retain(original)
    calls=[]
    def read(work,now):calls.append(work);return outcome(work,now)
    kwargs=dict(observation_policy_sha256='f'*64,read_wind=read,read_solar=read,apply=True,limit=1)
    assert monitor_corrections(s,now=NOW+timedelta(days=1),**kwargs)['observations_attempted']==0
    now=NOW+timedelta(hours=337,minutes=2)
    report=monitor_corrections(s,now=now,**kwargs)
    assert report['observations_attempted']==1
    assert report['cohorts'][0]['raw']['mae']==3
    assert report['cohorts'][0]['candidate']['mae']==1
    assert report['cohorts'][0]['measurement_health_qualified'] is False
    assert monitor_corrections(s,now=now,**kwargs)['observations_attempted']==0
    assert len(calls)==1

def test_shared_budget_missing_target_does_not_starve_and_preview_does_not_commit(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);store=CorrectionStore(s);a=issue();b=issue('irradiance_w_m2');store.retain(a);store.retain(b)
    calls=[]
    def read(work,now):calls.append(work['kind']);return None if work['kind']=='wind_m_s' else outcome(work,now)
    kwargs=dict(now=NOW+timedelta(hours=2,minutes=2),observation_policy_sha256='f'*64,read_wind=read,read_solar=read,limit=2)
    preview=monitor_corrections(s,apply=False,**kwargs);assert preview['observations_attempted']==2
    result=monitor_corrections(s,apply=True,**kwargs);assert result['states']=={'completed':1,'pending':1}
    assert len(calls)==4
    with pytest.raises(ValueError):monitor_corrections(s,apply=True,**dict(kwargs,limit=65))

def test_partial_interval_and_future_originals_rejected(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore
    original=issue();original['targets'][0]['start']=NOW.isoformat();original['targets'][0]['end']=(NOW+timedelta(hours=1)).isoformat()
    original['issue_sha256']=identity({k:v for k,v in original.items() if k!='issue_sha256'})
    with pytest.raises(ValueError,match='causal'):CorrectionStore(state(tmp_path)).retain(original)

def test_first_delivered_proxy_per_declared_local_date_only(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);store=CorrectionStore(s);a=issue('irradiance_w_m2');store.retain(a)
    b=issue('irradiance_w_m2');b['issued_at']=(NOW+timedelta(minutes=5)).isoformat();b['completed_at']=(NOW+timedelta(minutes=6)).isoformat();b['issue_sha256']=identity({k:v for k,v in b.items() if k!='issue_sha256'});store.retain(b)
    report=monitor_corrections(s,now=NOW+timedelta(hours=2,minutes=2),observation_policy_sha256='f'*64,read_wind=outcome,read_solar=outcome,apply=True,limit=8)
    assert report['observations_attempted']==1
    assert report['sampling']['irradiance_w_m2']=='first_indexed_verified_conditioned_delivery_per_site_date'

def test_publish_wind_retains_before_replacing_pointer(monkeypatch,tmp_path):
    from weather_learning import historical_serving as serving
    import weather_learning.correction_monitor as monitor
    model=dict(model_sha256='b'*64,training_end=(NOW-timedelta(days=1)).isoformat(),trained_at=(NOW-timedelta(hours=1)).isoformat())
    monkeypatch.setattr(serving,'load_selection',lambda *a,**k:(model,{'selection_sha256':'c'*64}))
    monkeypatch.setattr(serving,'predict_gain',lambda model,raw,origin:raw*.8)
    events=[]
    def retain(*a,**k):events.append('retain');raise ValueError('capacity exhausted')
    monkeypatch.setattr(monitor,'retain_wind_issue',retain)
    s=SimpleNamespace(root=tmp_path,_write=lambda *a,**k:events.append('pointer'))
    snapshot={'points':[]};archive=SimpleNamespace(read=lambda pin:snapshot)
    with pytest.raises(ValueError,match='capacity'):serving.publish_wind(archive,s,payload={'status':'READY','source':{'snapshotSha256':'a'*64}},now=NOW)
    assert events==['retain']

def test_native_discovery_requires_external_deployment_pin_and_never_executes_unverified_sources(tmp_path,monkeypatch):
    from weather_learning.correction_monitor import NativeCorrectionDiscovery
    called=[]
    import household_cycle_deploy as deploy
    monkeypatch.setattr(deploy,'verify_stage',lambda *a,**k:(_ for _ in ()).throw(ValueError('stage changed')))
    import subprocess
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:called.append(a))
    with pytest.raises(ValueError,match='stage changed'):
        NativeCorrectionDiscovery(state(tmp_path),stage=tmp_path,deployment_sha256='a'*64,now=NOW,deadline=9999999999)(None,limit=16,guard=lambda:None)
    assert called==[]

def test_native_discovery_date_inventory_is_bounded_and_includes_arrival_allowance(tmp_path):
    from weather_learning.correction_monitor import native_delivery_paths
    root=tmp_path;folder=root/('origins-'+(NOW-timedelta(days=8)).strftime('%Y%m%d'));folder.mkdir(mode=0o700)
    a=folder/('a'*64+'.native-provisional-delivery-v2.json');a.write_text('{}');a.chmod(0o600)
    assert native_delivery_paths(root,now=NOW,guard=lambda:None)==[a]
    older=root/('origins-'+(NOW-timedelta(days=10)).strftime('%Y%m%d'));older.mkdir(mode=0o700)
    (older/'ignored.native-provisional-delivery-v2.json').write_text('{}')
    assert native_delivery_paths(root,now=NOW,guard=lambda:None)==[a]

def test_optional_publication_reference_failure_is_bounded_and_isolated(tmp_path,monkeypatch,capsys):
    import weather_learning.correction_monitor as monitor
    calls=[]
    def refused(*a,**k):calls.append(k);raise OSError('private household details must not escape')
    monkeypatch.setattr(monitor,'retain_native_delivery_reference',refused)
    assert monitor.index_native_delivery_safely({'evidence_directory':str(tmp_path)},tmp_path/'delivery.json',indexed_at=NOW,guard=lambda:None) is False
    diagnostic=capsys.readouterr().err
    assert 'OSError' in diagnostic and 'private household' not in diagnostic
    assert len(calls)==1

from test_native_thermal_artifact import originals

def test_real_conditioned_publisher_keeps_validated_delivery_when_optional_index_raises(tmp_path,monkeypatch,originals,capsys):
    from test_native_thermal_live_publication import fixture,NUMERIC_ITEM,PUBLICATION_ITEM,ISSUE
    import test_thermal_weather_conditioning as conditioned
    import thermal_weather_source
    import weather_learning.correction_monitor as monitor
    live,settings,backend,clock,candidate,geometry,runtime=fixture(tmp_path,monkeypatch,originals)
    inputs=backend.collect();clock[0]=ISSUE-timedelta(seconds=30)
    monkeypatch.setattr(conditioned,'ISSUE',ISSUE)
    args,_=conditioned.bound_fixture(tmp_path/'conditioning',monkeypatch,forecast=inputs['forecast'],geometry=geometry,sensor_epoch=candidate['fit']['sensor_epochs']['outdoor'])
    proof=thermal_weather_source.collect_context(**args)
    monkeypatch.setattr(thermal_weather_source,'collect_context',lambda **kw:proof)
    called=[]
    def refused(*a,**kw):called.append(kw);raise OSError('private diagnostic')
    monkeypatch.setattr(monitor,'index_native_delivery_safely',refused)
    result=live.publish_cycle(settings,geometry=geometry,guard=lambda:None,backend=backend)
    assert result['status']=='published' and result['delivery_verified'] is True
    assert backend.puts==[NUMERIC_ITEM,PUBLICATION_ITEM] and len(called)==1
    assert 'OSError' in capsys.readouterr().err


def test_wind_hour_keeps_native_declared_station_quality_and_elapsed_mean():
    from weather_learning.correction_monitor import wind_outcome
    rows=[(NOW+timedelta(minutes=i),22.369362921) for i in range(60)]
    label=wind_outcome(rows,start=NOW,assessed_at=NOW+timedelta(hours=1,minutes=2),source_available_at=NOW+timedelta(hours=1),unit='mph')
    assert label['value']==pytest.approx(10.) and label['coverage_seconds']==3600
    assert label['measurement_health_qualified'] is False
    assert wind_outcome(rows[:20],start=NOW,assessed_at=NOW+timedelta(hours=1,minutes=2),source_available_at=NOW+timedelta(hours=1),unit='mph') is None
    with pytest.raises(ValueError,match='mph'):wind_outcome(rows,start=NOW,assessed_at=NOW+timedelta(hours=1),source_available_at=NOW,unit='m_s')

def test_raw_only_historical_delivery_does_not_consume_conditioned_daily_slot(tmp_path):
    import json
    from weather_learning.correction_monitor import retain_native_delivery_reference
    original={'schema':'earthship-provisional-thermal-origin/v2'};original['capture_sha256']=identity(original)
    capture=tmp_path/(original['capture_sha256']+'.native-provisional-origin-v2.json');capture.write_text(json.dumps(original));capture.chmod(0o600)
    header=dict(schema='earthship-provisional-thermal-delivery/v2',capture_path=str(capture),capture_sha256=original['capture_sha256'],issued_at=NOW.isoformat())
    header['delivery_sha256']=identity(header)
    path=tmp_path/(header['delivery_sha256']+'.native-provisional-delivery-v2.json');path.write_text(json.dumps(header));path.chmod(0o600)
    assert retain_native_delivery_reference(state(tmp_path),path,indexed_at=NOW+timedelta(days=1),origin='historical_header_bootstrap') is None

def test_missing_candidate_comparison_uses_matched_targets_and_retains_policy_fallback(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);original=issue();original['targets'][0].update(raw=10.,corrected=None)
    original['targets'].append(dict(start=(NOW+timedelta(hours=2)).isoformat(),end=(NOW+timedelta(hours=3)).isoformat(),raw=1.,corrected=2.,regime='all'))
    original['issue_sha256']=identity({k:v for k,v in original.items() if k!='issue_sha256'});CorrectionStore(s).retain(original)
    def read(work,now):return outcome(work,now)|dict(value=0.)
    report=monitor_corrections(s,now=NOW+timedelta(hours=4),observation_policy_sha256='f'*64,read_wind=read,read_solar=read,apply=True,limit=8)
    cohort=report['cohorts'][0]
    assert cohort['raw_all']['mae']==5.5 and cohort['raw']['mae']==1 and cohort['candidate']['mae']==2
    assert cohort['fallback_pairs']==1 and cohort['policy']['mae']==6

def test_native_discovery_failure_does_not_suppress_existing_wind_scores(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);CorrectionStore(s).retain(issue())
    def refused(*a,**kw):raise ValueError('private producer unavailable')
    report=monitor_corrections(s,now=NOW+timedelta(hours=3),observation_policy_sha256='f'*64,read_wind=outcome,read_solar=outcome,apply=True,limit=8,discover=refused)
    assert report['states']=={'completed':1}
    assert report['dependencies']==[{'component':'native_discovery','reason':'ValueError'}]

def test_wind_backlog_reserves_a_shared_budget_slot_for_proxy(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);a=issue();a['targets']=[dict(start=(NOW+timedelta(hours=i)).isoformat(),end=(NOW+timedelta(hours=i+1)).isoformat(),raw=10.,corrected=8.,regime='all') for i in range(1,5)]
    a['issue_sha256']=identity({k:v for k,v in a.items() if k!='issue_sha256'});store=CorrectionStore(s);store.retain(a);store.retain(issue('irradiance_w_m2',hours=5));calls=[]
    def read(work,now):calls.append(work['kind']);return outcome(work,now)
    report=monitor_corrections(s,now=NOW+timedelta(hours=7),observation_policy_sha256='f'*64,read_wind=read,read_solar=read,apply=True,limit=4)
    assert report['observations_attempted']==4 and calls.count('irradiance_w_m2')==1

def test_original_model_and_producer_objects_are_deduplicated_and_verified(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore
    store=CorrectionStore(state(tmp_path));model={'coefficients':[1.,2.],'original_source':'frozen'}
    name=store.retain_object(model);assert store.retain_object(model)==name
    with store.connect() as db:assert db.execute('SELECT COUNT(*) FROM objects').fetchone()[0]==1
    original=issue();original['evidence']['model_object_sha256']=name;original['issue_sha256']=identity({k:v for k,v in original.items() if k!='issue_sha256'});store.retain(original)
    with store.connect() as db:db.execute('UPDATE objects SET value=? WHERE name=?',('{}',name))
    with pytest.raises(ValueError,match='object changed'):store.read_issue(original['issue_sha256'])

def test_wind_retention_preserves_exact_original_model_file_bytes(tmp_path):
    import json
    from hashlib import sha256
    from weather_learning.correction_monitor import retain_wind_issue,CorrectionStore
    model=dict(schema='earthship-site-weather-gain/v1',kind='wind_m_s',gain=.8,training_end=(NOW-timedelta(hours=3)).isoformat(),cutoff=(NOW-timedelta(hours=2)).isoformat(),trained_at=(NOW-timedelta(hours=1)).isoformat(),automatic_actuation=False)
    model['model_sha256']=identity(model);raw=json.dumps(model,indent=3).encode();path=tmp_path/'model.json';path.write_bytes(raw);path.chmod(0o600)
    selection=dict(selection_sha256='c'*64,model_path=str(path),model_file_sha256=sha256(raw).hexdigest())
    value=dict(issued_at=NOW.isoformat(),generated_at=(NOW+timedelta(seconds=1)).isoformat(),source_snapshot_sha256='a'*64,target='hour_mean_local_station_wind_m_s',baseline='trapezoid_of_adjacent_native_instantaneous_forecasts',
        hours=[dict(start=(NOW+timedelta(hours=1)).isoformat(),end=(NOW+timedelta(hours=2)).isoformat(),raw_m_s=10.,local_m_s=8.)])
    snapshot=dict(historical=False,ingestion_completed_at=(NOW-timedelta(minutes=1)).isoformat(),site={'timezone':'America/Denver'})
    pin=retain_wind_issue(state(tmp_path),value,model=model,selection=selection,snapshot=snapshot)
    store=CorrectionStore(state(tmp_path));receipt=store.read_issue(pin);original=store.read_object(receipt['evidence']['model_object_sha256'])
    assert original['utf8'].encode()==raw and original['file_sha256']==sha256(raw).hexdigest()
    assert len(receipt['evidence']['procedure']['method_policy_sha256'])==64
    assert receipt['evidence']['procedure']['training_policy_sha256'] is None

def test_http_completion_clock_is_validated_after_read_without_changing_issue_selection(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);CorrectionStore(s).retain(issue());now=NOW+timedelta(hours=3)
    def read(work,assessed):return outcome(work,assessed+timedelta(seconds=1))
    kwargs=dict(now=now,observation_policy_sha256='f'*64,read_wind=read,read_solar=read,apply=True,limit=8)
    assert monitor_corrections(s,**kwargs)['states']=={'pending':1}
    result=monitor_corrections(s,clock=lambda:now+timedelta(hours=1,seconds=1),**dict(kwargs,now=now+timedelta(hours=1)))
    assert result['states']=={'completed':1}
    assert result['generated_at']==(now+timedelta(hours=1,seconds=1)).isoformat()

def test_publisher_reference_cursor_detects_index_replacement_or_row_reset(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,_publisher_references
    store=CorrectionStore(state(tmp_path))
    with store.connect() as db:
        db.execute('CREATE TABLE native_refs (sequence INTEGER PRIMARY KEY,name TEXT,path TEXT,indexed TEXT)')
        db.execute('INSERT INTO native_refs VALUES(1,?,?,?)',('a'*64,'/synthetic/original',NOW.isoformat()))
    rows=_publisher_references(tmp_path,after=None,limit=16)
    sequence,path,indexed,source_id,anchor=rows[0]
    cursor=dict(sequence=sequence,source=source_id,anchor=anchor)
    assert _publisher_references(tmp_path,after=cursor,limit=16)==[]
    with store.connect() as db:
        db.execute('DELETE FROM native_refs');db.execute('INSERT INTO native_refs VALUES(1,?,?,?)',('b'*64,'/synthetic/replacement',NOW.isoformat()))
    assert _publisher_references(tmp_path,after=cursor,limit=16)[0][1]=='/synthetic/replacement'

@pytest.mark.parametrize('phase',['intake','due'])
@pytest.mark.parametrize('damage',['missing','corrupt'])
def test_missing_or_corrupt_original_dependency_defers_only_its_work(tmp_path,phase,damage):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections,CONTRACT_SHA256
    s=state(tmp_path);store=CorrectionStore(s);obj={'original_model':'frozen'};pin=store.retain_object(obj)
    wind=issue();wind['evidence']['model_object_sha256']=pin;wind['issue_sha256']=identity({k:v for k,v in wind.items() if k!='issue_sha256'})
    store.retain(wind);store.retain(issue('irradiance_w_m2'))
    now=NOW+timedelta(hours=2,minutes=2)
    scope=identity(dict(contract=CONTRACT_SHA256,observation_policy_sha256='f'*64))
    if phase=='due':store.prepare(scope,now,lambda:None)
    with store.connect() as db:
        if damage=='missing':db.execute('DELETE FROM objects WHERE name=?',(pin,))
        else:db.execute('UPDATE objects SET value=? WHERE name=?',('{}',pin))
    calls=[]
    def read(work,at):calls.append(work['kind']);return outcome(work,at)
    kwargs=dict(observation_policy_sha256='f'*64,read_wind=read,read_solar=read,apply=True,limit=8)
    report=monitor_corrections(s,now=now,**kwargs)
    assert calls==['irradiance_w_m2']
    assert report['states']['completed']==1
    assert report['intake_dependencies'] or report['withheld_reasons']
    # Restoring exact frozen bytes permits bounded retry, never replacement.
    from weather_learning.contracts import canonical
    with store.connect() as db:db.execute('INSERT OR REPLACE INTO objects VALUES(?,?)',(pin,canonical(obj).decode()))
    resumed=monitor_corrections(s,now=now+timedelta(hours=1),**kwargs)
    assert resumed['states']['completed']==2
    assert calls==['irradiance_w_m2','wind_m_s']


def test_actual_proxy_transport_outage_is_deferred_without_losing_wind(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    from weather_radiation_history import RadiationHistoryUnavailable
    s=state(tmp_path);store=CorrectionStore(s);store.retain(issue());store.retain(issue('irradiance_w_m2'))
    def failed(work,now):raise RadiationHistoryUnavailable('fixture database unavailable')
    report=monitor_corrections(s,now=NOW+timedelta(hours=2,minutes=2),observation_policy_sha256='f'*64,
        read_wind=outcome,read_solar=failed,apply=True,limit=8)
    assert report['states']=={'completed':1,'pending':1}
    assert report['withheld_reasons']=={'RadiationHistoryUnavailable':1}

@pytest.mark.parametrize('timely',[False,True])
def test_arrival_allowance_uses_original_availability_not_processing_time(tmp_path,timely):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);CorrectionStore(s).retain(issue());now=NOW+timedelta(days=10)
    def read(work,at):
        label=outcome(work,at)
        label['available_at']=(NOW+timedelta(hours=3) if timely else now).isoformat()
        return label
    report=monitor_corrections(s,now=now,observation_policy_sha256='f'*64,read_wind=read,read_solar=read,apply=True,limit=8)
    assert report['states']==({'completed':1} if timely else {'expired':1})
    if not timely:assert report['withheld_reasons']=={'observation_arrival_outside_allowance':1}


def test_correction_report_separates_artifact_and_unidentified_procedure_series(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);store=CorrectionStore(s);store.retain(issue())
    other=issue();other['issued_at']=(NOW+timedelta(minutes=5)).isoformat();other['completed_at']=(NOW+timedelta(minutes=6)).isoformat()
    other['model_sha256']='1'*64;other['source_sha256']='2'*64;other['policy_sha256']='3'*64
    other['targets'][0]['corrected']=None
    other['issue_sha256']=identity({k:v for k,v in other.items() if k!='issue_sha256'});store.retain(other)
    report=monitor_corrections(s,now=NOW+timedelta(hours=2,minutes=2),observation_policy_sha256='f'*64,
        read_wind=outcome,read_solar=outcome,apply=True,limit=8)
    assert len(report['cohorts'])==2
    assert len(report['policy_cohorts'])==1
    policy=report['policy_cohorts'][0]
    assert policy['provenance_status']=='method_training_selection_policy_unidentified'
    assert policy['training_policy_sha256'] is None
    assert policy['metrics']['issued_pairs']==2
    assert policy['metrics']['raw']['count']==policy['metrics']['candidate']['count']==1
    assert policy['metrics']['raw_all']['count']==policy['metrics']['policy']['count']==2
    assert policy['metrics']['unique_targets']==1
    assert policy['by_horizon']['0-24h']['issued_pairs']==2
    assert policy['by_local_target_month']['2026-10']['issued_pairs']==2
    assert report['calibration_qualified'] is False


def test_corrupt_durable_score_is_withheld_without_rewriting_original(tmp_path):
    import json
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);store=CorrectionStore(s);store.retain(issue())
    kwargs=dict(now=NOW+timedelta(hours=3),observation_policy_sha256='f'*64,read_wind=outcome,read_solar=outcome,apply=True,limit=8)
    monitor_corrections(s,**kwargs)
    with store.connect() as db:
        key,raw=db.execute('SELECT key,score FROM work').fetchone();value=json.loads(raw);value['outcome']['value']=1000.
        changed=json.dumps(value);db.execute('UPDATE work SET score=? WHERE key=?',(changed,key))
    report=monitor_corrections(s,**kwargs)
    assert report['cohorts']==[]
    assert report['score_dependencies']=={'invalid_score_identity':1}
    with store.connect() as db:assert db.execute('SELECT score FROM work WHERE key=?',(key,)).fetchone()[0]==changed


def test_many_source_cohorts_have_explicit_bounded_public_projection(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    from weather_learning.contracts import canonical
    s=state(tmp_path);store=CorrectionStore(s)
    for i in range(16):
        original=issue(hours=3);original['issued_at']=(NOW+timedelta(minutes=5*i)).isoformat();original['completed_at']=(NOW+timedelta(minutes=5*i,seconds=30)).isoformat()
        original['producer_sha256']=f'{i:064x}';original['source_sha256']=f'{i+20:064x}'
        original['issue_sha256']=identity({k:v for k,v in original.items() if k!='issue_sha256'});store.retain(original)
    report=monitor_corrections(s,now=NOW+timedelta(hours=5),observation_policy_sha256='f'*64,read_wind=outcome,read_solar=outcome,apply=True,limit=32)
    assert len(canonical(report))<=64*1024
    assert report['projection_coverage']['artifact_cohorts_omitted']+report['projection_coverage']['procedure_cohorts_omitted']>0
    assert report['states']['completed']==16


def test_future_original_waits_without_blocking_later_indexed_mature_work(tmp_path):
    from weather_learning.correction_monitor import CorrectionStore,monitor_corrections
    s=state(tmp_path);store=CorrectionStore(s);future=issue()
    future['issued_at']=(NOW+timedelta(days=1)).isoformat();future['completed_at']=(NOW+timedelta(days=1,seconds=30)).isoformat()
    future['targets']=[dict(start=(NOW+timedelta(days=1,hours=1)).isoformat(),end=(NOW+timedelta(days=1,hours=2)).isoformat(),raw=10.,corrected=8.,regime='all')]
    future['issue_sha256']=identity({k:v for k,v in future.items() if k!='issue_sha256'});store.retain(future);store.retain(issue('irradiance_w_m2'))
    kwargs=dict(observation_policy_sha256='f'*64,read_wind=outcome,read_solar=outcome,apply=True,limit=8)
    report=monitor_corrections(s,now=NOW+timedelta(hours=3),**kwargs)
    assert report['states']=={'completed':1}
    assert report['intake_dependencies']=={'original_not_yet_available':1}
    later=monitor_corrections(s,now=NOW+timedelta(days=1,hours=3),**kwargs)
    assert later['states']=={'completed':2}
    assert later['intake_dependencies']=={}
