"""A new read-only near24 correction binds origin and targets to one source."""
from datetime import timedelta
from hashlib import sha256
import importlib.util
from pathlib import Path
import pytest
from learning_fixtures import T,SITE,EPOCH,full_snapshot,receipt
from weather_learning.archive import Archive
from weather_learning.contracts import canonical,identity


def api():
    assert importlib.util.find_spec('weather_learning.near_term_correction'), 'Task6 independent near24 correction missing'
    from weather_learning.near_term_correction import prepare_near_term_correction
    return prepare_near_term_correction


@pytest.fixture
def context(tmp_path):
    from test_weather_site_calibration import rows
    from weather_learning.site_calibration import fit_residual,evaluate
    data=rows(12)
    for row in data:
        row['features'].update(hour_sin=0.,hour_cos=1.,season_sin=0.,season_cos=1.,origin_bias_decay_c=2.)
        row['pair_sha256']=identity({k:v for k,v in row.items() if k!='pair_sha256'})
    init=T+timedelta(days=20);now=init+timedelta(hours=10,minutes=30)
    cutoff=T+timedelta(days=8);end=T+timedelta(days=12)
    train=fit_residual(data,kind='outdoor_temperature_c',cutoff=cutoff,trained_at=cutoff,correction_limit=6.)
    report=evaluate(train,data,holdout_start=cutoff,holdout_end=end)
    model=fit_residual(data,kind='outdoor_temperature_c',cutoff=end,trained_at=now-timedelta(hours=1),correction_limit=6.)
    scripts=Path(__file__).resolve().parents[1]
    names=('site_calibration.py','historical_pairs.py','contracts.py','weights.py')
    original=dict(final_models={'outdoor_temperature_c':model['model_sha256']},reports={'outdoor_temperature_c':report},
        runtime_manifest={'openhab/scripts/weather_learning/'+name:sha256((scripts/name).read_bytes()).hexdigest() for name in names})
    original['receipt_sha256']=identity(original)
    experiment=tmp_path/'experiment.json';experiment.write_bytes(canonical(original));experiment.chmod(0o600)
    model_path=tmp_path/'model.json';model_path.write_bytes(canonical(model));model_path.chmod(0o600)
    selection=dict(schema='earthship-historical-weather-selection/v1',kind='outdoor_temperature_c',experiment_path=str(experiment),
        experiment_file_sha256=sha256(experiment.read_bytes()).hexdigest(),experiment_receipt_sha256=original['receipt_sha256'],
        model_path=str(model_path),model_file_sha256=sha256(model_path.read_bytes()).hexdigest(),model_sha256=model['model_sha256'],
        target_dates=12,sensor_epoch=EPOCH,available_at=(now-timedelta(minutes=30)).isoformat(),automatic_actuation=False)
    selection['selection_sha256']=identity(selection)
    pointer=tmp_path/'selected.json';pointer.write_bytes(canonical(selection));pointer.chmod(0o600)
    archive=Archive(tmp_path/'archive')
    full=archive.store_snapshot(full_snapshot(init,hours=360))
    short=archive.store_snapshot(full_snapshot(init+timedelta(hours=2),hours=48,temperature_k=293.15))
    return dict(archive=archive,decision_at=now,site=SITE,selection_path=pointer,
        origin_metadata=receipt(now,celsius=22),origin_acquired_at=now-timedelta(seconds=1),sensor_epoch=EPOCH),full,short


def test_near24_origin_bias_and_predictors_use_the_same_interim_not_extended_source(context):
    args,full,short=context
    value=api()(**args).to_dict()
    assert value['profile']=='near_term_local_correction_24h_v1'
    assert value['status']=='CORRECTED_READ_ONLY'
    assert value['source']['snapshot_sha256']==short
    assert value['source']['snapshot_sha256']!=full
    assert value['origin']['google_c']==20
    assert value['origin']['bias_c']==pytest.approx(2)
    assert value['hours'][0]['raw_c']==20
    assert value['hours'][0]['local_c']==pytest.approx(22)
    assert len(value['hours'])==25
    assert value['model']['selection_sha256']
    assert value['issued'] is False
    assert value['local_coverage_qualified'] is False
    assert value['automatic_actuation'] is False


def test_near24_qualifies_when_there_is_no_extended_source(context):
    args,full,_=context
    with args['archive']._connect() as db:db.execute('DELETE FROM snapshots WHERE digest=?',(full,))
    value=api()(**args).to_dict()
    assert value['status']=='CORRECTED_READ_ONLY'
    assert value['hours'][0]['local_c']==pytest.approx(22)


def test_missing_or_future_acquired_origin_has_explicit_raw_fallback(context):
    args,_,short=context
    for change in ({'origin_metadata':None},{'origin_acquired_at':args['decision_at']+timedelta(seconds=1)},
                   {'origin_acquired_at':args['decision_at']-timedelta(minutes=3)}):
        value=api()(**dict(args,**change)).to_dict()
        assert value['status']=='RAW_FALLBACK'
        assert value['reason']=='ORIGIN_UNAVAILABLE'
        assert value['source']['snapshot_sha256']==short
        assert all(row['local_c'] is None and row['selected_c']==row['raw_c'] for row in value['hours'])


def test_unavailable_selected_model_does_not_disable_raw_near_forecast(context):
    args,_,_=context
    value=api()(**dict(args,selection_path=None)).to_dict()
    assert value['status']=='RAW_FALLBACK'
    assert value['reason']=='MODEL_UNAVAILABLE'
    assert value['hours'][0]['raw_c']==20
    assert all(row['local_c'] is None for row in value['hours'])


def test_forecast_at_exact_native_origin_is_allowed_without_extrapolation(context):
    args,_,_=context
    now=args['decision_at'].replace(minute=0)
    value=api()(**dict(args,decision_at=now,origin_metadata=receipt(now,celsius=22),origin_acquired_at=now-timedelta(seconds=1))).to_dict()
    assert value['status']=='CORRECTED_READ_ONLY'
    assert value['origin']['google_c']==20
    assert len(value['hours'])==24


def test_near_term_does_not_change_extended_source_or_selected_model_files(context):
    from weather_learning.provider import load_publication_forecast
    args,_,_=context
    before=load_publication_forecast(args['archive'],decision_at=args['decision_at'],site=SITE).to_dict()
    originals={p:p.read_bytes() for p in args['selection_path'].parent.glob('*.json')}
    prepared=api()(**args);value=prepared.to_dict();value['hours'][0]['raw_c']=999
    assert prepared.to_dict()['hours'][0]['raw_c']==20
    assert all(p.read_bytes()==raw for p,raw in originals.items())
    assert load_publication_forecast(args['archive'],decision_at=args['decision_at'],site=SITE).to_dict()==before


def test_model_selection_available_after_decision_is_raw_fallback(context):
    args,_,_=context
    import json
    pointer=args['selection_path'];selection=json.loads(pointer.read_bytes())
    selection['available_at']=(args['decision_at']+timedelta(seconds=1)).isoformat()
    selection['selection_sha256']=identity({k:v for k,v in selection.items() if k!='selection_sha256'})
    pointer.write_bytes(canonical(selection))
    value=api()(**args).to_dict()
    assert value['status']=='RAW_FALLBACK'
    assert value['reason']=='MODEL_UNAVAILABLE'


def test_missing_same_source_origin_bracket_does_not_borrow_extended_origin(context):
    args,_,_=context
    from weather_learning.weathernext_ee import parse_collection_response,make_snapshot
    from weather_learning.contracts import instant
    newer=full_snapshot(args['decision_at'].replace(minute=0),hours=48,temperature_k=303.15)
    # The new run arrives before the decision but its first native point is later.
    parts=[]
    for item in newer['source_originals']:
        raw=item['payload']
        parts.append(parse_collection_response(raw,collection=item['collection'],bands=raw['region'][0][4:],site=SITE,
            initialized_at=instant(newer['initialized_at']),horizon=48))
    snapshot=make_snapshot(parts,site=SITE,initialized_at=instant(newer['initialized_at']),
        first_seen_at=args['decision_at']-timedelta(minutes=5),completed_at=args['decision_at']-timedelta(minutes=4))
    name=args['archive'].store_snapshot(snapshot)
    value=api()(**args).to_dict()
    assert value['source']['snapshot_sha256']==name
    assert value['hours'][0]['raw_c']==30
    assert value['status']=='RAW_FALLBACK'
    assert value['reason']=='ORIGIN_UNAVAILABLE'
