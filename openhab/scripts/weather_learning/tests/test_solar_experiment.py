"""Retrospective solar forcing must retain original clocks and stay non-operational."""
from copy import deepcopy
from datetime import timedelta
import importlib
import pytest
from native_solar_fixtures import T,SITE,ARRAY,HORIZON,snapshot,geometry
from weather_learning.contracts import identity,canonical
from weather_learning.native_forecast import validate_native_forecast,make_native_component_forecast
from household_pv_components import integrate_array_components


def api():return importlib.import_module('weather_learning.solar_experiment')
def historical():
    source=snapshot(hours=36);source['historical']=True
    source['first_seen_at']=(T+timedelta(days=3)).isoformat()
    source['ingestion_completed_at']=(T+timedelta(days=3,minutes=1)).isoformat()
    source['snapshot_sha256']=identity({k:v for k,v in source.items() if k!='snapshot_sha256'})
    return source

def make(source=None,**kwargs):
    args=dict(origin=T+timedelta(hours=9),horizon_hours=2,site=SITE,assessed_at=T+timedelta(days=4),availability_basis='retrospective_assumed_full_cycle_9h')
    args.update(kwargs)
    return api().make_retrospective_forcing(historical() if source is None else source,**args)


def test_historical_component_packet_retains_later_acquisition_and_cannot_be_a_live_forecast():
    source=historical();before=canonical(source);value=make(source)
    assert value['captured_at']==(T+timedelta(days=3,minutes=1)).isoformat()
    assert value['origin']==(T+timedelta(hours=9)).isoformat()
    assert value['prospective_score'] is False and value['as_issued_forecast'] is False
    assert api().validate_retrospective_forcing(value)==value
    from weather_learning.native_forecast import _decode
    assert _decode(value['source_original'])['historical'] is True
    assert value['rows'][0]['solar']['direct_j_m2']==1080000
    with pytest.raises(ValueError):validate_native_forecast(value)
    with pytest.raises(ValueError):make_native_component_forecast(source,origin=T+timedelta(hours=9),horizon_hours=2,site=SITE,available_by=T+timedelta(hours=9))
    assert canonical(source)==before


def test_retrospective_and_prospective_packets_use_identical_shared_components_when_inputs_match():
    live=snapshot(hours=36);origin=T+timedelta(hours=1)
    native=make_native_component_forecast(live,origin=origin,horizon_hours=1,site=SITE,available_by=origin)
    retro=make(live,origin=origin,horizon_hours=1,availability_basis='retrospective_recorded_ingestion_next_whole_hour')
    args=dict(array=ARRAY,positions=geometry(count=36),origin=origin,horizon_hours=1,timezone_name='UTC',horizon_profile=HORIZON)
    a=integrate_array_components(**args,forecast=native);b=integrate_array_components(**args,forecast=retro)
    assert a['potential_pv_kwh']==pytest.approx(b['potential_pv_kwh'],abs=1e-12)
    assert b['source_support']['native_hours']==1
    assert b['prospective_score'] is False and a['evidence_class']=='original_prospective_forcing'


@pytest.mark.parametrize('changes',[
    {'origin':T+timedelta(hours=8)},
    {'assessed_at':T+timedelta(days=2)},
    {'availability_basis':'original_as_issued'},
    {'availability_basis':'retrospective_recorded_ingestion_next_whole_hour'},
])
def test_retrospective_basis_cannot_rewrite_source_availability(changes):
    with pytest.raises(ValueError):make(**changes)


def test_rehashed_retrospective_rows_or_references_must_still_replay_original_provider_bytes():
    value=make();value['rows'][0]['solar']['direct_j_m2']=0
    value['rows_sha256']=identity(value['rows']);value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
    with pytest.raises(ValueError):api().validate_retrospective_forcing(value)
    value=make();value['as_issued_forecast']=True
    value['forecast_sha256']=identity({k:v for k,v in value.items() if k!='forecast_sha256'})
    with pytest.raises(ValueError):api().validate_retrospective_forcing(value)
