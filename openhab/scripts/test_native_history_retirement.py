"""Retirement must preserve every consumer's still eligible original."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import pytest
from household_native_training import save, directory


def test_auxiliary_index_equal_boundary_retains_its_stage(tmp_path):
    import household_native_history as history
    now=datetime(2026,10,25,8,tzinfo=timezone.utc)
    stage=directory(tmp_path/'stage'); evidence=directory(stage/'evidence')
    store=directory(tmp_path/'state'/'energy-outcomes')
    ref=dict(forecast_path=str(evidence/('a'*64+'.household-energy-forecast-v1.json')),
        forecast_sha256='a'*64,forecast_receipt_sha256='b'*64,issued_at=(now-timedelta(days=7)).isoformat(),
        cohort_id='c'*64,score_path=None,retry_after=None)
    index=dict(schema='earthship-household-solar-storage-samples/v1',samples={ref['issued_at']:ref})
    save(store/'samples.json',index)
    raw=(store/'samples.json').read_bytes()
    assert history.index_dependencies(index,store=store,now=now)=={str(stage)}
    assert history.index_dependencies(index,store=store,now=now+timedelta(seconds=1))==set()
    assert (store/'samples.json').read_bytes()==raw


@pytest.mark.parametrize('hour',['2026-10-25T09:00:00+00:00','2026-10-25T08:01:00+00:00','garbage'])
def test_index_future_nonhour_and_malformed_refuse(tmp_path,hour):
    import household_native_history as history
    index=dict(schema='earthship-household-battery-sample-index/v1',samples={hour:{}})
    with pytest.raises(ValueError):
        history.index_dependencies(index,store=tmp_path/'battery-outcomes',now=datetime(2026,10,25,8,tzinfo=timezone.utc))


def test_expired_solar_row_still_requires_closed_schema_for_pv_import(tmp_path):
    import household_native_history as history
    index=dict(schema='earthship-household-solar-storage-samples/v1',samples={'2026-10-01T00:00:00+00:00':{}})
    with pytest.raises(ValueError,match='closed'):
        history.index_dependencies(index,store=tmp_path/'energy-outcomes',now=datetime(2026,10,25,8,tzinfo=timezone.utc))


def test_final_revalidation_refuses_changed_original_and_new_retired_binding(monkeypatch):
    import household_native_history as history
    from copy import deepcopy
    now=datetime(2026,10,25,8,tzinfo=timezone.utc)
    proof=dict(schema=history.SCHEMA,assessed_at=now.isoformat(),references=[],retained=[],policies={},
        files={'original':{'sha256':'a'}},directories={},state_root='/private',retired=[],absent=[],archives_modified=False,automatic_actuation=False)
    current=deepcopy(proof);current['files']['original']['sha256']='b'
    monkeypatch.setattr(history,'assess',lambda *a,**kw:current)
    with pytest.raises(ValueError,match='changed'):history.revalidate(proof,now=now,guard=lambda:None)
    current=deepcopy(proof);current['retained']=[{'stage':'new-needed'}]
    with pytest.raises(ValueError,match='retired'):history.revalidate(proof,now=now,guard=lambda:None)


def test_known_policy_retirement_revalidates_additive_retained_binding_and_refuses_removal(tmp_path,monkeypatch):
    from test_native_active_score_history import fixture
    import household_native_history as history
    backend,refs,path,now=fixture(tmp_path,monkeypatch)
    proof=history.assess(refs,now=now,guard=lambda:None)
    assert proof['retired']==[refs[0]] and proof['retained']==refs[1:]
    assert history.revalidate(proof,now=now,guard=lambda:None)['retained']==refs[1:]
    original=path.read_bytes();value=json.loads(original);value['capture_sha256']='e'*64
    from household.codec import identity
    value['binding_sha256']=identity({k:v for k,v in value.items() if k!='binding_sha256'})
    new=path.parent/('e'*64+'.native-serving-model-binding-v1.json');save(new,value)
    assert history.revalidate(proof,now=now,guard=lambda:None)['retained']==refs[1:]
    path.unlink()
    with pytest.raises(ValueError,match='changed or missing'):history.revalidate(proof,now=now,guard=lambda:None)


@pytest.mark.parametrize('damage',['symlink','permissions','future','date'])
def test_original_native_binding_unsafe_or_wrong_date_refuses(tmp_path,monkeypatch,damage):
    from test_native_active_score_history import fixture
    import household_native_history as history
    from household.codec import identity
    backend,refs,path,now=fixture(tmp_path,monkeypatch)
    if damage=='symlink':
        other=path.with_suffix('.original');path.rename(other);path.symlink_to(other)
    elif damage=='permissions':path.chmod(0o644)
    else:
        value=json.loads(path.read_bytes());value['issued_at']=(now+timedelta(days=1) if damage=='future' else now-timedelta(days=1)).isoformat()
        value['binding_sha256']=identity({k:v for k,v in value.items() if k!='binding_sha256'});save(path,value)
    with pytest.raises(ValueError):history.assess(refs,now=now,guard=lambda:None)


def test_final_snapshot_guard_detects_directory_addition_and_file_replacement(tmp_path,monkeypatch):
    from test_native_active_score_history import fixture
    import household_native_history as history
    backend,refs,path,now=fixture(tmp_path,monkeypatch)
    proof=history.assess(refs,now=now,guard=lambda:None)
    guard=history.snapshot_guard(proof);guard()
    save(path.parent/'extra.json',{})
    with pytest.raises(ValueError,match='directory changed'):guard()


@pytest.mark.parametrize('store_name',['battery-outcomes','energy-outcomes','profiled-energy-outcomes','captured-pv-outcomes'])
def test_each_auxiliary_consumer_keeps_complete_and_pending_boundary_rows(tmp_path,store_name):
    import household_native_history as history
    now=datetime(2026,10,25,8,tzinfo=timezone.utc);schema,kind,suffix,compact=history.STORES[store_name]
    store=tmp_path/store_name;stage=tmp_path/'stage'
    ref={kind+'_path':str(stage/'evidence'/('a'*64+suffix)),kind+'_sha256':'a'*64,kind+'_receipt_sha256':'b'*64,
         'issued_at':(now-timedelta(days=7)).isoformat(),'cohort_id':'c'*64,'retry_after':None}
    ref.update({'sample_sha256':'d'*64,'score_file_sha256':'e'*64} if compact else {'score_path':str(store/'existing-score.json')})
    index={'schema':schema,'samples':{ref['issued_at']:ref}}
    assert history.index_dependencies(index,store=store,now=now)=={str(stage)}
    assert history.index_dependencies(index,store=store,now=now+timedelta(microseconds=1))==set()


@pytest.mark.parametrize('offset,retained',[(0,True),(-1,False)])
def test_candidate_only_dependency_uses_inclusive_seven_day_boundary(tmp_path,monkeypatch,offset,retained):
    from test_native_active_score_history import fixture
    import household_native_history as history
    import os
    from hashlib import sha256
    backend,refs,path,now=fixture(tmp_path,monkeypatch)
    at=now-timedelta(days=7)+timedelta(seconds=offset)
    value={'schema':'earthship-household-model-plan-receipt/v6','inputs':{'snapshot':{'as_of':at.isoformat()}}}
    raw=json.dumps(value).encode();candidate=Path(refs[0]['stage'])/'evidence'/(sha256(raw).hexdigest()+'.household-model-plan-v6.json')
    candidate.write_bytes(raw);candidate.chmod(0o600);os.utime(candidate,(at.timestamp(),at.timestamp()))
    proof=history.assess(refs,now=now,guard=lambda:None)
    assert (refs[0] in proof['retained']) is retained
    assert candidate.read_bytes()==raw


def test_valid_new_binding_to_retired_stage_refuses_sealed_dispatch(tmp_path,monkeypatch):
    from test_native_active_score_history import fixture
    import household_native_history as history
    from household.codec import identity
    backend,refs,path,now=fixture(tmp_path,monkeypatch)
    proof=history.assess(refs,now=now,guard=lambda:None)
    value=json.loads(path.read_bytes());value.update(stage=refs[0]['stage'],deployment_sha256=refs[0]['deployment_sha256'],capture_sha256='f'*64)
    value['binding_sha256']=identity({k:v for k,v in value.items() if k!='binding_sha256'})
    save(path.parent/('f'*64+'.native-serving-model-binding-v1.json'),value)
    with pytest.raises(ValueError,match='retired selection'):history.revalidate(proof,now=now,guard=lambda:None)


from test_household_energy_forecast import originals


def completed_compact_history(tmp_path,monkeypatch,originals,kind):
    """Run the original private scorer to produce real compact/raw contracts."""
    import household_native_history as history
    import household_cycle_deploy as deploy
    from hashlib import sha256
    if kind=='pv':
        from test_household_pv_score import setup
        import household_pv_score as scorer
        args,stage,state,_=setup(tmp_path,monkeypatch,originals)
        scorer.run(stage=stage,historical=[],guard=lambda:None,deadline=100.,clock=lambda:args['assessed_at'],
            monotonic=lambda:0.,state_root=state,hour_reader=lambda **kw:args['hour_sources']['1'])
        store=state/'captured-pv-outcomes'
    else:
        from test_household_profiled_score import staged
        scorer,kwargs,_,args=staged(tmp_path,monkeypatch,originals);scorer.run(**kwargs)
        stage=kwargs['stage'];state=kwargs['state_root'];store=state/'profiled-energy-outcomes'
    stage.chmod(0o700)
    native=directory(tmp_path/'native-history');config=tmp_path/'history-config.json';save(config,dict(evidence_directory=str(native)))
    save(stage/'cycle.json',dict(forecast_config=str(config)))
    record={'source_manifest':{name:sha256((Path(__file__).resolve().parents[2]/name).read_bytes()).hexdigest() for name in history.POLICIES}}
    save(stage/'deployment.json',record);reference=dict(stage=str(stage),deployment_sha256=sha256((stage/'deployment.json').read_bytes()).hexdigest())
    monkeypatch.setattr(deploy,'verify_stage',lambda *a,**kw:record)
    return history,reference,state,store,args['assessed_at']


@pytest.mark.parametrize('kind',['pv','profiled'])
def test_assess_accepts_real_completed_compact_sample_and_pinned_compressed_score(tmp_path,monkeypatch,originals,kind):
    history,reference,state,store,now=completed_compact_history(tmp_path,monkeypatch,originals,kind)
    from hashlib import sha256
    index=json.loads((store/'samples.json').read_bytes());row=next(iter(index['samples'].values()))
    suffix='.captured-pv-verified-v1.json' if kind=='pv' else '.profiled-energy-sample-v1.json'
    sample=store/(row['sample_sha256']+suffix);value=json.loads(sample.read_bytes())
    assert (sha256(sample.read_bytes()).hexdigest()==row['sample_sha256']) is (kind=='profiled')
    if kind=='pv':assert value['sample_sha256']==row['sample_sha256']
    before={p:p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    proof=history.assess([reference],now=now,guard=lambda:None,state_root=state)
    assert proof['retained']==[reference] and not proof['retired']
    assert all(p.read_bytes()==raw for p,raw in before.items())


@pytest.mark.parametrize('kind',['pv','profiled'])
@pytest.mark.parametrize('damage',['sample_binding','raw_score','cohort'])
def test_assess_refuses_changed_compact_original_bindings(tmp_path,monkeypatch,originals,kind,damage):
    history,reference,state,store,now=completed_compact_history(tmp_path,monkeypatch,originals,kind)
    from household.codec import canonical,identity
    from hashlib import sha256
    index_path=store/'samples.json';index=json.loads(index_path.read_bytes());row=next(iter(index['samples'].values()))
    if damage=='raw_score':
        suffix='.captured-pv-outcome-v1.json.gz' if kind=='pv' else '.profiled-energy-outcome-v1.json.gz'
        path=store/(row['score_file_sha256']+suffix);path.write_bytes(path.read_bytes()+b'changed')
    elif damage=='cohort':row['cohort_id']='f'*64;save(index_path,index)
    else:
        suffix='.captured-pv-verified-v1.json' if kind=='pv' else '.profiled-energy-sample-v1.json'
        sample=json.loads((store/(row['sample_sha256']+suffix)).read_bytes())
        if kind=='pv':sample['inputs']['energy_receipt_sha256']='f'*64
        else:sample['profiled_receipt_sha256']='f'*64
        sample['sample_sha256']=identity({k:v for k,v in sample.items() if k!='sample_sha256'})
        raw=canonical(sample);pin=sample['sample_sha256'] if kind=='pv' else sha256(raw).hexdigest()
        save(store/(pin+suffix),sample);row['sample_sha256']=pin;save(index_path,index)
    with pytest.raises(ValueError,match='compact|sample|score'):history.assess([reference],now=now,guard=lambda:None,state_root=state)
