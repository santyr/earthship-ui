"""Original thermal state and coefficients survive a weather-only comparison."""
from copy import deepcopy
from datetime import timedelta
import importlib
import pytest
from household.codec import canonical
from household.model_snapshot import restore_snapshot
from household.thermal_model import project
from test_weathernext_fixed_energy import setup,google,originals


def compare(*args,**kwargs):
    return importlib.import_module('weather_learning.thermal_shadow').compare_fixed_thermal(*args,**kwargs)


def test_weather_changes_without_refitting_initial_state_actions_or_native_geometry(tmp_path,monkeypatch,originals):
    _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
    prepared=restore_snapshot(plan['inputs']['snapshot'],plan['inputs']['source_contexts']).weather.prepared
    original=prepared.to_dict();source=google(origin);before=canonical(dict(plan=plan,energy=energy,source=source))
    result=compare(energy,plan_receipt=plan,google_snapshot=source,assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
    assert result['status']=='COMPARED',result
    assert result['control']['output']==project(prepared)['output']
    assert result['fixed_inputs']=={name:original[name] for name in ('coefficients','initial','actions','horizon_hours')}
    assert result['geometry_series_sha256']==original['geometry_series_sha256']
    assert result['google']['trajectory']!=result['control']['output']['trajectory']
    assert result['google']['trajectory'][0]['at']==result['control']['output']['trajectory'][0]['at']
    assert len(result['google']['trajectory'])==24
    assert result['google']['first_forcing']['outdoor_f']==pytest.approx(44.33)
    assert result['google']['first_forcing']['radiation_wm2']==1000
    for name in ('indoor_shade_closed','outdoor_shade_present','vent_open'):
        assert result['google']['first_forcing'][name]==original['forcings'][0][name]
    assert canonical(dict(plan=plan,energy=energy,source=source))==before
    assert result['outcomes']['score_status']=='NOT_SCORED'
    assert result['outcomes']['measured_hourly_air_f'] is None
    assert result['qualification']=='SHADOW_ONLY' and result['automatic_actuation'] is False
    assert result['weather_weights_imported'] is False and result['model_fitting'] is False


@pytest.mark.parametrize('damage',['future','historical','missing','site','tampered'])
def test_ineligible_google_is_unavailable_without_changing_or_substituting_control(tmp_path,monkeypatch,originals,damage):
    _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals);source=google(origin,missing=damage=='missing')
    if damage=='future':source['ingestion_completed_at']=(origin+timedelta(seconds=1)).isoformat()
    if damage=='historical':source['historical']=True
    if damage=='site':source['site']['latitude']=38.39
    if damage=='tampered':source['points'][0]['value']+=5
    result=compare(energy,plan_receipt=plan,google_snapshot=source,assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
    assert result['status']=='UNAVAILABLE' and result['google'] is None
    assert result['control']['output']['trajectory']


def test_comparison_uses_actual_completion_for_whole_hour_prospective_flags(tmp_path,monkeypatch,originals):
    _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
    completed=origin+timedelta(hours=1,minutes=5)
    result=compare(energy,plan_receipt=plan,google_snapshot=google(origin),assessed_at=args['now']+timedelta(seconds=1),clock=lambda:completed)
    assert result['completed_at']==completed.isoformat()
    assert result['prospective_ending_hours']['1'] is False
    assert result['prospective_ending_hours']['2'] is False
    assert result['prospective_ending_hours']['3'] is True


def test_original_runtime_drift_is_refused_before_comparison(tmp_path,monkeypatch,originals):
    api,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
    runtime=deepcopy(api.forecast_runtime_manifest());runtime['openhab/scripts/native_thermal_model.py']='f'*64
    monkeypatch.setattr(api,'forecast_runtime_manifest',lambda:runtime)
    with pytest.raises(ValueError):compare(energy,plan_receipt=plan,google_snapshot=google(origin),assessed_at=args['now']+timedelta(seconds=1))


def test_mid_comparison_runtime_drift_is_refused_before_return(tmp_path,monkeypatch,originals):
    api,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
    before=api.forecast_runtime_manifest();after=deepcopy(before);after['openhab/scripts/native_thermal_model.py']='f'*64
    calls=[]
    def runtime():
        calls.append(True)
        return before if len(calls)==1 else after
    monkeypatch.setattr(api,'forecast_runtime_manifest',runtime)
    with pytest.raises(ValueError):compare(energy,plan_receipt=plan,google_snapshot=google(origin),assessed_at=args['now']+timedelta(seconds=1))


def test_incompatible_installed_model_profile_is_not_silently_replaced_by_older_family(tmp_path,monkeypatch,originals):
    _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
    import native_thermal_artifact
    from native_thermal_model import NativeInstalledShadeDynamics
    # The executing runtime owns model-family dispatch. A profile/rule mismatch
    # must refuse, even if an older class would accept these coefficient values.
    monkeypatch.setattr(native_thermal_artifact,'fit_profile',lambda fit:dict(rule='incompatible_model_rule',model=NativeInstalledShadeDynamics),raising=False)
    result=compare(energy,plan_receipt=plan,google_snapshot=google(origin),assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
    assert result['status']=='UNAVAILABLE' and result['google'] is None


def test_native_hourly_ramp_preserves_existing_five_minute_interpolation(tmp_path,monkeypatch,originals):
    _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals)
    from weather_learning.config import Site
    from weather_learning.contracts import instant
    from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
    source=google(origin);parts=[];boundary=origin.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    for original in source['source_originals']:
        raw=deepcopy(original['payload']);bands=raw['region'][0][4:]
        for metadata,row in zip(raw['metadata'],raw['region'][1:]):
            late=instant(metadata['end_time'])>=boundary
            row[4]=(285.15 if late else 273.15) if bands[0].startswith('station_') else (1200*3600 if late else 0)
        parts.append(parse_collection_response(raw,collection=original['collection'],bands=bands,site=Site(**source['site']),initialized_at=instant(source['initialized_at']),horizon=48))
    source=make_snapshot(parts,site=Site(**source['site']),initialized_at=instant(source['initialized_at']),first_seen_at=origin-timedelta(hours=1),completed_at=origin-timedelta(minutes=30))
    result=compare(energy,plan_receipt=plan,google_snapshot=source,assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
    first=result['google']['first_forcing'];at=instant(first['at'])
    fraction=(at-(boundary-timedelta(hours=1))).total_seconds()/3600
    assert first['outdoor_f']==pytest.approx(32+21.6*fraction)
    assert first['radiation_wm2']==pytest.approx(1200*fraction)


def test_original_replay_never_contacts_provider_or_database(tmp_path,monkeypatch,originals):
    _,args,plan,energy,origin=setup(tmp_path,monkeypatch,originals);source=google(origin)
    import socket,urllib.request,psycopg2
    def forbidden(*args,**kwargs):pytest.fail('Live data access during retained comparison')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(urllib.request,'urlopen',forbidden)
    monkeypatch.setattr(psycopg2,'connect',forbidden)
    result=compare(energy,plan_receipt=plan,google_snapshot=source,assessed_at=args['now']+timedelta(seconds=1),clock=lambda:args['now']+timedelta(seconds=1))
    assert result['status']=='COMPARED'
