"""Training pair baselines must equal served interval power for identical inputs."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from math import fsum

import pytest

from household_pv_model import ASSUMPTIONS, integrate_array
from historical_pv_legacy_assess import pair_older
from test_daily_pv_potential import ARRAY

START=datetime(2026,6,1,18,tzinfo=timezone.utc)


def forcing(origin, *, missing=None, elevation=30., terrain=5.):
    floor=origin.replace(minute=0,second=0,microsecond=0)
    rows=[dict(at=(floor+timedelta(hours=i)).isoformat(),radiationWm2=radiation,
        tempF=temp,windMph=wind) for i,(radiation,temp,wind) in enumerate([
            (100.,40.,1.),(900.,80.,15.),(200.,20.,4.)])]
    if missing is not None:rows[missing]['windMph']=None
    positions=[dict(at=(origin+timedelta(minutes=5*i)).isoformat(),elevation_degrees=elevation,
        azimuth_degrees=110.) for i in range(1,13)]
    horizon=[dict(azimuth_degrees=i*7.5,elevation_degrees=terrain) for i in range(48)]
    hours={r['at']:dict(station_head_temperature_2m=(r['tempF']-32)*5/9,
        wind_speed_10m=None if r['windMph'] is None else r['windMph']/(3600/1609.344),
        surface_solar_radiation_downwards_1hr=r['radiationWm2']) for r in rows}
    return rows,positions,horizon,hours


@pytest.mark.parametrize('offset,missing,elevation,terrain',[
    (0,None,30.,5.),        # :05 endpoint: interpolate a steep temperature/wind gradient
    (55*60,None,30.,5.),    # whole-hour endpoint keeps exact original point weather
    (55*60+15,None,30.,5.), # radiation crosses the UTC hour inside the interval
    (0,0,30.,5.),          # missing earlier wind uses the same declared assumption
    (0,1,30.,5.),
    (0,None,-1.,5.),       # night/dusk stays zero
    (0,None,2.,0.),        # dawn diffuse response
    (0,None,30.,40.),      # terrain masks direct beam without arbitrary power clipping
])
def test_legacy_pair_and_served_interval_use_identical_baseline(offset,missing,elevation,terrain):
    origin=START+timedelta(seconds=offset)
    rows,positions,horizon,hours=forcing(origin,missing=missing,elevation=elevation,terrain=terrain)
    before=deepcopy((rows,positions,hours))
    served=integrate_array(array=ARRAY,assumptions=ASSUMPTIONS,hourly_forecast=rows,
        positions=positions,origin=origin,horizon_hours=1,timezone_name='America/Denver',horizon_profile=horizon)
    end=origin+timedelta(minutes=5)
    energy=fsum(r['potential_pv_kwh'] for r in served['steps'] if datetime.fromisoformat(r['end'])<=end)
    expected=energy*12000  # five-minute energy -> mean watts
    label=dict(start=origin.isoformat(),end=end.isoformat(),outcome_w=800.,source_sha256='c'*64,
        censoring_basis='numeric_proxy',positive_charge_basis='recent_soc_rise')
    pairs,missing_count=pair_older([label],runs=[(origin-timedelta(hours=2),'a'*64,hours,'historical_assumption')],
        positions={p['at']:p for p in positions},array=ARRAY,horizon=horizon)
    assert missing_count==0 and len(pairs)==1
    assert pairs[0]['baseline_w']==pytest.approx(expected,rel=1e-12,abs=1e-9)
    assert (rows,positions,hours)==before


def test_pairing_requires_both_original_point_weather_endpoints():
    rows,positions,horizon,hours=forcing(START)
    del hours[rows[0]['at']]
    label=dict(start=START.isoformat(),end=positions[0]['at'],outcome_w=800.,source_sha256='c'*64,
        censoring_basis='numeric_proxy',positive_charge_basis='recent_soc_rise')
    pairs,missing=pair_older([label],runs=[(START-timedelta(hours=2),'a'*64,hours,'historical_assumption')],
        positions={p['at']:p for p in positions},array=ARRAY,horizon=horizon)
    assert pairs==[] and missing==1


def test_pair_temperature_and_wind_are_interpolated_points_not_ending_hour_means():
    from household_pv_model import array_power
    from historical_pv_train import pair_baseline
    rows,positions,horizon,hours=forcing(START)
    # At :05, 40 -> 80 F is 43 1/3 F; 1 -> 15 mph is 2 1/6 mph.
    expected=array_power(array=ARRAY,assumptions=ASSUMPTIONS,ghi_wm2=900.,
        elevation_degrees=30.,azimuth_degrees=110.,day_of_year=152,
        temp_f=43.333333333333336,wind_mph=2.1666666666666665,
        horizon_elevation_degrees=5.)['potential_dc_w']
    actual=pair_baseline(start=START,end=START+timedelta(minutes=5),hours=hours,
        position=positions[0],array=ARRAY,horizon=horizon)
    assert actual==pytest.approx(expected,rel=1e-12)


def test_new_assessment_cannot_reuse_old_pair_arithmetic_even_with_valid_original_hash(tmp_path):
    import gzip
    from weather_learning.contracts import canonical, identity
    from historical_pv_legacy_assess import _dataset
    old=dict(schema='earthship-historical-pv-calibration-data/v1',pairs=[])
    old['dataset_sha256']=identity(old)
    path=tmp_path/'original.pairs.json.gz';path.write_bytes(gzip.compress(canonical(old)));path.chmod(0o600)
    original=path.read_bytes()
    with pytest.raises(ValueError,match='baseline'):_dataset(path,old['dataset_sha256'])
    assert path.read_bytes()==original


def test_pair_unit_conversion_matches_provider_exact_metre_per_second_contract():
    from household_pv_model import array_power
    from historical_pv_train import pair_baseline
    hours={at.isoformat():dict(station_head_temperature_2m=20.,wind_speed_10m=1.,
        surface_solar_radiation_downwards_1hr=900.) for at in (START,START+timedelta(hours=1))}
    expected=array_power(array=ARRAY,assumptions=ASSUMPTIONS,ghi_wm2=900.,
        elevation_degrees=30.,azimuth_degrees=110.,day_of_year=152,temp_f=68.,
        wind_mph=3600/1609.344,horizon_elevation_degrees=None)['potential_dc_w']
    actual=pair_baseline(start=START,end=START+timedelta(minutes=5),hours=hours,
        position=dict(elevation_degrees=30.,azimuth_degrees=110.),array=ARRAY,horizon=None)
    assert actual==pytest.approx(expected,rel=1e-14,abs=1e-12)
