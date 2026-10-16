"""Explicit receipt profile and publication guards; transport is synthetic only."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json
import pytest
from test_native_serving_forecast import context,originals
from test_native_thermal_live_publication import earlier_geometry
from test_native_thermal_forecast import ISSUE
from thermal_model.installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM


def fixture(tmp_path,originals,monkeypatch):
    import inspect,native_thermal_live as live
    assert 'serving_model' in inspect.signature(live.publish_cycle).parameters, 'receipt publisher context is missing'
    forecasts,artifacts,candidate,model,inputs,kwargs,paths=context(tmp_path,originals,monkeypatch)
    # The owned context points to this test's sealed stage; use its actual config.
    stage=Path(json.loads(model._selection._encoded)['stage'])
    settings=json.loads((stage/'forecast.json').read_bytes())
    import native_thermal_live as live
    clock=[ISSUE-timedelta(seconds=30)]
    monkeypatch.setattr(live,'_clock',lambda:clock[0])
    monkeypatch.setattr(live,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+timedelta(seconds=seconds)))
    monkeypatch.setattr(live,'_resource_preflight',lambda:None)
    class Backend:
        def __init__(self):self.states={};self.puts=[];self.damage_after_first=False
        def collect(self,**request):clock[0]=ISSUE;return deepcopy(inputs)
        def verify_unchanged(self):pass
        def put(self,item,state,*,preflight):
            preflight();self.states[item]=state;self.puts.append(item)
            if self.damage_after_first and item==NUMERIC_ITEM:Path(settings['candidate_path']).write_bytes(b'{}')
        def persisted(self,item,state,*,since):
            clock[0]+=timedelta(milliseconds=10)
            return {'item':item,'time':int(clock[0].timestamp()*1000),'state':state}
    return live,settings,model,Backend(),earlier_geometry(ISSUE),stage


def test_explicit_v3_loader_retains_owned_original_configuration(tmp_path,originals,monkeypatch):
    live,settings,model,backend,geometry,stage=fixture(tmp_path,originals,monkeypatch)
    assert live.load_settings(stage/'forecast.json')==settings


def test_receipt_publisher_delivers_same_schemas_without_full_candidate_replay(tmp_path,originals,monkeypatch):
    live,settings,model,backend,geometry,stage=fixture(tmp_path,originals,monkeypatch)
    def forbidden(*args,**kwargs):pytest.fail('receipt live publisher repeated full candidate replay')
    monkeypatch.setattr(live,'read_native_candidate',forbidden)
    result=live.publish_cycle(settings,guard=lambda:None,geometry=geometry,backend=backend,serving_model=model)
    assert result['delivery_verified'] is True
    assert backend.puts==[NUMERIC_ITEM,PUBLICATION_ITEM]
    assert json.loads(backend.states[PUBLICATION_ITEM])['version']==9
    assert json.loads(Path(result['origin_path']).read_bytes())['schema']=='earthship-provisional-thermal-origin/v2'


def test_receipt_drift_between_two_writes_never_qualifies_delivery(tmp_path,originals,monkeypatch):
    live,settings,model,backend,geometry,stage=fixture(tmp_path,originals,monkeypatch)
    backend.damage_after_first=True
    with pytest.raises(ValueError):live.publish_cycle(settings,guard=lambda:None,geometry=geometry,backend=backend,serving_model=model)
    assert backend.puts==[NUMERIC_ITEM]
    assert not list(Path(settings['evidence_directory']).glob('origins-*/*.native-provisional-delivery-v2.json'))


def test_publication_retains_selected_report_after_historical_refresh(tmp_path,originals,monkeypatch):
    from native_thermal_score import summarize
    live,settings,model,backend,geometry,stage=fixture(tmp_path,originals,monkeypatch)
    report=summarize([],artifact_sha256=settings['artifact_sha256'])
    report['assessed_at']=(ISSUE-timedelta(seconds=30)).isoformat()
    historical=summarize([],artifact_sha256='f'*64);historical['assessed_at']=report['assessed_at']
    root=Path(settings['evidence_directory'])
    live._write_native_report(root,report,lambda:None)
    live._write_native_report(root,historical,lambda:None)
    result=live.publish_cycle(settings,guard=lambda:None,geometry=geometry,backend=backend,serving_model=model)
    capture=json.loads(Path(result['origin_path']).read_bytes())
    assert result['delivery_verified'] is True and capture['monitoring_report']==report
