"""PV uses the original native weather context, never a separately fetched sky."""
from copy import deepcopy
from datetime import timedelta
import pytest
from household.codec import canonical
from household.control_contracts import instant
from test_household_native_weather import made,originals
from test_household_pv_model import source
from test_household_solar_horizon import source as horizon_source


def test_pv_forecast_uses_the_same_original_native_weather_and_geometry(tmp_path,monkeypatch,originals):
    import household_pv_model as pv_model
    capture,_,_,weather=made(tmp_path,monkeypatch,originals);at=instant(capture['issued_at'])
    out=pv_model.project_pv(weather=weather,system_source=source(at),horizon_source=horizon_source(at),now=instant(capture['published_at']))
    assert out['status']=='projected_provisional_array_potential',out['reason']
    assert len(out['trajectory'])==24 and out['potential_pv_kwh']>0
    assert out['weather_context_sha256']==weather.to_dict()['weather_sha256']
    assert out['original_capture_sha256']==capture['capture_sha256']
    assert out['geometry_series_sha256']==capture['geometry_series_sha256']
    assert out['captured_pv_kwh'] is None and out['physical_calibration_qualified'] is False
    assert out['assumptions']['dc_loss_multiplier']==.86


def test_missing_array_configuration_withholds_pv_without_mutating_thermal_weather(tmp_path,monkeypatch,originals):
    import household_pv_model as pv_model
    capture,_,_,weather=made(tmp_path,monkeypatch,originals);before=weather.content
    out=pv_model.project_pv(weather=weather,system_source=None,horizon_source=horizon_source(instant(capture['issued_at'])),now=instant(capture['published_at']))
    assert out['status']=='unavailable' and out['reason']=='pv_system_unavailable'
    assert out['trajectory']==[] and weather.content==before


def test_pv_projection_rejects_lookalikes_and_preserves_frozen_inputs_without_reads(tmp_path,monkeypatch,originals):
    import household_pv_model as pv_model
    capture,_,_,weather=made(tmp_path,monkeypatch,originals);at=instant(capture['issued_at']);system=source(at);now=instant(capture['published_at'])
    before=canonical(system);horizon=horizon_source(at);expected=pv_model.project_pv(weather=weather,system_source=system,horizon_source=horizon,now=now)
    with pytest.raises(ValueError):pv_model.project_pv(weather=weather.to_dict(),system_source=system,horizon_source=horizon_source(at),now=now)
    import builtins
    def forbidden(*a,**kw):pytest.fail('read during frozen PV projection')
    monkeypatch.setattr(builtins,'open',forbidden)
    assert pv_model.project_pv(weather=weather,system_source=system,horizon_source=horizon,now=now)==expected
    assert canonical(system)==before


def test_original_map_horizon_is_bound_to_shared_native_geometry_without_changing_weather(tmp_path,monkeypatch,originals):
    import household_pv_model as pv_model
    from test_household_solar_horizon import source as horizon_source
    from household.codec import identity
    capture,_,_,weather=made(tmp_path,monkeypatch,originals);at=instant(capture['issued_at']);horizon=horizon_source(at);before=weather.content
    out=pv_model.project_pv(weather=weather,system_source=source(at),horizon_source=horizon,now=instant(capture['published_at']))
    assert out['status']=='projected_provisional_array_potential',out['reason']
    assert out['horizon_source_sha256']==identity(horizon)
    assert out['terrain_status']=='unvalidated_map_estimate'
    assert out['terrain_rule']=='direct_beam_and_direct_ground_reflection_mask_diffuse_sky_view_unmodeled'
    assert weather.content==before and out['physical_calibration_qualified'] is False


def test_wrong_site_horizon_withholds_the_new_PV_model_instead_of_hiding_mismatch(tmp_path,monkeypatch,originals):
    import household_pv_model as pv_model
    from test_household_solar_horizon import source as horizon_source
    from hashlib import sha256
    from household.codec import loads
    capture,_,_,weather=made(tmp_path,monkeypatch,originals);at=instant(capture['issued_at']);horizon=horizon_source(at)
    body=loads(horizon['raw']);body['site_sha256']='f'*64;horizon['raw']=canonical(body).decode();horizon['sha256']=sha256(horizon['raw'].encode()).hexdigest()
    out=pv_model.project_pv(weather=weather,system_source=source(at),horizon_source=horizon,now=instant(capture['published_at']))
    assert out['status']=='unavailable' and out['reason']=='solar_horizon_site_mismatch'
    assert out['trajectory']==[]
