"""Marginal inputs must replay literal native quantities and measured targets."""
from copy import deepcopy
from datetime import timedelta
import importlib.util
import pytest
from learning_fixtures import T,SITE,native_snapshot,full_snapshot


def api():
    assert importlib.util.find_spec('weather_learning.probabilistic_retained'), 'Task7 original marginal adapter missing'
    from weather_learning import probabilistic_retained
    return probabilistic_retained


def prepared(snapshot=None):
    original=native_snapshot(hours=80) if snapshot is None else snapshot
    original['historical']=True
    return api().prepare_marginal_source(original,assessed_at=T+timedelta(days=30))


def test_temperature_native_statistics_and_source_clocks_survive_all_lead_scopes():
    source=prepared();f=source.forecast('temperature',target=T+timedelta(hours=50),quality={'sensor_phase':'one'})
    assert f.baseline==pytest.approx(10.)
    assert f.p10==pytest.approx(8.) and f.p90==pytest.approx(12.)
    assert f.p50 is None
    assert f.origin==(T+timedelta(hours=9)).isoformat()
    assert f.target_start==f.target_end
    assert f.source_ready_at==f.origin
    assert f.actual_source_available_at==(T+timedelta(minutes=21)).isoformat()
    assert f.availability_basis=='historical_assumed_availability'


def test_original_normalized_value_cannot_be_changed_even_with_a_new_top_digest():
    source=native_snapshot(hours=80);source['points'][0]['value']+=1
    with pytest.raises(ValueError,match='native|original'):
        prepared(source)


def test_hourly_scalar_wind_averages_original_boundary_means_without_hourly_quantile_invention():
    source=prepared(full_snapshot());f=source.forecast('wind',target=T+timedelta(hours=11),quality={'quality':'numeric_state'})
    assert f.baseline==1.
    assert f.target_start==(T+timedelta(hours=10)).isoformat()
    assert f.p10 is None and f.p50 is None and f.p90 is None


def test_solar_hour_uses_native_normalized_energy_rate_once_not_twice_divided():
    source=prepared(full_snapshot());f=source.forecast('solar_proxy',target=T+timedelta(hours=11),quality={'quality':'proxy_only'})
    assert f.baseline==100.
    assert f.target_end==(T+timedelta(hours=11)).isoformat()
    assert f.p10 is None and f.p90 is None


def test_recorded_actual_availability_and_unknown_fields_do_not_enter_historical_cohort():
    original=native_snapshot(hours=80);s=api().prepare_marginal_source(original,assessed_at=T+timedelta(days=30))
    f=s.forecast('temperature',target=T+timedelta(hours=3),quality={'sensor_phase':'one'})
    assert f.availability_basis=='recorded_ingestion_availability'
    assert f.source_ready_at==(T+timedelta(minutes=21)).isoformat()
    assert f.origin==(T+timedelta(hours=1)).isoformat()
    assert f.cohort_sha256!=prepared().forecast('temperature',target=T+timedelta(hours=11),quality={'sensor_phase':'one'}).cohort_sha256
    with pytest.raises(ValueError,match='available'):
        api().prepare_marginal_source(original,assessed_at=T)


def test_measured_sensor_policy_and_grid_are_not_pooled_in_one_source_cohort():
    source=prepared();target=T+timedelta(hours=11)
    a=source.forecast('temperature',target=target,quality={'sensor_phase':'one'})
    b=source.forecast('temperature',target=target,quality={'sensor_phase':'two'})
    assert a.cohort_sha256!=b.cohort_sha256
    with pytest.raises(AttributeError):source.initialized_at=T


def test_proxy_originals_replay_and_repeat_readiness_is_first_actual_capture_not_last_sensor_packet():
    from test_solar_shadow import source as observations
    from weather_learning.solar_shadow import capture_solar_window
    data=observations();value=capture_solar_window(**data)
    labels=api().proxy_labels([value])
    assert len(labels)==2
    first=labels[0]
    assert first['value']==pytest.approx(100.,abs=1e-9)
    assert first['actual_available_at']==value['assessed_at']
    assert first['actual_available_at']!=value['available_at']
    later=deepcopy(value);later['assessed_at']=(data['assessed_at']+timedelta(hours=1)).isoformat()
    again=api().proxy_labels([later,value])
    assert again==labels
    corrupted=deepcopy(value);corrupted['hourly'][0]['proxy_wh_m2']+=1
    with pytest.raises(ValueError,match='original|receipt'):
        api().proxy_labels([corrupted])


def test_temperature_pair_is_rederived_from_original_parent_not_its_rehashed_claim():
    from weather_learning.historical_pairs import pair_temperatures
    from weather_learning.contracts import identity
    from test_weather_historical_pairs import observations
    snapshot=full_snapshot();snapshot['historical']=True;source=prepared(snapshot);labels=observations()
    parent=next(r for r in pair_temperatures(snapshot,labels) if r['kind']=='outdoor_temperature_c')
    availability={(at,'outdoor'):(T+timedelta(days=30)).isoformat() for at in labels}
    pair=api().temperature_pair(parent,snapshot=snapshot,source=source,measurements=labels,availability=availability)
    assert pair.value==parent['outcome']
    assert pair.forecast.baseline==10.
    assert pair.actual_outcome_available_at==(T+timedelta(days=30)).isoformat()
    assert pair.outcome_ready_at==(T+timedelta(hours=10,minutes=2)).isoformat()
    bad=dict(parent,outcome=parent['outcome']+1);bad['pair_sha256']=identity({k:v for k,v in bad.items() if k!='pair_sha256'})
    with pytest.raises(ValueError,match='replay|original'):
        api().temperature_pair(bad,snapshot=snapshot,source=source,measurements=labels,availability=availability)


def test_wind_pair_replays_native_window_and_literal_measured_hour():
    from weather_learning.contracts import identity
    source=prepared(full_snapshot());start=T+timedelta(hours=10);end=start+timedelta(hours=1)
    label={'mean_m_s':.5,'source_sha256':'c'*64,'actual_available_at':(T+timedelta(days=30)).isoformat()}
    parent=dict(kind='wind_m_s',origin=source.origin,target_start=start.isoformat(),target_end=end.isoformat(),baseline=1.,outcome=.5,source_sha256=source.snapshot_sha256,measurement_sha256='c'*64,measurement_quality='persisted_numeric_state',prospective_score=False,automatic_actuation=False,availability_basis='retrospective_assumed_full_cycle_9h')
    parent['pair_sha256']=identity(parent)
    pair=api().wind_pair(parent,source=source,label=label)
    assert pair.value==.5 and pair.forecast.baseline==1.
    with pytest.raises(ValueError,match='original|replay'):
        api().wind_pair(parent,source=source,label=dict(label,mean_m_s=2.))


def test_oversized_coherent_population_partitions_by_native_lead_without_dropping_rows():
    from dataclasses import replace
    from test_probabilistic import pairs
    values=pairs(days=3);expanded=[]
    for i,p in enumerate(values):
        extra=timedelta(hours=i%2)
        f=replace(p.forecast,target_start=(T+timedelta(days=i//4,hours=10+(i%4)*4)+extra).isoformat(),target_end=(T+timedelta(days=i//4,hours=10+(i%4)*4)+extra).isoformat())
        expanded.append(replace(p,forecast=f,outcome_ready_at=(T+timedelta(days=i//4,hours=10+(i%4)*4,minutes=2)+extra).isoformat(),actual_outcome_available_at=(T+timedelta(days=i//4,hours=10+(i%4)*4,minutes=2)+extra).isoformat()))
    partitioned,descriptors=api().partition_population(expanded,maximum_rows=8)
    assert len(partitioned)==12
    assert len({p.forecast.cohort_sha256 for p in partitioned})==2
    assert sorted(d['exact_lead_hours'] for d in descriptors.values())==[1.,2.]
    assert sorted((p.forecast.origin,p.forecast.target_end,p.value) for p in partitioned)==sorted((p.forecast.origin,p.forecast.target_end,p.value) for p in expanded)
    with pytest.raises(ValueError,match='coherent.*bound'):
        api().partition_population(values,maximum_rows=8)


def test_serialized_population_reconstructs_original_pairs_and_refuses_changed_inputs(tmp_path):
    from dataclasses import asdict
    import gzip,json
    from weather_learning.contracts import canonical,identity
    from test_probabilistic import POLICY,pairs
    original=pairs(days=2)
    body=dict(schema='earthship-marginal-calibration-population/v1',policy_sha256=POLICY['policy_sha256'],rows=[asdict(p) for p in original]);body['population_sha256']=identity(body)
    path=tmp_path/(body['population_sha256']+'.population.json.gz');path.write_bytes(gzip.compress(canonical(body)))
    loaded,metadata=api().restore_population(path,policy=POLICY,read=lambda p,n:p.read_bytes())
    assert loaded==original
    body['rows'][0]['forecast']['baseline']=20
    body['population_sha256']=identity({k:v for k,v in body.items() if k!='population_sha256'})
    changed=tmp_path/(body['population_sha256']+'.population.json.gz');changed.write_bytes(gzip.compress(canonical(body)))
    with pytest.raises(ValueError,match='original|identity'):
        api().restore_population(changed,policy=POLICY,read=lambda p,n:p.read_bytes())


def test_experiment_original_copy_is_lossless_compressed_and_never_replaces_different_bytes(tmp_path):
    import gzip
    from hashlib import sha256
    from marginal_calibration_experiment import retain_original
    raw=b'literal native retained bytes\n'*10000
    pin=sha256(raw).hexdigest();size=retain_original(tmp_path,pin,raw)
    path=tmp_path/'originals'/(pin+'.bin.gz')
    assert gzip.decompress(path.read_bytes())==raw
    assert size==path.stat().st_size and size<len(raw)
    assert retain_original(tmp_path,pin,raw)==size
    with pytest.raises(ValueError,match='original|digest'):
        retain_original(tmp_path,pin,raw+b'changed')
