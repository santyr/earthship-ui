"""Profile identity and optional data never relax the established core contract."""
from dataclasses import FrozenInstanceError,replace
from datetime import timedelta
import importlib
import pytest
from learning_fixtures import T,SITE,full_snapshot,native_snapshot
from weather_learning.config import AccessPolicy,COLLECTIONS
from weather_learning.worker import DEFAULT_BANDS
from weather_learning.normalize import normalize_point

def api():return importlib.import_module('weather_learning.capabilities')

def test_core_profile_preserves_existing_band_meaning_and_budget():
    core=api().profile('core-v1')
    assert core.bands_by_grid==DEFAULT_BANDS
    assert sum(map(len,core.bands_by_grid.values()))==12
    assert core.optional is False
    assert api().enabled_profiles()==(core,)
    assert core.max_bytes==AccessPolicy().max_bytes
    assert core.max_seconds==75 and core.max_requests==32

def test_profile_hash_changes_with_coverage_and_requested_statistics():
    p=api().profile('temperature-display-v1')
    assert replace(p,horizons=(48,)).signature!=p.signature
    assert api().profile('uncertainty-v1').signature!=p.signature
    assert len({p.signature for p in api().PROFILES.values()})==len(api().PROFILES)
    with pytest.raises(FrozenInstanceError):p.optional=False
    with pytest.raises(TypeError):api().PROFILES['unreviewed']=p

@pytest.mark.parametrize('change',[
    {'max_bytes':8*1024**2+1},{'max_seconds':76},{'max_requests':33},
    {'max_pixels':17},{'attempts':3},{'horizons':(361,)},
    {'bands':(('station','station_head_temperature_2m_members'),)},
    {'bands':(('station','wind_speed_10m_mean'),)},
    {'bands':(('gridded','renamed_cloud_layer_mean'),)},
])
def test_profile_refuses_unreviewed_access_or_resource_expansion(change):
    with pytest.raises(ValueError):replace(api().profile('core-v1'),**change)

@pytest.mark.parametrize('change',[{'paid_access_allowed':True},{'full_ensemble_allowed':True},{'requester_billing_project':'unapproved'}])
def test_capability_profiles_do_not_relax_access_policy(change):
    with pytest.raises(ValueError):AccessPolicy(**change)

@pytest.mark.parametrize('variable',['high_cloud_cover','medium_cloud_cover','low_cloud_cover'])
def test_each_cloud_layer_has_native_fraction_units_and_independent_bounds(variable):
    kw=dict(valid_at=(T+timedelta(hours=1)).isoformat(),source_ref=COLLECTIONS['gridded']+'/fixture',source_digest='a'*64,latitude=38.35,longitude=-105.75)
    assert normalize_point(variable,.25,'(0 - 1)',**kw)['value']==25
    for value,unit in [(1.01,'(0 - 1)'),(-.01,'(0 - 1)'),(.5,'percent')]:
        with pytest.raises(ValueError):normalize_point(variable,value,unit,**kw)

def test_native_series_keeps_original_units_interval_and_actual_availability():
    snapshot=native_snapshot(hours=4)
    series=api().native_series(snapshot,'station_head_temperature_2m','p10',decision=T+timedelta(hours=1))
    assert series.raw_unit=='K' and series.unit=='degC'
    assert series.period_seconds==0 and series.grid=='station'
    assert series.available_at==snapshot['ingestion_completed_at']
    assert series.initialized_at==T.isoformat()
    assert series.valid_at[0]==(T+timedelta(hours=1)).isoformat()
    assert series.values[0]==pytest.approx(series.raw_values[0]-273.15)
    with pytest.raises(ValueError):replace(series,run_id='ee:'+ (T+timedelta(hours=6)).isoformat())
    with pytest.raises(ValueError):replace(series,cell=(float('nan'),0))
    with pytest.raises(ValueError):replace(series,raw_unit='degC')

def test_profile_cache_cannot_relabel_old_subset_or_late_original():
    snapshot=native_snapshot(hours=48)
    before=__import__('copy').deepcopy(snapshot)
    decision=T+timedelta(hours=2)
    assert api().profile_coverage(snapshot,api().profile('temperature-display-v1'),decision=decision,horizon=48)['status']=='complete'
    assert api().profile_coverage(full_snapshot(T,hours=48),api().profile('temperature-display-v1'),decision=decision,horizon=48)['status']=='missing_fields'
    missing=api().profile_coverage(snapshot,api().profile('uncertainty-v1'),decision=decision,horizon=48)
    assert missing['status']=='missing_fields'
    assert 'station_head_temperature_2m_p50' in missing['missing_bands']
    assert api().profile_coverage(snapshot,api().profile('temperature-display-v1'),decision=T,horizon=48)['status']=='unavailable_at_decision'
    assert snapshot==before

def test_quantiles_keep_ties_and_mean_median_distinction_without_sorting():
    q=api().validate_quantiles({'mean':20.,'p10':0.,'p50':0.,'p90':0.})
    assert q=={'mean':20.,'p10':0.,'p50':0.,'p90':0.}
    for values in [{'p10':2.,'p90':1.},{'p10':0.,'p90':float('inf')}]:
        with pytest.raises(ValueError):api().validate_quantiles(values)
    assert api().validate_quantiles({'mean':5.,'p10':None})=={'mean':5.,'p10':None}

def test_evidence_refuses_source_clock_or_permission_substitution():
    cls=api().ForecastEvidence
    e=cls(profile_sha256='a'*64,snapshot_sha256='b'*64,method='raw-native-statistics/v1',
        target='station_temperature_degC',issued_at=(T+timedelta(hours=1)).isoformat(),
        available_at=(T+timedelta(minutes=20)).isoformat(),issued_values_sha256='c'*64)
    assert e.local_skill=='not_evaluated' and e.probability_calibration=='unqualified'
    assert e.automatic_actuation is False
    with pytest.raises(ValueError):replace(e,automatic_actuation=True)
    with pytest.raises(ValueError):replace(e,available_at=(T+timedelta(hours=2)).isoformat())

def test_stress_scenario_cannot_invent_probability_qualification_or_unbounded_members():
    cls=api().ScenarioSet
    s=cls(profile_sha256='a'*64,source_sha256='b'*64,method='deterministic-stress/v1',seed=20261021,
        issued_at=T.isoformat(),variables=('temperature_c','solar_w_m2'),
        interval_ends=((T+timedelta(hours=1)).isoformat(),),trajectories=(((10.,0.),),),
        dependence='hypothetical_fixed_trajectory',scope='weather_only_stress')
    assert s.probability_claim is False
    with pytest.raises(ValueError):replace(s,probability_claim=True)
    with pytest.raises(ValueError):replace(s,trajectories=s.trajectories*17)
    with pytest.raises(ValueError):replace(s,trajectories=(((10.,float('nan')),),))
