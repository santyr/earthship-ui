"""Real clock/maturity and delivery discovery; outcome backend is synthetic."""
from datetime import timedelta
import json
import pytest
from test_provisional_thermal_live import fixture,module as live_module
from test_installed_shade_origin import outcome


def module():
    from thermal_model import provisional_monitor
    return provisional_monitor


def setup(tmp_path,monkeypatch):
    settings,backend,clock,candidate=fixture(tmp_path,monkeypatch)
    published=live_module().publish_cycle(settings,backend=backend,guard=lambda:None)
    settings['native_db_config']='synthetic';settings['native_policy']='synthetic';settings['token_file']='synthetic';settings['openhab_base']='http://127.0.0.1:8080/rest'
    clock[0]+=timedelta(hours=1,minutes=5)
    monkeypatch.setattr(module(),'_clock',lambda:clock[0])
    monkeypatch.setattr(module(),'_resource_preflight',lambda:None)
    monkeypatch.setattr(module(),'current_runtime',lambda:candidate['runtime'])
    monkeypatch.setattr(module(),'read_candidate',lambda *a,**k:candidate)
    class Reader:
        native_source_paths=[]
        def verify_unchanged(self):pass
        def publication(self,receipt):return receipt
        def native(self,targets,*,assessed_at,sensor_epoch):
            return [(at,outcome(at,75)) for at in targets]
    return settings,published,Reader()


def test_monitor_scores_only_mature_delivered_forecasts(tmp_path,monkeypatch):
    settings,_,reader=setup(tmp_path,monkeypatch)
    result=module().score_jobs(settings,guard=lambda:None,reader=reader,max_jobs=1)
    assert result['status']=='scored' and result['scored']==1
    report=json.loads((tmp_path/'archive'/'latest-provisional-performance.json').read_text())
    assert report['by_horizon']['1']['model']['count']==1
    again=module().score_jobs(settings,guard=lambda:None,reader=reader,max_jobs=1)
    assert again['scored']==0


def test_missing_completed_original_is_withheld_without_recollection(tmp_path,monkeypatch):
    settings,_,reader=setup(tmp_path,monkeypatch)
    module().score_jobs(settings,guard=lambda:None,reader=reader,max_jobs=1)
    pair=next((tmp_path/'archive').glob('scores-*/*.provisional-pair-v1.json'));pair.unlink()
    reader.native=lambda *a,**k:pytest.fail('lost completed original was recollected')
    result=module().score_jobs(settings,guard=lambda:None,reader=reader,max_jobs=1)
    assert result['status']=='withheld'


def test_lost_completed_capture_is_withheld_without_recollecting(tmp_path,monkeypatch):
    settings,published,reader=setup(tmp_path,monkeypatch)
    module().score_jobs(settings,guard=lambda:None,reader=reader,max_jobs=1)
    from pathlib import Path
    Path(published['origin_path']).unlink()
    reader.native=lambda *a,**k:pytest.fail('lost origin was recollected')
    result=module().score_jobs(settings,guard=lambda:None,reader=reader,max_jobs=1)
    assert result['status']=='withheld'
