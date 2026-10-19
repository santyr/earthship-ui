from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import importlib
import pytest

ARRAY=dict(module_count=12,module_nameplate_w=350,dc_nameplate_w=4200,surface_azimuth_degrees=165.,surface_tilt_degrees=57.4)

def inputs(day='2026-10-20',origin=None):
    zone=ZoneInfo('America/Denver');start=datetime.fromisoformat(day).replace(tzinfo=zone).astimezone(timezone.utc)
    end=(datetime.fromisoformat(day)+timedelta(days=1)).replace(tzinfo=zone).astimezone(timezone.utc)
    hours=[];positions=[];at=start
    while at<end:
        at+=timedelta(hours=1)
        hours.append(dict(at=at.isoformat(),tempF=59.,radiationWm2=500.,windMph=2.))
    at=start
    while at<end:
        at+=timedelta(minutes=5);positions.append(dict(at=at.isoformat(),elevation_degrees=45.,azimuth_degrees=165.))
    return dict(dates=[day],hours=hours,positions=positions,array=ARRAY,horizon_profile=None,timezone_name=zone.key,
        issued_at=origin or start)

def project(**kw):return importlib.import_module('daily_pv_potential').project_days(**kw)

def test_daily_potential_reuses_array_physics_and_has_no_storage_dependence():
    args=inputs();result=project(**args)
    from household_pv_model import array_power,ASSUMPTIONS
    w=array_power(array=ARRAY,assumptions=ASSUMPTIONS,ghi_wm2=500,elevation_degrees=45,azimuth_degrees=165,day_of_year=293,temp_f=59,wind_mph=2)['potential_dc_w']
    midnight_w=array_power(array=ARRAY,assumptions=ASSUMPTIONS,ghi_wm2=500,elevation_degrees=45,azimuth_degrees=165,day_of_year=294,temp_f=59,wind_mph=2)['potential_dc_w']
    assert result[0]['potentialKwh']==pytest.approx((w*287+midnight_w)/12/1000)
    assert result[0]['scope']=='full_day'
    assert result[0]['status']=='available'

@pytest.mark.parametrize('day,elapsed',[('2026-03-08',23),('2026-11-01',25)])
def test_daily_energy_follows_denver_midnights_across_dst(day,elapsed):
    result=project(**inputs(day))[0]
    assert (datetime.fromisoformat(result['throughAt'])-datetime.fromisoformat(result['fromAt'])).total_seconds()==elapsed*3600
    assert result['potentialKwh']>0

def test_today_integrates_only_future_partial_intervals():
    args=inputs();start=args['issued_at'];args['issued_at']+=timedelta(hours=8,minutes=32,seconds=15)
    value=project(**args)[0];full=project(**inputs())[0]
    assert value['scope']=='remaining'
    assert value['fromAt']==args['issued_at'].isoformat()
    assert value['potentialKwh']==pytest.approx(full['potentialKwh']*(24-8-32/60-15/3600)/24)

@pytest.mark.parametrize('damage',['weather_gap','null_radiation','geometry_gap','nan_geometry'])
def test_missing_coverage_never_becomes_zero_or_a_partial_full_day(damage):
    args=inputs()
    if damage=='weather_gap':args['hours'].pop(12)
    if damage=='null_radiation':args['hours'][12]['radiationWm2']=None
    if damage=='geometry_gap':args['positions'].pop(120)
    if damage=='nan_geometry':args['positions'][120]['elevation_degrees']=float('nan')
    value=project(**args)[0]
    assert value['status']=='unavailable';assert value['potentialKwh'] is None


def test_night_is_zero_and_terrain_masks_direct_beam():
    args=inputs()
    for row in args['positions']:row['elevation_degrees']=-2
    assert project(**args)[0]['potentialKwh']==0
    args=inputs();clear=project(**args)[0]['potentialKwh']
    args['horizon_profile']=[dict(azimuth_degrees=i*7.5,elevation_degrees=50.) for i in range(48)]
    assert 0<project(**args)[0]['potentialKwh']<clear


def test_day_geometry_cache_reuses_original_availability_and_rejects_tampering(tmp_path):
    from daily_pv_worker import day_geometry
    from astro_geometry import build_cache
    from weather_learning.config import Site
    import json
    tmp_path.chmod(0o700)
    runtime=dict(binding_version='5.2.3',libraries=dict(astro_binding='a'*64,openhab_core='b'*64),collector_sha256='c'*64)
    now=datetime(2026,10,19,22,tzinfo=timezone.utc);calls=[]
    def capture(request,source,**kw):
        calls.append(request)
        return build_cache(request,source,native_output=''.join(at+'\t45.0\t165.0\n' for at in request['instants']).encode(),computed_at=now)
    args=dict(site=Site(38.3739919,-105.7744609,'America/Denver'),native_runtime=runtime,libraries={},guard=lambda:None,capture=capture)
    first=day_geometry(tmp_path,'2026-10-20',clock=lambda:now,**args)
    second=day_geometry(tmp_path,'2026-10-20',clock=lambda:now+timedelta(hours=1),**args)
    assert len(calls)==3
    assert first.to_dict()==second.to_dict()
    path=next(tmp_path.glob('*.geometry.json'));value=json.loads(path.read_text());value['caches'][0]['positions'][0]['elevation_degrees']=0.
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):day_geometry(tmp_path,'2026-10-20',clock=lambda:now,**args)
