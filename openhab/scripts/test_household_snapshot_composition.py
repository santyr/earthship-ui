"""Layer composition preserves original identities without repeated validation.

A complete immutable prepared context remains validated on construction; derived
lower layers need not reconstruct and validate the same context repeatedly.
"""
from copy import deepcopy
import pytest
from household.codec import canonical
from test_household_measured_weather_pipeline import make


def test_measured_restore_validates_weather_once_and_preserves_exact_document(tmp_path,monkeypatch):
    from household.weather_context import PreparedWeatherContext
    from household.measured_weather_snapshot import restore_measured_weather_snapshot
    snapshot,*_=make(tmp_path,monkeypatch)
    document=snapshot.to_dict();context=snapshot.source_context
    calls=[];original=PreparedWeatherContext.__post_init__
    def checked(self):calls.append(self.content);original(self)
    monkeypatch.setattr(PreparedWeatherContext,'__post_init__',checked)
    restored=restore_measured_weather_snapshot(document,context)
    assert restored.to_dict()==document
    assert restored.source_context==context
    # Access to source_context deliberately revalidates its exposed weather
    # context, independently of the one validation during restoration.
    assert len(calls)==2

@pytest.mark.parametrize('damage',['source_receipt','prepared_weather','configuration','measured','snapshot'])
def test_composed_restore_still_rejects_every_changed_original_layer(damage,tmp_path,monkeypatch):
    from household.measured_weather_snapshot import restore_measured_weather_snapshot
    snapshot,*_=make(tmp_path,monkeypatch)
    document=deepcopy(snapshot.to_dict());context=deepcopy(snapshot.source_context)
    if damage=='source_receipt':context['power_receipt']['receipt_sha256']='a'*64
    elif damage=='prepared_weather':context['weather_inputs']['weather_sha256']='a'*64
    elif damage=='configuration':context['energy_configuration']['configuration_sha256']='a'*64
    elif damage=='measured':context['measured_weather']['measured_weather_sha256']='a'*64
    else:document['domains']['energy']['nominal_bank_kwh']['value']=999
    with pytest.raises(ValueError):restore_measured_weather_snapshot(document,context)

@pytest.mark.parametrize('kind',['weather','configuration'])
def test_direct_composition_preserves_prepared_context_type_boundary(kind,tmp_path,monkeypatch):
    from household.measured_weather_snapshot import bind_measured_weather_snapshot
    snapshot,measured,*_=make(tmp_path,monkeypatch)
    weather=snapshot.weather;configuration=snapshot.energy_configuration
    class Lookalike:
        def __init__(self,value):self.value=value
        def __getattr__(self,name):return getattr(self.value,name)
    if kind=='weather':weather=Lookalike(weather)
    else:configuration=Lookalike(configuration)
    with pytest.raises(ValueError):
        bind_measured_weather_snapshot(source_receipt=snapshot.source_receipt,source_runtime_manifest=snapshot.source_receipt['runtime_manifest'],
            weather_context=weather,energy_configuration=configuration,measured_weather=measured,code_revision='e'*40)
