"""Native errors replay whole original queries, rather than cached scalars."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import json
import pytest
from test_native_thermal_score import issued,api,originals,ISSUE
from thermal_model.temperature_history import STREAMS,POLICY
from thermal_model.recent_cycles import shifted_clock
from weather_temperature_evidence import TemperaturePolicy,MODELS
from weather_temperature_receiver import TemperatureCollector
from weather_temperature_sources import build_temperature_source,write_compressed_temperature_source,replay_temperature_source
import native_thermal_forecast as forecast


def queried(tmp_path,monkeypatch,originals,*,history='available',hours=1):
    capture,receipts,k=issued(tmp_path,monkeypatch,originals)
    origin=forecast.persist(tmp_path,capture)
    epoch=capture['candidate']['fit']['sensor_epochs']['air']
    stream,model,sensor=STREAMS['air'];policy=TemperaturePolicy(model,sensor,**POLICY)
    target=ISSUE+timedelta(hours=hours);assessed=target+timedelta(minutes=10)
    paths=[];grid=[];selected=None;whole={}
    first=2 if hours==24 else 1
    lags=range(first,first+7) if history=='available' else range(first,32)
    for lag in [*lags,0]:
        targets=[shifted_clock(ISSUE,lag),shifted_clock(target,lag)] if lag else [target]
        rows=[]
        for index,at in enumerate(targets):
            if history=='missing' and lag:continue
            if at in whole:
                rows.append(whole[at]);continue
            clock=at-timedelta(seconds=30)
            collector=TemperatureCollector({stream:policy},sensor_epochs={stream:epoch},clock=lambda:clock,monotonic=lambda:1000,process_id=lambda:1)
            value=70-lag*2+index*2 if hours==24 and lag else (70+index*2) if lag else 75
            collector.observe({'model':model,'id':str(sensor),MODELS[model][1]:str(value)})
            whole[at]=(at-timedelta(seconds=20),json.dumps(collector.snapshot()))
            rows.append(whole[at])
        packet=build_temperature_source(rows=rows,targets=targets,assessed_at=ISSUE if lag else assessed,stream=stream,policy=policy,sensor_epoch=epoch)
        paths.append(str(write_compressed_temperature_source(tmp_path,packet)))
        values=json.loads(json.dumps(replay_temperature_source(packet),default=lambda v:v.isoformat()))
        if lag:
            seen={row[0] for row in grid}
            grid.extend(row for row in values if row[0] not in seen)
        else:selected=values[0][1]
    return dict(capture_path=str(origin),receipts=receipts,outcome=selected,recent_cycle_grid=grid,source_paths=paths,horizon_hours=hours,assessed_at=assessed,**k)


def build(args):return api().build_source_score(**args)

def validate(record,args):
    return api().validate_source_score(record,runtime=args['runtime'],expected_artifact_sha256=args['expected_artifact_sha256'],expected_capture_sha256=args['expected_capture_sha256'],expected_source_score_sha256=record['source_score_sha256'])


def test_source_score_replays_available_baseline_and_private_roundtrip(tmp_path,monkeypatch,originals):
    args=queried(tmp_path,monkeypatch,originals);record=build(args)
    assert record['pair']['predictions']['recent_cycle']==76
    assert record['pair']['recent_cycle']['qualified_cycles']==7
    assert record['pair']['errors']['recent_cycle']==1
    assert record['release_authority'] is False
    assert validate(record,args)==record
    path=api().persist_source_score(tmp_path,record)
    assert path.stat().st_mode & 0o777==0o600
    assert api().read_source_score(path,runtime=args['runtime'],expected_artifact_sha256=args['expected_artifact_sha256'],expected_capture_sha256=args['expected_capture_sha256'],expected_source_score_sha256=record['source_score_sha256'])==record


def test_full_31_day_null_query_search_remains_insufficient_not_fabricated(tmp_path,monkeypatch,originals):
    args=queried(tmp_path,monkeypatch,originals,history='missing');record=build(args)
    assert len(args['source_paths'])==32
    assert record['pair']['recent_cycle']['exclusions']=={'qualified_cycle_unavailable':31}
    assert record['pair']['predictions']['recent_cycle'] is None
    assert validate(record,args)==record


@pytest.mark.parametrize('damage',['cached_outcome','cached_history','missing_coverage','missing_original','wrong_capture','wrong_artifact'])
def test_raw_source_score_refuses_forged_missing_or_unpinned_inputs(tmp_path,monkeypatch,originals,damage):
    args=queried(tmp_path,monkeypatch,originals)
    if damage=='cached_outcome':args['outcome']['temperatureF']=99
    if damage=='cached_history':args['recent_cycle_grid'][0][1]['temperatureF']=99
    if damage=='missing_coverage':
        args['recent_cycle_grid']=args['recent_cycle_grid'][2:];args['source_paths']=args['source_paths'][1:]
    if damage=='missing_original':Path(args['source_paths'][-1]).unlink()
    if damage=='wrong_capture':args['expected_capture_sha256']='f'*64
    if damage=='wrong_artifact':args['expected_artifact_sha256']='f'*64
    with pytest.raises((ValueError,OSError)):build(args)


@pytest.mark.parametrize('damage',['pair','baseline','query_deleted','capture_deleted','root','clock'])
def test_resealed_source_scores_rederive_original_capture_queries_and_errors(tmp_path,monkeypatch,originals,damage):
    args=queried(tmp_path,monkeypatch,originals);record=build(args)
    if damage=='pair':
        record['pair']['predictions']['model']+=1;record['pair']['errors']['model']+=1
        record['pair']['pair_sha256']=api().digest(record['pair'],'pair_sha256')
    if damage=='baseline':record['pair']['recent_cycle']['qualified_cycles']=6
    if damage=='query_deleted':Path(args['source_paths'][-1]).unlink()
    if damage=='capture_deleted':Path(args['capture_path']).unlink()
    if damage=='clock':record['assessed_at']=record['assessed_at'].split('+')[0]+'.0000009+00:00'
    root=record['source_score_sha256']
    record['source_score_sha256']=api().digest(record,'source_score_sha256')
    if damage=='root':record['source_score_sha256']='f'*64
    with pytest.raises((ValueError,OSError)):validate(record,args)


def test_source_score_freezes_caller_before_budget_callbacks(tmp_path,monkeypatch,originals):
    args=queried(tmp_path,monkeypatch,originals)
    def mutate():args['outcome']['temperatureF']=99;args['recent_cycle_grid'].clear()
    record=api().build_source_score(**args,check_budget=mutate)
    assert record['pair']['outcome']['temperatureF']==75
    assert record['pair']['predictions']['recent_cycle']==76


@pytest.mark.parametrize('field',['recordedAt','receivedAt','validUntil'])
def test_raw_original_receipt_clocks_cannot_be_silently_truncated(tmp_path,monkeypatch,originals,field):
    from weather_temperature_sources import read_compressed_temperature_source
    args=queried(tmp_path,monkeypatch,originals)
    path=Path(args['source_paths'][-1]);packet=read_compressed_temperature_source(path.parent,path)
    raw=json.loads(packet['native_rows'][0][1]);receipt=raw['records'][STREAMS['air'][0]]
    receipt[field]=receipt[field].split('+')[0]+'.0000009+00:00'
    packet['native_rows'][0][1]=json.dumps(raw)
    args['source_paths'][-1]=str(write_compressed_temperature_source(tmp_path,packet))
    args['outcome']=json.loads(json.dumps(replay_temperature_source(packet),default=lambda v:v.isoformat()))[0][1]
    assert args['outcome'] is not None
    with pytest.raises(ValueError):build(args)


@pytest.mark.parametrize('hours',[6,12,24])
def test_raw_native_score_supported_horizons_preserve_historical_clock_exclusions(tmp_path,monkeypatch,originals,hours):
    args=queried(tmp_path,monkeypatch,originals,hours=hours);record=build(args)
    assert record['pair']['horizon_hours']==hours
    assert record['pair']['predictions']['recent_cycle']==76
    assert record['pair']['recent_cycle']['qualified_cycles']==7
    if hours==24:
        assert record['pair']['recent_cycle']['selected_lag_days']==list(range(2,9))
        assert record['pair']['recent_cycle']['exclusions']=={'not_strictly_historical':1}
    assert validate(record,args)==record
