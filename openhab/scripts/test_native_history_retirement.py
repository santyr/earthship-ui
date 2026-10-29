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


def completed_compact_history(tmp_path,monkeypatch,originals,kind,*,pending=False):
    """Run the original private scorer to produce real compact/raw contracts."""
    import household_native_history as history
    import household_cycle_deploy as deploy
    from hashlib import sha256
    if kind=='pv':
        from test_household_pv_score import setup
        import household_pv_score as scorer
        args,stage,state,_=setup(tmp_path,monkeypatch,originals)
        kwargs=dict(stage=stage,historical=[],guard=lambda:None,deadline=100.,clock=lambda:args['assessed_at'],
            monotonic=lambda:0.,state_root=state,hour_reader=lambda **kw:args['hour_sources']['1'])
        store=state/'captured-pv-outcomes'
    else:
        from test_household_profiled_score import staged
        scorer,kwargs,_,args=staged(tmp_path,monkeypatch,originals)
        stage=kwargs['stage'];state=kwargs['state_root'];store=state/'profiled-energy-outcomes'
    initial_kwargs=dict(kwargs,hour_reader=lambda **kw:None) if pending else kwargs
    scorer.run(**initial_kwargs)
    def advance():
        later=args['assessed_at']+timedelta(minutes=11)
        scorer.run(**dict(kwargs,clock=lambda:later))
        return later
    stage.chmod(0o700)
    native=directory(tmp_path/'native-history');config=tmp_path/'history-config.json';save(config,dict(evidence_directory=str(native)))
    save(stage/'cycle.json',dict(forecast_config=str(config)))
    record={'source_manifest':{name:sha256((Path(__file__).resolve().parents[2]/name).read_bytes()).hexdigest() for name in history.POLICIES}}
    save(stage/'deployment.json',record);reference=dict(stage=str(stage),deployment_sha256=sha256((stage/'deployment.json').read_bytes()).hexdigest())
    monkeypatch.setattr(deploy,'verify_stage',lambda *a,**kw:record)
    return history,reference,state,store,args['assessed_at'],advance


@pytest.mark.parametrize('kind',['pv','profiled'])
def test_assess_accepts_real_completed_compact_sample_and_pinned_compressed_score(tmp_path,monkeypatch,originals,kind):
    history,reference,state,store,now,_=completed_compact_history(tmp_path,monkeypatch,originals,kind)
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
    history,reference,state,store,now,_=completed_compact_history(tmp_path,monkeypatch,originals,kind)
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


def mutable_history_case(tmp_path,monkeypatch,store_name='battery-outcomes'):
    """A real pending index advances while every original dependency remains."""
    from test_native_active_score_history import fixture
    from hashlib import sha256
    from types import SimpleNamespace
    import os
    import household_native_history as history
    backend,refs,binding,now=fixture(tmp_path,monkeypatch)
    evidence=Path(refs[1]['stage'])/'evidence';at=now-timedelta(hours=1)
    def original(value,suffix):
        raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode()
        path=evidence/(sha256(raw).hexdigest()+suffix)
        path.write_bytes(raw);path.chmod(0o600);os.utime(path,(at.timestamp(),at.timestamp()))
        return path,sha256(raw).hexdigest()
    plan,plan_pin=original({'inputs':{'snapshot':{'as_of':at.isoformat()}},'receipt_sha256':'a'*64},'.household-model-plan-v6.json')
    energy,energy_pin=original({'inputs':{'plan_document_sha256':plan_pin},'output':{'array_pv':{'origin':at.isoformat()}},'receipt_sha256':'b'*64},'.household-energy-forecast-v1.json')
    profile,profile_pin=original({'inputs':{'original_energy_document_sha256':energy_pin,'original_energy_receipt_sha256':'b'*64},'receipt_sha256':'c'*64},'.household-profiled-energy-v1.json')
    state=tmp_path/'.local/state/household-intel';store=directory(state/store_name)
    schema,kind,suffix,compact=history.STORES[store_name]
    source,pin,receipt=(plan,plan_pin,'a'*64) if store_name=='battery-outcomes' else (profile,profile_pin,'c'*64) if store_name=='profiled-energy-outcomes' else (energy,energy_pin,'b'*64)
    row={kind+'_path':str(source),kind+'_sha256':pin,kind+'_receipt_sha256':receipt,
        'issued_at':at.isoformat(),'cohort_id':'d'*64,'retry_after':None}
    row.update({'sample_sha256':None,'score_file_sha256':None} if compact else {'score_path':None})
    index=store/'samples.json';save(index,dict(schema=schema,samples={at.isoformat():row}))
    proof=history.assess(refs,now=now,guard=lambda:None,state_root=state)
    def advance():
        value=json.loads(index.read_bytes());value['samples'][at.isoformat()]['retry_after']=(now+timedelta(minutes=1)).isoformat();save(index,value)
    return SimpleNamespace(history=history,backend=backend,refs=refs,binding=binding,now=now,
        index=index,proof=proof,advance=advance,plan=plan,source=source)


@pytest.mark.parametrize('store_name',['battery-outcomes','energy-outcomes','profiled-energy-outcomes','captured-pv-outcomes'])
def test_retry_history_qualifies_normal_index_advance_without_changing_sealed_proof(tmp_path,monkeypatch,store_name):
    from copy import deepcopy
    case=mutable_history_case(tmp_path,monkeypatch,store_name);original=deepcopy(case.proof)
    case.advance()
    # This is the sufficient14:12 blocker in the original retained package.
    with pytest.raises(ValueError,match='dependency changed or missing'):
        case.history.revalidate(case.proof,now=case.now,guard=lambda:None)
    fresh=case.history.refresh(case.proof,now=case.now,guard=lambda:None)
    assert case.proof==original
    assert fresh['files'][str(case.index)]!=original['files'][str(case.index)]
    assert fresh['retained']==case.refs[1:]
    assert case.history.revalidate(fresh,now=case.now,guard=lambda:None)==fresh
    case.advance()
    with pytest.raises(ValueError,match='dependency changed or missing'):
        case.history.revalidate(fresh,now=case.now,guard=lambda:None)


@pytest.mark.parametrize('damage',['immutable','removed','membership','malformed_index','unowned_index','partition','policy'])
def test_retry_history_cannot_refresh_unsafe_originals_or_partition(tmp_path,monkeypatch,damage):
    case=mutable_history_case(tmp_path,monkeypatch);case.advance()
    if damage=='immutable':case.plan.write_bytes(case.plan.read_bytes()+b' ')
    elif damage=='removed':case.binding.unlink()
    elif damage=='membership':
        path=case.binding.parent/'unparsed-original.txt';path.write_bytes(b'original')
        case.proof=case.history.assess(case.refs,now=case.now,guard=lambda:None)
        path.unlink()
    elif damage=='malformed_index':save(case.index,{'schema':'wrong','samples':{}})
    elif damage=='unowned_index':case.index.chmod(0o644)
    elif damage=='partition':case.proof['retained'].append(case.proof['retired'][0])
    else:
        import household_cycle_deploy as deploy
        original=deploy.verify_stage
        def policy(*args,**kwargs):
            record=original(*args,**kwargs)
            return dict(record,source_manifest={**record['source_manifest'],'openhab/scripts/household_battery_score.py':'f'*64})
        monkeypatch.setattr(deploy,'verify_stage',policy)
    with pytest.raises((ValueError,OSError)):
        case.history.refresh(case.proof,now=case.now,guard=lambda:None)


def test_retry_history_still_refuses_new_dependency_on_originally_retired_selection(tmp_path,monkeypatch):
    from household.codec import identity
    case=mutable_history_case(tmp_path,monkeypatch);case.advance()
    value=json.loads(case.binding.read_bytes())
    value.update(stage=case.refs[0]['stage'],deployment_sha256=case.refs[0]['deployment_sha256'],capture_sha256='e'*64)
    value['binding_sha256']=identity({k:v for k,v in value.items() if k!='binding_sha256'})
    save(case.binding.parent/('e'*64+'.native-serving-model-binding-v1.json'),value)
    with pytest.raises(ValueError,match='retired selection'):
        case.history.refresh(case.proof,now=case.now,guard=lambda:None)


@pytest.mark.parametrize('store_name',['battery-outcomes','energy-outcomes'])
def test_retry_history_validates_superseded_immutable_scores_after_index_progress(tmp_path,monkeypatch,store_name):
    case=mutable_history_case(tmp_path,monkeypatch,store_name)
    old=case.index.parent/'previous-score.json';save(old,{'score_fixture':'first mature horizon'})
    index=json.loads(case.index.read_bytes());row=next(iter(index['samples'].values()));row['score_path']=str(old);save(case.index,index)
    proof=case.history.assess(case.refs,now=case.now,guard=lambda:None)
    advanced=case.index.parent/'advanced-score.json';save(advanced,{'score_fixture':'next mature horizon'})
    row['score_path']=str(advanced);save(case.index,index)
    fresh=case.history.refresh(proof,now=case.now,guard=lambda:None)
    assert str(advanced) in fresh['files']
    final=case.history.revalidate(fresh,now=case.now,guard=lambda:None)
    assert final==fresh
    case.history.snapshot_guard(final)()
    old.write_bytes(old.read_bytes()+b' ')
    with pytest.raises(ValueError,match='dependency changed or missing'):
        case.history.refresh(proof,now=case.now,guard=lambda:None)


@pytest.mark.parametrize('kind',['pv','profiled'])
def test_retry_history_accepts_actual_compact_scorer_progress_and_checks_superseded_originals(tmp_path,monkeypatch,originals,kind):
    history,reference,state,store,now,advance=completed_compact_history(tmp_path,monkeypatch,originals,kind,pending=True)
    proof=history.assess([reference],now=now,guard=lambda:None,state_root=state)
    old={Path(path):Path(path).read_bytes() for path in proof['files'] if Path(path).parent==store and Path(path).name!='samples.json'}
    later=advance();assert later.date()==now.date()
    fresh=history.refresh(proof,now=later,guard=lambda:None)
    assert fresh['retained']==[reference] and all(path.read_bytes()==raw for path,raw in old.items())
    superseded=[path for path in old if str(path) not in fresh['files']]
    assert len(superseded)==2
    final=history.revalidate(fresh,now=later,guard=lambda:None)
    assert final==fresh
    check=history.snapshot_guard(final);check()
    # Exercise both real compact contracts without re-refreshing the old proof.
    path=next(path for path in superseded if (path.suffix=='.gz') is (kind=='pv'))
    path.write_bytes(old[path]+b' ')
    with pytest.raises(ValueError,match='dependency changed or missing'):
        history.revalidate(fresh,now=later,guard=lambda:None)
    with pytest.raises(ValueError,match='dependency changed'):
        check()


@pytest.mark.parametrize('store_name',['battery-outcomes','energy-outcomes'])
@pytest.mark.parametrize('damage',['rewrite','delete'])
@pytest.mark.parametrize('phase',['revalidate','snapshot'])
def test_final_history_rejects_superseded_score_change(tmp_path,monkeypatch,store_name,damage,phase):
    """Dropping an original pin at refresh must not admit later score damage."""
    case=mutable_history_case(tmp_path,monkeypatch,store_name)
    old=case.index.parent/'old-partial-score.json';save(old,{'horizon':'partial'})
    index=json.loads(case.index.read_bytes());row=next(iter(index['samples'].values()))
    row['score_path']=str(old);save(case.index,index)
    original=case.history.assess(case.refs,now=case.now,guard=lambda:None)
    advanced=case.index.parent/'completed-score.json';save(advanced,{'horizon':'completed'})
    row['score_path']=str(advanced);save(case.index,index)
    fresh=case.history.refresh(original,now=case.now,guard=lambda:None)
    # The actual installer composes these two production consumers in this order.
    final=case.history.revalidate(fresh,now=case.now,guard=lambda:None)
    check=case.history.snapshot_guard(final);check()
    parent_before=old.parent.stat()
    if damage=='delete':old.unlink()
    else:
        raw=old.read_bytes();old.write_bytes(raw.replace(b'partial',b'changed'))
        parent_after=old.parent.stat()
        assert (parent_after.st_mtime_ns,parent_after.st_ctime_ns)==(parent_before.st_mtime_ns,parent_before.st_ctime_ns)
    with pytest.raises((ValueError,OSError)):
        if phase=='revalidate':case.history.revalidate(fresh,now=case.now,guard=lambda:None)
        else:check()
