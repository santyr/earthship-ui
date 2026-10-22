"""Full native populations include hourly long leads and missing old bias inputs."""
from dataclasses import asdict
from datetime import timedelta
import importlib.util
import pytest
from learning_fixtures import T,SITE,native_snapshot,full_snapshot,receipt
from test_probabilistic import POLICY
from weather_learning.contracts import identity
from weather_learning.features import _jsonable


def api():
    assert importlib.util.find_spec('weather_learning.probabilistic_population'), 'Task7 full native population builder missing'
    from weather_learning import probabilistic_population
    return probabilistic_population


def label(hour,value=12.):
    at=T+timedelta(hours=hour);return _jsonable(dict(receipt(at,value),at=at,sourceModel='synthetic',sourceSensorId=1))


def compile(*,hours=(10,11,12,120,288),historical=True,winds=None,legacy=None):
    snapshot=native_snapshot(hours=360) if winds is None else full_snapshot(hours=360);snapshot['historical']=historical
    measurements={}
    for hour in hours:measurements[(T+timedelta(hours=hour)).isoformat()]={'outdoor':label(hour)}
    readiness={(at,'outdoor'):(T+timedelta(days=30)).isoformat() for at in measurements}
    return api().pairs_for_source(snapshot,site=SITE,assessed_at=T+timedelta(days=40),temperatures=measurements,temperature_ready=readiness,winds=winds or {},proxies=[],legacy={} if legacy is None else legacy)


def test_all_native_hourly_long_leads_are_matched_without_old_origin_bias_feature():
    value=compile();rows=value['pairs']
    assert len(rows)==5
    assert sorted(p.forecast.target_end for p in rows)==[(T+timedelta(hours=h)).isoformat() for h in (10,11,12,120,288)]
    assert all(p.forecast.baseline==pytest.approx(10.) for p in rows)
    assert all(p.forecast.p10==pytest.approx(8.) and p.forecast.p90==pytest.approx(12.) for p in rows)
    assert all(p.value==pytest.approx(12.) for p in rows)
    assert value['matched_without_origin_temperature']==5


def test_actual_acquisition_and_counterfactual_ready_time_are_retained_separately():
    old=compile(hours=(10,))['pairs'][0];actual=compile(hours=(10,),historical=False)['pairs'][0]
    assert old.outcome_ready_at==(T+timedelta(hours=10,minutes=2)).isoformat()
    assert old.actual_outcome_available_at==(T+timedelta(days=30)).isoformat()
    assert actual.outcome_ready_at==actual.actual_outcome_available_at
    assert old.forecast.availability_basis!=actual.forecast.availability_basis
    assert old.forecast.cohort_sha256!=actual.forecast.cohort_sha256


def test_every_complete_observed_wind_hour_can_match_at_long_native_leads():
    winds={}
    for h in (11,120,288):winds[(T+timedelta(hours=h)).isoformat()]=dict(mean_m_s=.5,covered_seconds=3600,measurement_health_qualified=False,unit='m_s',source_sha256='c'*64,actual_available_at=(T+timedelta(days=30)).isoformat())
    value=compile(hours=(),winds=winds);rows=value['pairs']
    assert len(rows)==3
    assert all(p.forecast.kind=='wind' and p.forecast.baseline==1. and p.value==.5 for p in rows)
    assert all(p.forecast.p10 is None and p.forecast.p90 is None for p in rows)


def test_existing_parent_rows_are_checked_against_native_and_measured_originals():
    row=asdict(compile(hours=(10,))['pairs'][0]);key=(row['forecast']['forecast_sha256'],'temperature',row['forecast']['target_end'],row['forecast']['cohort_sha256'])
    value=compile(hours=(10,),legacy={key:row})
    assert value['legacy_checked']==1 and value['legacy_exact']==1
    row['value']=13.;row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
    with pytest.raises(ValueError,match='legacy|original|replay'):
        compile(hours=(10,),legacy={key:row})


def test_cohort_files_preserve_all_rows_without_a_larger_global_object(tmp_path):
    rows=compile(hours=(10,11,12))['pairs']
    collection=api().retain_collection(rows,output=tmp_path/'collection',policy=POLICY,metadata={'frozen_seed_population_sha256':'a'*64},maximum_rows=2)
    assert collection['rows']==3 and len(collection['cohorts'])>=2
    from weather_learning.probabilistic_retained import restore_population
    all_rows=[]
    for descriptor in collection['cohorts'].values():
        path=tmp_path/'collection'/descriptor['population_filename']
        current,meta=restore_population(path,policy=POLICY,read=lambda p,n:p.read_bytes())
        assert len(current)<=2
        all_rows.extend(current)
    assert sorted((p.forecast.origin,p.forecast.target_end,p.value) for p in all_rows)==sorted((p.forecast.origin,p.forecast.target_end,p.value) for p in rows)
    again=api().retain_collection(rows,output=tmp_path/'collection',policy=POLICY,metadata={'frozen_seed_population_sha256':'a'*64},maximum_rows=2)
    assert collection==again


def test_mean_source_without_observation_remains_named_missing_support():
    value=compile(hours=())
    assert value['pairs']==[]
    assert sum(value['withheld'].values())>0


def test_frozen_inputs_are_read_and_staged_from_retained_bytes_even_without_live_original(tmp_path):
    from hashlib import sha256
    from weather_learning.contracts import canonical
    raw=b'literal original measurement bytes';pin=sha256(raw).hexdigest();base=tmp_path/'old-base';original=base/'historical-measurements'/'2026-01-01.temperature-grid.json'
    source=tmp_path/'seed';(source/'originals').mkdir(parents=True)
    import gzip
    (source/'originals'/(pin+'.bin.gz')).write_bytes(gzip.compress(raw))
    seed=dict(schema='earthship-marginal-calibration-population/v1',policy_sha256=POLICY['policy_sha256'],rows=[],source_inputs={str(original):dict(sha256=pin,maximum=1024,source=False)})
    seed['population_sha256']=identity(seed);path=source/(seed['population_sha256']+'.population.json.gz');path.write_bytes(gzip.compress(canonical(seed)))
    frozen=api().FrozenInputs(path,read=lambda p,n:p.read_bytes())
    assert frozen.read(original,1024)==raw
    staged=frozen.stage_measurements(base=base,output=tmp_path/'staged')
    assert (staged/'historical-measurements'/original.name).read_bytes()==raw
    assert frozen.read(staged/'historical-measurements'/original.name,1024)==raw
    assert not original.exists()


def test_frozen_input_byte_or_seed_identity_changes_are_rejected(tmp_path):
    import gzip
    from hashlib import sha256
    from weather_learning.contracts import canonical
    raw=b'original';pin=sha256(raw).hexdigest();source=tmp_path/'seed';(source/'originals').mkdir(parents=True);p=source/'originals'/(pin+'.bin.gz');p.write_bytes(gzip.compress(b'changed'))
    seed=dict(schema='earthship-marginal-calibration-population/v1',policy_sha256=POLICY['policy_sha256'],rows=[],source_inputs={'/old/object':dict(sha256=pin,maximum=1024,source=False)})
    seed['population_sha256']=identity(seed);path=source/(seed['population_sha256']+'.population.json.gz');path.write_bytes(gzip.compress(canonical(seed)));frozen=api().FrozenInputs(path,read=lambda p,n:p.read_bytes())
    with pytest.raises(ValueError,match='original|digest'):
        frozen.read('/old/object',1024)
    seed['rows']=[{'changed':True}];path.write_bytes(gzip.compress(canonical(seed)))
    with pytest.raises(ValueError,match='seed|identity'):
        api().FrozenInputs(path,read=lambda p,n:p.read_bytes())


def test_capacity_partition_keeps_adjacent_native_leads_together_without_overfine_hour_cohorts():
    rows=compile(hours=(10,11,12,13,14))['pairs']
    partitioned,descriptors=api().partition_complete_population(rows,maximum_rows=2)
    assert len(partitioned)==5
    assert sorted((d['lower_exclusive_hours'],d['upper_inclusive_hours']) for d in descriptors.values())==[(0.,2.),(2.,4.),(4.,24.)]
    from collections import Counter
    assert sorted(Counter(p.forecast.cohort_sha256 for p in partitioned).values())==[1,2,2]
    assert all(d['method']=='contiguous_whole_native_leads_greedy_capacity/v1' for d in descriptors.values())


def test_capacity_partition_is_unchanged_when_outcomes_change():
    from dataclasses import replace
    rows=compile(hours=(10,11,12,13,14))['pairs']
    a,ad=api().partition_complete_population(rows,maximum_rows=2)
    b,bd=api().partition_complete_population([replace(p,value=30.) for p in rows],maximum_rows=2)
    assert ad==bd
    assert [(p.forecast.origin,p.forecast.target_end,p.forecast.cohort_sha256) for p in a]==[(p.forecast.origin,p.forecast.target_end,p.forecast.cohort_sha256) for p in b]
