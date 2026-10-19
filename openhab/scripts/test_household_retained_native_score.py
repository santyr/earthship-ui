"""Historical orchestration uses current clocks and original numerical helpers."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json
import pytest
from test_native_serving_live import fixture,originals
from test_native_thermal_forecast import ISSUE


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
