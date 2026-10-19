from datetime import timedelta
from unittest.mock import Mock
import pytest
from learning_fixtures import T,native_snapshot
from weather_learning.archive import Archive


def api():
    from weather_learning.historical import collect_history
    return lambda *a,**kw: collect_history(*a,bands_by_grid={'station':('station_head_temperature_2m_mean','station_head_temperature_2m_p10','station_head_temperature_2m_p90')},**kw)


def test_historical_collector_preserves_actual_acquisition_clocks_and_reuses(tmp_path):
    archive=Archive(tmp_path/'history');reader=Mock();reader.fetch_points.return_value=native_snapshot(hours=2)
    original=reader.fetch_points.return_value.copy()
    first=api()(reader,archive,initializations=[T],horizon=2,now=T+timedelta(days=2))
    assert first['downloaded']==1
    snapshot=archive.read(first['snapshots'][0]['sha256'])
    assert snapshot['historical'] is True
    assert snapshot['first_seen_at']==original['first_seen_at']
    assert snapshot['source_originals']==original['source_originals']
    second=api()(reader,archive,initializations=[T],horizon=2,now=T+timedelta(days=3))
    assert second['downloaded']==0
    assert second['snapshots']==first['snapshots']
    assert reader.fetch_points.call_count==1
    assert archive.eligible_snapshot(T+timedelta(days=2),T+timedelta(days=2,hours=1)) is None


def test_history_cannot_write_into_an_operational_archive(tmp_path):
    archive=Archive(tmp_path/'operational');archive.store_snapshot(native_snapshot(hours=2));reader=Mock()
    with pytest.raises(ValueError,match='operational'):
        api()(reader,archive,initializations=[T],horizon=2,now=T+timedelta(days=2))
    reader.initialize.assert_not_called()


def test_historical_data_must_rederive_from_original_native_capsules(tmp_path):
    archive=Archive(tmp_path/'history');reader=Mock();raw=native_snapshot(hours=2)
    raw['points'][0]['value']+=1;reader.fetch_points.return_value=raw
    with pytest.raises(ValueError,match='normalized'):
        api()(reader,archive,initializations=[T],horizon=2,now=T+timedelta(days=2))
    assert not list(archive.objects.glob('*.json'))


@pytest.mark.parametrize('initializations,horizon', [([T]*2,2),([T+timedelta(hours=1)],2),([T+timedelta(days=i) for i in range(5)],2),([T],361)])
def test_backfill_respects_bounded_explicit_runs(tmp_path,initializations,horizon):
    with pytest.raises(ValueError):api()(Mock(),Archive(tmp_path/'history'),initializations=initializations,horizon=horizon,now=T+timedelta(days=10))


def test_incomplete_requested_history_is_not_retained(tmp_path):
    archive=Archive(tmp_path/'history');reader=Mock();reader.fetch_points.return_value=native_snapshot(hours=1)
    with pytest.raises(ValueError,match='complete'):
        api()(reader,archive,initializations=[T],horizon=2,now=T+timedelta(days=2))
    assert not list(archive.objects.glob('*.json'))
