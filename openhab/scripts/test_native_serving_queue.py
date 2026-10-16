"""A natural-shape private delivery is scored through its owned serving receipt."""
import inspect,json
from datetime import datetime,timedelta
from pathlib import Path
import pytest
from test_native_serving_live import fixture,originals
from test_native_thermal_forecast import ISSUE


def test_serving_queue_keeps_raw_outcomes_and_single_job_completion(tmp_path,originals,monkeypatch):
    import native_thermal_live as live
    assert 'serving_model' in inspect.signature(live.score_jobs).parameters,'receipt queue context is missing'
    live,settings,model,backend,geometry,stage=fixture(tmp_path,originals,monkeypatch)
    publication=live.publish_cycle(settings,guard=lambda:None,geometry=geometry,backend=backend,serving_model=model)
    capture=json.loads(Path(publication['origin_path']).read_bytes());delivery=json.loads(Path(publication['delivery_path']).read_bytes())
    import test_native_thermal_score_sources as old
    pins=dict(runtime=model.runtime,expected_artifact_sha256=capture['candidate']['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(old,'issued',lambda *a:(capture,delivery['receipts'],pins))
        args=old.queried(tmp_path,monkeypatch,originals)
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
    monkeypatch.setattr(live,'monotonic',lambda:100.)
    monkeypatch.setattr(live,'read_native_candidate',lambda *a,**k:pytest.fail('serving queue repeated full admission'))
    import native_thermal_forecast as forecasts
    monkeypatch.setattr(forecasts,'validate_native_candidate',lambda *a,**k:pytest.fail('serving queue repeated numerical replay'))
    result=live.score_jobs(settings,guard=lambda:None,reader=Reader(),serving_model=model,historical_selections=())
    assert result['status']=='scored' and result['scored']==1 and result['current_revision_scored']==1
    root=Path(settings['evidence_directory'])
    assert len(list(root.glob('scores-*/*.native-thermal-completion-v1.json')))==1
