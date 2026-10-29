"""Historical orchestration uses current clocks and original numerical helpers."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import pytest
from test_native_serving_live import fixture,originals
from test_native_thermal_forecast import ISSUE


@pytest.fixture
def reviewed_native_source():
    import hashlib
    import native_thermal_live as native
    # Independent reviewed pin: never derive the expected digest from this file.
    source=Path(native.__file__).absolute()
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='28714d64f977cb9e7fd25eed7295336baa2870f2062a4ce17a86ad7a8f3c6cbc'
    return source


@pytest.fixture(params=['legacy_hash_boundary','reviewed_successor_bytes'])
def supported_native_source(request,tmp_path,monkeypatch,reviewed_native_source):
    import hashlib
    import native_thermal_live as native
    if request.param=='legacy_hash_boundary':
        # Dispatch-only stub: actual archived-runtime byte qualification is separate.
        raw=b'# legacy native source hash-boundary fixture\n'
        source=tmp_path/'legacy-native.py';source.write_bytes(raw);source.chmod(0o644)
        original=hashlib.sha256
        class LegacyDigest:
            def hexdigest(self):return '61851a694333d3cd66c24e8e71aab016631844a34b09411c6816c74e0e5c11f8'
        monkeypatch.setattr(hashlib,'sha256',lambda value=b'':LegacyDigest() if value==raw else original(value))
        monkeypatch.setattr(native,'__file__',str(source))
    else:source=reviewed_native_source
    return source


def test_supported_native_source_selects_existing_endpoint_reader(supported_native_source):
    import household_retained_native_score as retained,household_native_score_queries as queries
    assert retained._reader_factory() is queries.RecentCycleWindowReader


def prepared(tmp_path,originals,monkeypatch):
    live,settings,model,backend,geometry,stage=fixture(tmp_path,originals,monkeypatch)
    publication=live.publish_cycle(settings,guard=lambda:None,geometry=geometry,backend=backend,serving_model=model)
    capture=json.loads(Path(publication['origin_path']).read_bytes());delivery=json.loads(Path(publication['delivery_path']).read_bytes())
    import test_native_thermal_score_sources as old
    pins=dict(runtime=model.runtime,expected_artifact_sha256=capture['candidate']['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(old,'issued',lambda *a:(capture,delivery['receipts'],pins))
        args=old.queried(tmp_path,monkeypatch,originals)
    args['capture_path']=publication['origin_path']
    grid={at:value for at,value in args['recent_cycle_grid']};grid[(ISSUE+timedelta(hours=1)).isoformat()]=args['outcome']
    class Reader:
        native_source_paths=args['source_paths']
        def publication(self,receipt):return receipt
        def verify_unchanged(self):pass
        def native(self,targets,*,assessed_at,sensor_epoch):
            assert sensor_epoch==capture['candidate']['fit']['sensor_epochs']['air']
            return [(target,None if grid.get(target.isoformat()) is None else
                {key:datetime.fromisoformat(value) if key in ('receivedAt','storedAt','validUntil') else value
                 for key,value in grid[target.isoformat()].items()}) for target in targets]
    monkeypatch.setattr(live,'_clock',lambda:args['assessed_at'])
    return live,settings,model,Reader(),args,stage


def test_retained_job_past_fifty_seconds_preserves_full_original_score(tmp_path,originals,monkeypatch):
    import household_retained_native_score as retained,native_thermal_score as scores
    live,settings,model,reader,args,stage=prepared(tmp_path,originals,monkeypatch)
    # Independent full replay supplies the expected numerical/source record.
    normalized=[[datetime.fromisoformat(at).astimezone(timezone.utc).isoformat(),value] for at,value in args['recent_cycle_grid']]
    expected=scores.build_source_score(**dict(args,recent_cycle_grid=sorted(normalized,key=lambda row:row[0])))
    ticks=[0.];build=scores.build_serving_source_score
    def slow_original(**kwargs):
        ticks[0]=76.;return build(**kwargs)
    monkeypatch.setattr(scores,'build_serving_source_score',slow_original)
    monkeypatch.setattr(live,'score_jobs',lambda *a,**k:pytest.fail('archived fifty-second orchestration executed'))
    result=retained.score_jobs(settings,guard=lambda:None,reader=reader,serving_model=model,
        deadline=120.,clock=lambda:args['assessed_at'],monotonic=lambda:ticks[0])
    assert result==dict(status='scored',scored=1,current_revision_scored=1,automatic_actuation=False)
    path=next(Path(settings['evidence_directory']).glob('scores-*/*.native-thermal-score-sources-v1.json'))
    actual=json.loads(path.read_bytes())
    assert actual==expected
    assert len(list(Path(settings['evidence_directory']).glob('scores-*/*.native-thermal-completion-v1.json')))==1


def test_retained_job_cannot_renew_the_outer_budget(tmp_path,originals,monkeypatch):
    import household_retained_native_score as retained,native_thermal_score as scores
    live,settings,model,reader,args,stage=prepared(tmp_path,originals,monkeypatch)
    ticks=[100.];build=scores.build_serving_source_score
    def overrun(**kwargs):
        ticks[0]=121.;return build(**kwargs)
    monkeypatch.setattr(scores,'build_serving_source_score',overrun)
    with pytest.raises(ValueError,match='native scoring deadline exceeded'):
        retained.score_jobs(settings,guard=lambda:None,reader=reader,serving_model=model,
            deadline=120.,clock=lambda:args['assessed_at'],monotonic=lambda:ticks[0])
    assert not list(Path(settings['evidence_directory']).glob('scores-*/*.native-thermal-completion-v1.json'))


def outer_context(tmp_path,monkeypatch):
    import household_retained_native_score as retained,native_thermal_live as live
    import native_model_serving_receipt as admission
    from test_household_forecast_score import runtime_setup
    from test_household_score_pressure import monitor
    config,now=runtime_setup(tmp_path,monkeypatch,mock_native_pressure=False)
    settings=json.loads(config.read_bytes());settings['schema']=live.SERVING_SCHEMA
    config.write_text(json.dumps(settings));config.chmod(0o600)
    (tmp_path/'cycle.json').write_text(json.dumps(dict(forecast_config=str(config))))
    (tmp_path/'cycle.json').chmod(0o600)
    monkeypatch.setattr(live,'load_settings',lambda _:settings)
    def admitted(*a,**kw):kw['guard']();return object()
    monkeypatch.setattr(admission,'load_serving_selection',admitted)
    monkeypatch.setattr(admission,'read_serving_model',admitted)
    pressure,ticks,_,events=monitor(tmp_path)
    options=dict(stage=tmp_path,deployment_sha256='a'*64,deadline=120.,resource_preflight=lambda:None,
        pressure_factory=lambda:pressure,source_guard=lambda:None,verify_archive=lambda:None,
        clock=lambda:now,monotonic=lambda:ticks[0])
    return retained,config,options,ticks,events,now


@pytest.mark.parametrize('damage',['deadline','configuration','memory_event','forecast_window','archive'])
def test_retained_outer_guard_still_refuses_changed_runtime_state(tmp_path,monkeypatch,damage):
    retained,config,options,ticks,events,now=outer_context(tmp_path,monkeypatch)
    if damage=='archive':
        def changed():raise ValueError('archive changed')
        options['verify_archive']=changed
    clocks=[now];options['clock']=lambda:clocks[0]
    def scored(*args,**kwargs):
        kwargs['guard']()
        if damage=='deadline':ticks[0]=121.
        elif damage=='configuration':config.write_text('{}')
        elif damage=='memory_event':events.write_text('max 1\noom 0\noom_kill 0\n')
        elif damage=='forecast_window':clocks[0]=now+timedelta(minutes=3)
        return dict(status='waiting')
    monkeypatch.setattr(retained,'score_jobs',scored)
    with pytest.raises(ValueError):retained.run(config,**options)


def test_retained_outer_guard_checks_deadline_spent_admitting_the_model(tmp_path,monkeypatch):
    retained,config,options,ticks,events,now=outer_context(tmp_path,monkeypatch)
    import native_model_serving_receipt as admission
    def exhausted(*args,**kwargs):ticks[0]=121.;return object()
    monkeypatch.setattr(admission,'read_serving_model',exhausted)
    monkeypatch.setattr(retained,'score_jobs',lambda *a,**k:pytest.fail('expired admission started a new work budget'))
    with pytest.raises(ValueError,match='score lifetime elapsed'):retained.run(config,**options)


def test_retained_default_reader_uses_operational_batch_path_with_same_guard(tmp_path,originals,monkeypatch,reviewed_native_source):
    """The selected reader, including post-acquisition checks, is operational."""
    import household_retained_native_score as retained
    import household_native_score_queries as queries
    live,settings,model,reader,args,stage=prepared(tmp_path,originals,monkeypatch)
    observed=[];guards=[]
    def selected(config,*,shared_lock_guard):
        assert config=={**{key:settings[key] for key in ('token_file','native_db_config','native_policy','openhab_base')},
            'schema':live.COMPRESSED_SOURCE_SCHEMA,
            'output_directory':str(Path(settings['evidence_directory'])/('scores-'+args['assessed_at'].strftime('%Y%m%d')))}
        shared_lock_guard();observed.append(reader);return reader
    monkeypatch.setattr(queries,'RecentCycleWindowReader',selected)
    monkeypatch.setattr(live,'NativeScoreReader',lambda *a,**kw:pytest.fail('retained path selected archived acquisition-lifetime reader'))
    result=retained.score_jobs(settings,guard=lambda:guards.append(True),serving_model=model,
        deadline=120.,clock=lambda:args['assessed_at'],monotonic=lambda:0.)
    assert result['scored']==1 and observed==[reader] and guards


@pytest.mark.parametrize('source_kind',['unknown','modified_successor'])
def test_unknown_archived_reader_keeps_original_path(tmp_path,monkeypatch,source_kind):
    import household_retained_native_score as retained,native_thermal_live as native
    raw=b'# unknown immutable archived runtime\n' if source_kind=='unknown' else Path(native.__file__).read_bytes()+b'\n# unreviewed successor\n'
    source=tmp_path/'native_thermal_live.py';source.write_bytes(raw);source.chmod(0o644)
    monkeypatch.setattr(native,'__file__',str(source))
    monkeypatch.setattr(retained,'__file__',str(tmp_path/'retained.py'))
    assert retained._reader_factory() is native.NativeScoreReader


def test_retained_reader_refuses_changed_current_helper_before_execution(tmp_path,monkeypatch,supported_native_source):
    import household_retained_native_score as retained
    helper=tmp_path/'household_native_score_queries.py';helper.write_text("raise AssertionError('unverified source executed')\n");helper.chmod(0o644)
    monkeypatch.setattr(retained,'__file__',str(tmp_path/'household_retained_native_score.py'))
    with pytest.raises(ValueError,match='operational reader source differs'):retained._reader_factory()


def test_retained_reader_loads_current_sibling_in_archived_import_context(tmp_path,monkeypatch,supported_native_source):
    import household_retained_native_score as retained,household_native_score_queries as queries
    monkeypatch.setattr(queries,'__file__',str(tmp_path/'archived-queries.py'))
    selected=retained._reader_factory()
    assert Path(selected.native.__code__.co_filename).absolute()==Path(retained.__file__).absolute().with_name('household_native_score_queries.py')
    assert selected.__name__=='RecentCycleWindowReader'


@pytest.mark.parametrize('source',['native','helper'])
def test_retained_reader_rejects_source_permissions_before_selection(tmp_path,monkeypatch,source,supported_native_source):
    import household_retained_native_score as retained,native_thermal_live as native
    path=tmp_path/('native.py' if source=='native' else 'household_native_score_queries.py')
    path.write_text('# nonimmutable source\n');path.chmod(0o666)
    if source=='native':monkeypatch.setattr(native,'__file__',str(path))
    else:monkeypatch.setattr(retained,'__file__',str(tmp_path/'retained.py'))
    with pytest.raises(ValueError):retained._reader_factory()


def test_selected_operational_reader_source_joins_original_boundary_inventory(tmp_path,monkeypatch,reviewed_native_source):
    import household_retained_native_score as retained,household_native_score_queries as queries
    from thermal_model.replay_budget import capture_source_reads
    helper=tmp_path/'household_native_score_queries.py';helper.write_bytes(Path(queries.__file__).read_bytes());helper.chmod(0o644)
    monkeypatch.setattr(retained,'__file__',str(tmp_path/'retained.py'))
    with capture_source_reads() as originals:
        retained._reader_factory()
        assert helper in originals.records and reviewed_native_source in originals.records
        originals.verify()
        helper.write_bytes(helper.read_bytes()+b'\n# changed after selection\n')
        with pytest.raises(ValueError,match='source'):originals.verify()


def test_retained_reader_never_imports_unselected_archived_query_helper(tmp_path,monkeypatch,supported_native_source):
    import sys
    import household_retained_native_score as retained
    helper=tmp_path/'household_native_score_queries.py';helper.write_text("raise AssertionError('unselected archived helper executed')\n")
    monkeypatch.delitem(sys.modules,'household_native_score_queries',raising=False);monkeypatch.syspath_prepend(str(tmp_path))
    selected=retained._reader_factory()
    assert Path(selected.native.__code__.co_filename).absolute()==Path(retained.__file__).absolute().with_name('household_native_score_queries.py')


def test_retained_config_guard_checks_bytes_without_reparsing_each_boundary(tmp_path,monkeypatch):
    """Every boundary keeps strict metadata; immutable bytes need one parse."""
    import thermal_model.policy_registration as policy
    from thermal_model.replay_budget import capture_source_reads
    retained,config,options,ticks,events,now=outer_context(tmp_path,monkeypatch)
    original=policy.json.loads;parses=[]
    def parsed(*a,**kw):parses.append(True);return original(*a,**kw)
    monkeypatch.setattr(policy.json,'loads',parsed)
    def scored(settings,*,guard,**kw):
        before=len(parses)
        with capture_source_reads() as first:
            guard();guard()
            assert config in first.records
            first.verify()
        with capture_source_reads() as second:
            guard();guard()
            assert config in second.records
            second.verify()
        assert len(parses)==before,'unchanged full metadata/bytes were needlessly reread and JSON-parsed at every guard'
        return {'status':'waiting'}
    monkeypatch.setattr(retained,'score_jobs',scored)
    assert retained.run(config,**options)=={'status':'waiting'}


@pytest.mark.parametrize('damage',['settings','same_bytes_replace','parent_mode','file_mode','symlink','content','duplicate_key','nonfinite'])
def test_retained_config_guard_preserves_original_mutation_refusals(tmp_path,monkeypatch,damage):
    retained,config,options,ticks,events,now=outer_context(tmp_path,monkeypatch)
    def scored(settings,*,guard,**kw):
        guard()
        if damage=='settings':settings['schema']='mutated in-memory settings'
        elif damage=='same_bytes_replace':
            replacement=config.with_name('replacement');replacement.write_bytes(config.read_bytes());replacement.chmod(0o600);replacement.replace(config)
        elif damage=='parent_mode':config.parent.chmod(0o755)
        elif damage=='file_mode':config.chmod(0o644)
        elif damage=='symlink':
            original=config.with_name('original');config.rename(original);config.symlink_to(original)
        elif damage=='duplicate_key':config.write_text('{"schema":"one","schema":"two"}')
        elif damage=='nonfinite':config.write_text('{"schema":NaN}')
        else:config.write_bytes(config.read_bytes()+b' ')
        guard();pytest.fail('changed original configuration accepted')
    monkeypatch.setattr(retained,'score_jobs',scored)
    with pytest.raises((ValueError,OSError)):retained.run(config,**options)


def test_retained_config_guard_preserves_unknown_observer_and_nested_restore(tmp_path,monkeypatch):
    from thermal_model.replay_budget import _source_reads,capture_source_reads
    retained,config,options,ticks,events,now=outer_context(tmp_path,monkeypatch)
    class Observer:
        def __init__(self):self.paths=[]
        def record(self,path,raw):self.paths.append(path)
    observer=Observer()
    def scored(settings,*,guard,**kw):
        with capture_source_reads() as outer:
            guard()
            token=_source_reads.set(observer)
            try:guard();guard()
            finally:_source_reads.reset(token)
            guard();assert config in outer.records;outer.verify()
        assert observer.paths==[config,config]
        return {'status':'waiting'}
    monkeypatch.setattr(retained,'score_jobs',scored)
    assert retained.run(config,**options)=={'status':'waiting'}


def test_unknown_configuration_reader_retains_original_per_boundary_calls(tmp_path,monkeypatch):
    import thermal_model.policy_registration as policy
    retained,config,options,ticks,events,now=outer_context(tmp_path,monkeypatch)
    original=policy._read_private;calls=[]
    def unknown(path):calls.append(path);return original(path)
    monkeypatch.setattr(policy,'_read_private',unknown)
    def scored(settings,*,guard,**kw):
        before=len(calls);guard();guard();assert len(calls)==before+2
        return {'status':'waiting'}
    monkeypatch.setattr(retained,'score_jobs',scored)
    assert retained.run(config,**options)=={'status':'waiting'}


def test_config_guard_detects_admitted_source_mutation_at_original_inventory_boundary(tmp_path,monkeypatch):
    import household_observation as observations
    from thermal_model.replay_budget import capture_source_reads
    retained,config,options,ticks,events,now=outer_context(tmp_path,monkeypatch)
    source=tmp_path/'household_observation.py';source.write_bytes(Path(observations.__file__).read_bytes());source.chmod(0o644)
    monkeypatch.setattr(observations,'__file__',str(source))
    monkeypatch.setattr(observations._private_file,'__code__',observations._private_file.__code__.replace(co_filename=str(source)))
    def scored(settings,*,guard,**kw):
        with capture_source_reads() as originals:
            guard();assert source in originals.records
            source.write_bytes(source.read_bytes()+b'\n# changed admitted original\n')
            originals.verify()
        pytest.fail('changed admitted source passed original inventory boundary')
    monkeypatch.setattr(retained,'score_jobs',scored)
    with pytest.raises(ValueError,match='source'):retained.run(config,**options)


def test_config_guard_reverts_to_original_expression_when_loaded_reader_changes(tmp_path,monkeypatch):
    import thermal_model.policy_registration as policy
    retained,config,options,ticks,events,now=outer_context(tmp_path,monkeypatch)
    original_loads=policy.json.loads;parses=[]
    def counted(*a,**kw):parses.append(True);return original_loads(*a,**kw)
    monkeypatch.setattr(policy.json,'loads',counted)
    original_reader=policy._read_private
    def scored(settings,*,guard,**kw):
        guard();before=len(parses)
        monkeypatch.setattr(policy,'_read_private',lambda path:original_reader(path))
        guard();guard();assert len(parses)==before+2
        return {'status':'waiting'}
    monkeypatch.setattr(retained,'score_jobs',scored)
    assert retained.run(config,**options)=={'status':'waiting'}
