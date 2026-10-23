"""The retained refresh experiment replays literal observations without a query."""
from datetime import timedelta
import gzip,importlib.util,json
from pathlib import Path
import pytest
from test_refresh_evaluation import sources,publication
from learning_fixtures import T,SITE,EPOCH
from weather_learning.contracts import canonical,identity


def experiment():
    assert importlib.util.find_spec('refresh_retained_experiment'), 'Task6 actual retained outcome experiment missing'
    import refresh_retained_experiment
    return refresh_retained_experiment


def measurements(path):
    from daily_temperature_runtime import SOURCE_POLICY
    from weather_temperature_evidence import TemperaturePolicy,temperature_receipt
    from weather_learning.historical_measurements import capture_temperature_day
    path.mkdir(mode=0o700)
    at=T+timedelta(hours=11);received=at-timedelta(seconds=10)
    policy=TemperaturePolicy(**SOURCE_POLICY)
    receipt=temperature_receipt(dict(model='Fineoffset-WH65B',id=206,tempf=64.4),policy=policy,
        stream_epoch=EPOCH,received_at=received)
    receipt.update(version=2,sensorEpoch=EPOCH)
    snapshot=json.dumps(dict(version=2,streamEpoch=EPOCH,records=dict(outdoor=receipt)))
    source=dict(schema='earthship-historical-temperature-day/v1',start=T.isoformat(),end=(T+timedelta(days=1)).isoformat(),
        requested_at=(T+timedelta(days=2)).isoformat(),received_at=(T+timedelta(days=2,seconds=1)).isoformat(),
        source_item='Weather_Temperature_Evidence_JSON',rows=[[(at-timedelta(seconds=5)).isoformat(),snapshot]])
    source['source_sha256']=identity(source)
    p=path/'2026-01-01.temperature-source.json.gz';p.write_bytes(gzip.compress(canonical(source),mtime=0));p.chmod(0o600)
    grid=capture_temperature_day(path,'2026-01-01',connection_factory=None,policies=dict(outdoor=policy),epochs=dict(outdoor=EPOCH),
        clock=lambda:T+timedelta(days=3),persist=False)
    p=path/(grid['grid_sha256']+'.temperature-grid.json');p.write_bytes(canonical(grid));p.chmod(0o600)
    index=dict(schema='earthship-historical-temperature-index/v1',days=[dict(date='2026-01-01',grid_sha256=grid['grid_sha256'],source_sha256=source['source_sha256'])],automatic_actuation=False)
    index['index_sha256']=identity(index)
    p=path/'temperature-index.json';p.write_bytes(canonical(index));p.chmod(0o600)


def test_actual_retained_experiment_replays_native_receipts_and_preserves_inputs(tmp_path,sources):
    attempt,result=publication(tmp_path,sources);publication_root=tmp_path/'publications'
    root=tmp_path/'measurements';measurements(root)
    before={p:p.read_bytes() for p in [*root.iterdir(),*publication_root.iterdir()]}
    report=experiment().run(publication_directory=publication_root,archive_path=sources[0].root,
        measurement_root=root,output=tmp_path/'results',site=SITE,root=Path(__file__).resolve().parents[4],audit_state={'blocked_attempts':{}})
    assert report['decisions']==1 and report['qualified_scores']==1
    assert all(p.read_bytes()==raw for p,raw in before.items())
    saved=json.loads((tmp_path/'results'/(report['experiment_sha256']+'.experiment.json')).read_bytes())
    c=next(c for c in saved['report']['comparisons'] if c['comparison']=='latest_48h_collection_vs_latest_360h_collection')
    assert c['matched']['left']['mae_c']==pytest.approx(2)
    assert c['matched']['right']['mae_c']==pytest.approx(8)
    assert c['disposition']=='insufficient_evidence'
    assert saved['production_changed'] is False


def test_missing_retained_result_is_not_reconstructed_or_backfilled(tmp_path,sources):
    publication(tmp_path,sources);root=tmp_path/'measurements';measurements(root)
    next((tmp_path/'publications').glob('*.publication-result-v1.json')).unlink()
    with pytest.raises(ValueError,match='result'):
        experiment().run(publication_directory=tmp_path/'publications',archive_path=sources[0].root,
            measurement_root=root,output=tmp_path/'results',site=SITE,root=Path(__file__).resolve().parents[4],audit_state={'blocked_attempts':{}})
