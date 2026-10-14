"""Serving receipt propagation through genuine private forecast delivery archives."""
import inspect,json
from pathlib import Path
import pytest
from test_native_serving_live import fixture,originals
from test_native_thermal_forecast import ISSUE


def issued(tmp_path,originals,monkeypatch):
    import household_cycle as cycle
    assert 'serving_model' in inspect.signature(cycle.load_cycle_delivery).parameters, 'cycle serving context is missing'
    live,settings,model,backend,geometry,stage=fixture(tmp_path,originals,monkeypatch)
    publication=live.publish_cycle(settings,guard=lambda:None,geometry=geometry,backend=backend,serving_model=model)
    return cycle,publication,model,settings


def test_cycle_delivery_replays_serving_originals_without_candidate_numerical_replay(tmp_path,originals,monkeypatch):
    cycle,publication,model,settings=issued(tmp_path,originals,monkeypatch)
    import native_thermal_forecast as forecasts
    monkeypatch.setattr(forecasts,'validate_native_candidate',lambda *a,**kw:pytest.fail('cycle repeated full candidate replay'))
    capture=json.loads(Path(publication['origin_path']).read_bytes())
    restored=cycle.load_cycle_delivery(publication,issue=ISSUE,guard=lambda:None,serving_model=model,expected_capture_sha256=capture['capture_sha256'])
    assert restored['capture']==capture and restored['native'] is True
    restored['verify_unchanged']()
    Path(settings['candidate_path']).write_bytes(b'{}')
    with pytest.raises(ValueError):restored['verify_unchanged']()


def test_complete_cycle_passes_owned_context_to_household_preparation(tmp_path,originals,monkeypatch):
    import household_cycle as cycle
    assert 'serving_model' in inspect.signature(cycle.complete_cycle).parameters, 'completion serving context is missing'
    cycle,publication,model,settings=issued(tmp_path,originals,monkeypatch)
    import household.weather_context as weather
    import household_pipeline,household_observation
    import native_thermal_forecast as forecasts
    capture=json.loads(Path(publication['origin_path']).read_bytes());seen=[]
    real=weather.prepare_serving_native_cycle_contexts
    def prepared(value,actual_model,**kwargs):
        assert actual_model is model;seen.append('prepared');return real(value,actual_model,**kwargs)
    monkeypatch.setattr(weather,'prepare_serving_native_cycle_contexts',prepared)
    monkeypatch.setattr(forecasts,'validate_native_candidate',lambda *a,**kw:pytest.fail('completion repeated full candidate replay'))
    def derive(**kwargs):
        assert kwargs['weather'].original_capture==capture
        assert kwargs['thermal'].to_dict()['original_capture_sha256']==capture['capture_sha256']
        seen.append('derived');return {'fixture_record':True}
    monkeypatch.setattr(cycle,'derive_cycle',derive)
    monkeypatch.setattr(household_pipeline,'verify_source_closure',lambda *a:None)
    monkeypatch.setattr(cycle,'_retain_original',lambda *a:Path(publication['origin_path']))
    monkeypatch.setattr(household_observation,'materialize',lambda *a,**kw:{'status':'fixture_materialized'})
    result=cycle.complete_cycle(publication=publication,collection={'status':'collected','issue':ISSUE,'originals':{}},parameter_record=None,runtime_manifest=None,code_revision='a'*40,evidence_directory=None,observation_cache=None,guard=lambda:None,clock=lambda:ISSUE,serving_model=model,expected_capture_sha256=capture['capture_sha256'])
    assert result=={'status':'fixture_materialized'} and seen==['prepared','derived']
