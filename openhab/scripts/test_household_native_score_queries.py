"""Sparse paired acquisition preserves originals and bounded transaction semantics."""
from datetime import timedelta
import pytest
from test_installed_shade_score_inputs import settings
from test_native_paired_score_reader import (
    reader,test_paired_native_endpoint_query_uses_one_closed_readonly_connection,
    test_full_missing_history_and_outcome_fit_paced_native_request_budget,
    test_native_pair_replays_original_receipts_and_missing_barriers,
    test_native_pair_refuses_wrong_original_request_before_connection,
    test_native_reader_refuses_legacy_profile_and_changed_private_configuration,
    test_native_pair_preserves_null_snapshot_barrier,
    test_native_pair_bounds_aggregate_bytes_before_retention)
from test_weather_temperature_reader import AT
from test_thermal_sensor_epoch_history import EPOCHS


@pytest.fixture(autouse=True)
def bounded_reader(monkeypatch):
    import native_thermal_live as native
    try:
        from household_native_score_queries import EndpointWindowScoreReader
    except ModuleNotFoundError as error:
        if error.name != "household_native_score_queries": raise
        EndpointWindowScoreReader = native.NativeScoreReader
    monkeypatch.setattr(native,'NativeScoreReader',EndpointWindowScoreReader)


def test_sparse_pair_reads_only_endpoint_validity_windows(settings,monkeypatch):
    r,calls=reader(settings,monkeypatch)
    targets=[AT,AT+timedelta(hours=24)]
    result=r.native(targets,assessed_at=targets[-1]+timedelta(minutes=5),sensor_epoch=EPOCHS['air'])
    assert result==[(at,None) for at in targets]
    assert len(calls)==1 and calls[0].closed
    windows=[params for query,params in calls[0].calls if 'WHERE time >=' in query]
    assert windows==[(at-timedelta(seconds=120),at) for at in targets]
    assert len(r.native_source_paths)==1


def test_serving_coordinator_selects_bounded_reader(settings,monkeypatch,tmp_path):
    import household_forecast_score as coordinator
    import native_thermal_live as native
    from household_native_score_queries import EndpointWindowScoreReader
    from datetime import datetime,timezone
    tmp_path.chmod(0o700)
    evidence=tmp_path/'evidence';evidence.mkdir(mode=0o700)
    config={key:settings[1][key] for key in ('token_file','native_db_config','native_policy','openhab_base')}
    config.update(schema=native.SERVING_SCHEMA,evidence_directory=str(evidence))
    model=object();observed=[]
    def score(selected,**kwargs):
        assert selected==config and kwargs['serving_model'] is model
        assert isinstance(kwargs.get('reader'),EndpointWindowScoreReader)
        observed.append(kwargs['reader'])
        return {'status':'original-score-result'}
    monkeypatch.setattr(native,'score_jobs',score)
    assert coordinator.score_with_report(config,guard=lambda:None,serving_model=model,clock=lambda:datetime.now(timezone.utc))=={'status':'original-score-result'}
    assert len(observed)==1


@pytest.mark.parametrize('seconds',[90,360,86400])
@pytest.mark.parametrize('barrier',[False,True])
def test_endpoint_windows_match_full_original_selector(settings,monkeypatch,tmp_path,seconds,barrier):
    import json
    from household_native_score_queries import EndpointWindowScoreReader
    from test_installed_shade_score_inputs import WindowConnection
    from thermal_model.installed_shade_score_inputs import COMPRESSED_SOURCE_SCHEMA
    from test_thermal_sensor_epoch_history import sources
    _,originals=sources(tmp_path,monkeypatch)
    template=json.loads(originals[0][1])
    def row(at):
        from copy import deepcopy
        value=deepcopy(template)
        for record in value['records'].values():
            record.update(recordedAt=at.isoformat(),receivedAt=at.isoformat(),validUntil=(at+timedelta(seconds=120)).isoformat())
        return at,json.dumps(value)
    targets=[AT+timedelta(seconds=60),AT+timedelta(seconds=60+seconds)]
    rows=[row(AT),row(targets[0]+timedelta(seconds=10)),row(targets[1]-timedelta(seconds=60))]
    if barrier:rows.append((targets[1]-timedelta(seconds=30),None))
    rows.sort(key=lambda entry:entry[0])
    config={**settings[1],'schema':COMPRESSED_SOURCE_SCHEMA}
    original=EndpointWindowScoreReader.__bases__[0](config,shared_lock_guard=lambda:None)
    bounded=EndpointWindowScoreReader(config,shared_lock_guard=lambda:None)
    import hourly_temperature_runtime
    monkeypatch.setattr(hourly_temperature_runtime,'read_db_config',lambda _: {})
    for reader in (original,bounded):monkeypatch.setattr(reader,'_connect',lambda config:WindowConnection(rows=rows))
    kwargs=dict(assessed_at=targets[-1]+timedelta(minutes=5),sensor_epoch=EPOCHS['air'])
    assert bounded.native(targets,**kwargs)==original.native(targets,**kwargs)
