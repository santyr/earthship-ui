from datetime import timedelta
from unittest.mock import Mock
import pytest
from weather_learning.tests.learning_fixtures import T,native_snapshot
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


def test_verified_coverage_index_avoids_reparsing_old_runs_but_checks_file_bytes(tmp_path,monkeypatch):
    import weather_learning.historical as history
    archive=Archive(tmp_path/'history');reader=Mock();reader.fetch_points.return_value=native_snapshot(hours=2)
    result=api()(reader,archive,initializations=[T],horizon=2,now=T+timedelta(days=2))
    required={('station_head_temperature_2m',s) for s in ('mean','p10','p90')}
    monkeypatch.setattr(history,'verify_history',lambda *a:pytest.fail('reparsed completed history during acquisition selection'))
    refs=history.indexed_history(archive,horizon=2,required=required)
    assert refs[T.isoformat()]==result['snapshots'][0]['sha256']
    path=archive.objects/(result['snapshots'][0]['sha256']+'.json')
    raw=path.read_bytes();path.write_bytes(raw.replace(b'273.15',b'274.15'))
    if path.read_bytes()==raw:path.write_bytes(raw+b' ')
    with pytest.raises(ValueError):history.indexed_history(archive,horizon=2,required=required)


def test_history_selection_runs_without_training_packages(tmp_path):
    import subprocess,sys,os
    from pathlib import Path
    archive=Archive(tmp_path/'history');reader=Mock();reader.fetch_points.return_value=native_snapshot(hours=2)
    api()(reader,archive,initializations=[T],horizon=2,now=T+timedelta(days=2))
    code='''import sys
class NoTraining:
 def find_spec(self,name,*args):
  if name.split('.')[0] in ('numpy','scipy'):raise ModuleNotFoundError('training dependency forbidden')
sys.meta_path.insert(0,NoTraining())
from weather_learning.archive import Archive
from weather_learning.historical import indexed_history
value=indexed_history(Archive(sys.argv[1]),horizon=2,required={('station_head_temperature_2m',s) for s in ('mean','p10','p90')})
assert len(value)==1
'''
    result=subprocess.run([sys.executable,'-c',code,str(archive.root)],capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parent)},timeout=10)
    assert result.returncode==0,result.stderr


def test_seasonal_selection_covers_explicit_full_cycles_with_bounded_sampling():
    from weathernext_backfill import requested_initializations
    from datetime import datetime,timezone
    runs=requested_initializations('2026-01-01',262,cycles=[0,6,12,18],day_step=7,now=T.replace(year=2027))
    assert len(runs)==152
    assert runs[0]==datetime(2026,1,1,tzinfo=timezone.utc)
    assert runs[4]-runs[0]==timedelta(days=7)
    for step in (0,32):
        with pytest.raises(ValueError):requested_initializations('2026-01-01',262,cycles=[0],day_step=step,now=T.replace(year=2027))
