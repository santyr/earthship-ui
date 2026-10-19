"""Completed native jobs retain independent evidence and are not scored twice."""
import json
from pathlib import Path
import pytest
from test_native_serving_score import queried,originals
from test_native_thermal_forecast import ISSUE
from thermal_model.forcing_capture import _canonical


def test_serving_queue_reconciles_completed_job_without_reacquiring_outcome(tmp_path,originals,monkeypatch):
    scores,model,capture,args,serving_args=queried(tmp_path,originals,monkeypatch)
    import native_thermal_live as live,native_thermal_forecast as forecasts
    from thermal_model.native_operational_io import _phase_directory
    selected=json.loads(model._selection._encoded);settings=json.loads((Path(selected['stage'])/'forecast.json').read_bytes())
    root=Path(settings['evidence_directory']);folder=_phase_directory(root,'origins',ISSUE)
    origin=forecasts.persist(folder,capture);serving_args['capture_path']=str(origin)
    delivery=dict(schema='earthship-provisional-thermal-delivery/v2',issued_at=capture['issued_at'],capture_path=str(origin),capture_sha256=capture['capture_sha256'],artifact_sha256=capture['candidate']['artifact_sha256'],runtime_sha256=capture['candidate']['runtime_sha256'],geometry_series_sha256=capture['geometry_series_sha256'],receipts=args['receipts'])
    delivery['delivery_sha256']=forecasts.digest(delivery,'delivery_sha256')
    from thermal_model.provisional_forecast import persist
    persist(folder,delivery,field='delivery_sha256',suffix='.native-provisional-delivery-v2.json',maximum=65536)
    record=scores.build_serving_source_score(**serving_args)
    score_folder=_phase_directory(root,'scores',args['assessed_at']);source_path=scores.persist_source_score(score_folder,record)
    completion=scores.build_serving_source_completion(source_path,model=model,expected_capture_sha256=capture['capture_sha256'],expected_source_score_sha256=record['source_score_sha256'],completed_at=args['assessed_at'],check_budget=lambda:None)
    scores.persist_source_completion(score_folder,completion)
    class Reader:
        def publication(self,*a,**kw):pytest.fail('completed job repeated delivery acquisition')
        def native(self,*a,**kw):pytest.fail('completed job repeated native outcome acquisition')
        def verify_unchanged(self):pass
    monkeypatch.setattr(live,'_clock',lambda:args['assessed_at']);monkeypatch.setattr(live,'monotonic',lambda:100.)
    monkeypatch.setattr(live,'_resource_preflight',lambda:None)
    result=live.score_jobs(settings,guard=lambda:None,reader=Reader(),serving_model=model,historical_selections=())
    assert result['status']=='waiting' and result['scored']==0 and result['current_revision_scored']==1
    assert len(list(root.glob('scores-*/*.native-thermal-completion-v1.json')))==1
