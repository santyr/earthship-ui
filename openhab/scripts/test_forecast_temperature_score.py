"""Raw-source correction evaluation; test fixtures are not release evidence."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import importlib,importlib.util,json
from pathlib import Path
import pytest
import forecast_intel as fi
from forecast_input_capture import _instant
from forecast_temperature_origin import TemperatureOriginObserver
from weather_temperature_evidence import MODELS,TemperaturePolicy
from weather_temperature_receiver import TemperatureCollector
from test_forecast_temperature_origin import setup,inputs


def module():
    assert importlib.util.find_spec('forecast_temperature_score') is not None, 'missing raw-source correction scorer'
    return importlib.import_module('forecast_temperature_score')


def make_case(setup,*,times=None,temperatures=None,units="°F",issue_at=None):
    origin_module,root,_,policy_path=setup;snapshot,model,adjustment,_=inputs()
    issue=issue_at or datetime(2026,10,9,13,tzinfo=timezone.utc)
    origin_module._clock=lambda:issue
    if units is not None:snapshot['hourly_units']={'temperature_2m':units}
    snapshot['timezone']='America/Denver'
    if times is not None:
        snapshot['hourly']['time']=times
        count=len(times)
        for name,value in tuple(snapshot['hourly'].items()):
            if name!='time':snapshot['hourly'][name]=[value[0]]*count
        if temperatures is not None:snapshot['hourly']['temperature_2m']=temperatures
        dates=list(dict.fromkeys(t[:10] for t in times))
        for name,value in tuple(snapshot['daily'].items()):
            snapshot['daily'][name]=dates if name=='time' else [value[0]]*len(dates)
    now=issue.astimezone(fi.MOUNTAIN)
    payloads=fi.build_forecast_payloads(snapshot,[],now,temperature_adjustment=adjustment,hourly_model=model)
    observer=TemperatureOriginObserver(root,policy_path)
    token=observer.prepare(snapshot=snapshot,payloads=payloads,hourly_model=model,temperature_adjustment=adjustment)
    path=observer.complete(token,publication_started_at=issue+timedelta(seconds=1),publication_completed_at=issue+timedelta(seconds=2))
    target=_instant(next(h['at'] for d in payloads[2]['days'] for h in d['hours']))
    at=target-timedelta(seconds=30);policy=TemperaturePolicy('Fineoffset-WH65B',206,-40.,140.,300)
    source=TemperatureCollector({'outdoor':policy},sensor_epochs={'outdoor':'11111111-1111-4111-8111-111111111111'},clock=lambda:at,monotonic=lambda:1000)
    source.observe({'model':policy.model,'id':policy.sensor_id,MODELS[policy.model][1]:70.})
    packet={'schema':'earthship-temperature-correction-score-sources/v1','origin_sha256':path.name.split('.')[0],
        'publication_receipt':{'item':'Forecast_10Day_JSON','stored_at':(issue+timedelta(seconds=1.5)).isoformat(),'state':token['detail_state']},
        'target':target.isoformat(),'assessed_at':(target+timedelta(minutes=5)).isoformat(),
        'history_start':(target-timedelta(seconds=300)).isoformat(),
        'native_rows':[[(target-timedelta(seconds=20)).isoformat(),json.dumps(source.snapshot(),separators=(',',':'))]]}
    return root,packet


@pytest.fixture
def case(setup):return make_case(setup)


def test_uses_actual_persisted_corrected_value_and_qualified_native_outcome(case):
    root,packet=case;r=module().score_sources(root,packet)
    assert r['status']=='qualified'
    assert r['raw_error_f']==-2. and r['corrected_error_f']==-6.
    assert r['raw_forecast_f']==68. and r['corrected_forecast_f']==64. and r['measured_f']==70.
    assert r['local_hour']==12 and r['calendar_season']=='autumn'
    assert r['lead_bucket']=='24-48h' and r['weather_category']=='weather_code:3'
    assert r['release_authority'] is False


@pytest.mark.parametrize('damage',['bytes','wrong_item','earlier_receipt','late_receipt','missing_receipt','incomplete_query','scalar_outcome','future_row','extra_key'])
def test_refuses_unbound_or_incomplete_source_packets(case,damage):
    root,p=case
    if damage=='bytes':p['publication_receipt']['state']+=' '
    elif damage=='wrong_item':p['publication_receipt']['item']='Forecast_Daily_JSON'
    elif damage=='earlier_receipt':p['publication_receipt']['stored_at']='2026-10-09T12:59:00+00:00'
    elif damage=='late_receipt':p['publication_receipt']['stored_at']='2026-10-09T13:10:00+00:00'
    elif damage=='missing_receipt':p['publication_receipt']=None
    elif damage=='incomplete_query':p['history_start']=p['target']
    elif damage=='scalar_outcome':p['native_rows']=[[p['target'],{'temperatureF':70.}]]
    elif damage=='future_row':p['native_rows'][0][0]=(_instant(p['target'])+timedelta(seconds=1)).isoformat()
    else:p['active']=True
    with pytest.raises(ValueError):module().score_sources(root,p)


@pytest.mark.parametrize('damage',['wrong_phase','legacy_v1','invalid_barrier','expired'])
def test_native_unqualified_points_are_withheld_not_zero_error(case,damage):
    root,p=case;v=json.loads(p['native_rows'][0][1]);record=v['records']['outdoor']
    if damage=='wrong_phase':record['sensorEpoch']='22222222-2222-4222-8222-222222222222'
    elif damage=='legacy_v1':v['version']=1;record['version']=1;record.pop('sensorEpoch')
    elif damage=='invalid_barrier':
        record.update(status='invalid',reason='temperature_invalid',receivedAt=None,validUntil=None,temperatureF=None)
    else:
        record['receivedAt']=(_instant(p['target'])-timedelta(minutes=10)).isoformat();record['recordedAt']=record['receivedAt'];record['validUntil']=(_instant(p['target'])-timedelta(minutes=5)).isoformat()
    p['native_rows'][0][1]=json.dumps(v)
    r=module().score_sources(root,p)
    assert r['status']=='withheld' and 'corrected_error_f' not in r and r['release_authority'] is False


def test_unmature_target_does_not_become_error_evidence(case):
    root,p=case;p['assessed_at']=(_instant(p['target'])+timedelta(minutes=4,seconds=59)).isoformat()
    r=module().score_sources(root,p);assert r['status']=='pending' and 'raw_error_f' not in r


def test_past_rows_in_a_newly_issued_detail_are_not_forecasts(setup):
    root,p=make_case(setup,times=['2026-10-09T06:00'])
    with pytest.raises(ValueError):module().score_sources(root,p)


def test_summary_replays_sources_and_does_not_count_duplicate_pairs(case):
    root,p=case;m=module();r=m.summarize_sources(root,[p])
    assert r['qualified_observation_count']==1 and r['unique_target_days']==1
    assert r['complete_issued_hour_days']==0
    group=r['groups'][0]
    assert group['metrics']['raw']=={'mae_f':2.,'rmse_f':2.,'bias_f':-2.}
    assert group['metrics']['corrected']=={'mae_f':6.,'rmse_f':6.,'bias_f':-6.}
    assert r['release_authority'] is False
    with pytest.raises(ValueError):m.summarize_sources(root,[p,deepcopy(p)])


def test_daily_state_does_not_replace_original_issued_values(case,monkeypatch):
    root,p=case
    monkeypatch.setattr(fi,'load_state',lambda:pytest.fail('scorer read current learning state'))
    r=module().score_sources(root,p);assert r['corrected_error_f']==-6.


@pytest.mark.parametrize('units',[None,'°C'])
def test_missing_weather_units_are_not_assumed_fahrenheit(setup,units):
    root,p=make_case(setup,units=units)
    with pytest.raises(ValueError):module().score_sources(root,p)


def native_for_target(packet,target):
    p=deepcopy(packet);p['target']=target.isoformat();p['assessed_at']=(target+timedelta(minutes=5)).isoformat()
    p['history_start']=(target-timedelta(seconds=300)).isoformat()
    v=json.loads(p['native_rows'][0][1]);r=v['records']['outdoor']
    r['recordedAt']=(target-timedelta(seconds=30)).isoformat();r['receivedAt']=r['recordedAt']
    r['validUntil']=(target+timedelta(seconds=270)).isoformat()
    p['native_rows']=[[(target-timedelta(seconds=20)).isoformat(),json.dumps(v)]]
    return p


def test_repeated_dst_hour_preserves_both_issued_offsets(setup):
    root,p=make_case(setup,times=['2026-11-01T01:00','2026-11-01T01:00'],temperatures=[68.,69.],
        issue_at=datetime(2026,10,31,13,tzinfo=timezone.utc))
    m=module();first=m.score_sources(root,p)
    second_packet=native_for_target(p,_instant(p['target'])+timedelta(hours=1));second=m.score_sources(root,second_packet)
    assert first['target']=='2026-11-01T07:00:00+00:00'
    assert second['target']=='2026-11-01T08:00:00+00:00'
    assert first['raw_forecast_f']==68. and second['raw_forecast_f']==69.
    assert first['local_hour']==second['local_hour']==1
    report=m.summarize_sources(root,[p,second_packet]);assert report['qualified_observation_count']==2
    assert report['unique_target_days']==1 and report['complete_issued_hour_days']==0


@pytest.mark.parametrize('fall_fold',[False,True])
def test_complete_issued_day_requires_all_calendar_hour_targets(setup,fall_fold):
    day='2026-11-01' if fall_fold else '2026-10-10'
    times=[day+'T'+str(h).zfill(2)+':00' for h in range(24)]
    if fall_fold:times.insert(2,day+'T01:00')
    root,p=make_case(setup,times=times,issue_at=datetime(2026,10,31,13,tzinfo=timezone.utc) if fall_fold else None)
    original=json.loads(p['publication_receipt']['state']);targets=[_instant(h['at']) for d in original['days'] for h in d['hours']]
    packets=[native_for_target(p,target) for target in targets]
    m=module();complete=m.summarize_sources(root,packets)
    assert complete['qualified_observation_count']==(25 if fall_fold else 24)
    assert complete['complete_issued_hour_days']==1
    assert m.summarize_sources(root,packets[:-1])['complete_issued_hour_days']==0


def test_immutable_packet_storage_detects_corruption_and_is_not_score_cache(case,tmp_path):
    root,p=case;directory=tmp_path/'packets';directory.mkdir(mode=0o700);m=module()
    path=m.write_sources(directory,p);loaded=m.read_sources(directory,path)
    assert m.score_sources(root,loaded)['raw_error_f']==-2.
    path.write_bytes(b'corrupt')
    with pytest.raises(ValueError):m.read_sources(directory,path)
    with pytest.raises(ValueError):m.write_sources(directory,p)
    cache=m.score_sources(root,p)
    with pytest.raises(ValueError):m.write_sources(directory,cache)


def test_nonexistent_spring_hour_is_not_relabelled_into_another_local_hour(setup):
    root,p=make_case(setup,times=['2026-03-08T02:00'],issue_at=datetime(2026,3,7,13,tzinfo=timezone.utc))
    with pytest.raises(ValueError):module().score_sources(root,p)


def test_repeated_targets_choose_earliest_issue_not_best_error(setup):
    root,first=make_case(setup)
    _,later=make_case(setup,times=['2026-10-10T12:00'],temperatures=[70.],
        issue_at=datetime(2026,10,9,14,tzinfo=timezone.utc))
    group=module().summarize_sources(root,[later,first])['groups'][0]
    assert group['qualified_observation_count']==2 and group['unique_target_count']==1
    assert group['metrics']['raw']['mae_f']==2.
    assert group['metrics']['corrected']['mae_f']==6.


def test_large_finite_bad_forecasts_do_not_overflow_error_metrics(setup):
    import math
    root,p=make_case(setup,times=['2026-10-10T12:00'],temperatures=[1e308])
    summary=module().summarize_sources(root,[p]);metrics=summary['groups'][0]['metrics']
    assert all(math.isfinite(v) for values in metrics.values() for v in values.values())
    assert metrics['raw']['rmse_f']==1e308
    assert summary['release_authority'] is False
