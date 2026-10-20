from datetime import datetime,timedelta,timezone
from io import BytesIO
from pathlib import Path
import json,gzip
import pytest

START=datetime(2026,8,6,14,tzinfo=timezone.utc)
BANK=datetime(2026,7,19,6,tzinfo=timezone.utc)
CUTOVER=datetime(2026,9,10,21,51,32,812382,tzinfo=timezone.utc)


def inputs():
    return dict(start=START,end=START+timedelta(minutes=5),bank_start=BANK,soc_receipt_start=CUTOVER,
        power=[(START-timedelta(seconds=5)+timedelta(seconds=5*i),800.) for i in range(62)],
        soc=[(START-timedelta(minutes=5),79.),(START-timedelta(seconds=5),80.)],
        mode=[(START-timedelta(hours=1),769.),(START+timedelta(hours=1),773.)])


def test_older_training_proxy_preserves_unknown_health_and_recent_soc_age():
    from weather_learning.pv_legacy_history import numeric_proxy_intervals
    rows=numeric_proxy_intervals(**inputs());eligible=[r for r in rows if r['potential_proxy_eligible']]
    assert len(rows)==5 and len(eligible)==1
    assert eligible[0]['outcome_w']==800.
    assert eligible[0]['covered_seconds']==60.
    assert eligible[0]['measurement_health_qualified'] is False
    assert eligible[0]['physical_calibration_qualified'] is False
    assert eligible[0]['soc_state_age_end_seconds']==65.
    assert eligible[0]['positive_charge_basis']=='recent_persisted_soc_increase_not_measured_DC_power'


@pytest.mark.parametrize('damage',['float','invalid_power','missing_power','stale_soc','no_rise','after_receipt_cutover','before_bank'])
def test_older_proxy_excludes_unsupported_intervals_without_filling_health_gaps(damage):
    from weather_learning.pv_legacy_history import numeric_proxy_intervals
    args=inputs()
    if damage=='float':args['mode'][0]=(args['mode'][0][0],773.)
    elif damage=='invalid_power':args['power']=[(START,None)]
    elif damage=='missing_power':args['power']=[]
    elif damage=='stale_soc':args['soc']=[(START-timedelta(minutes=8),79.),(START-timedelta(minutes=5),80.)]
    elif damage=='no_rise':args['soc']=[(START-timedelta(minutes=5),80.),(START-timedelta(seconds=5),79.)]
    elif damage=='after_receipt_cutover':args['soc_receipt_start']=START
    else:args['bank_start']=START+timedelta(minutes=10)
    assert not any(r['potential_proxy_eligible'] for r in numeric_proxy_intervals(**args))


def test_capture_reuses_original_clocks_and_refuses_changed_bytes(tmp_path):
    from weather_learning.pv_legacy_history import capture_query
    from openhab_runtime_io import ReadBudget
    tmp_path.chmod(0o700);calls=[]
    class Response(BytesIO):
        def geturl(self):return calls[-1]
    raw=json.dumps({'name':'PV_Power','data':[{'time':int(START.timestamp()*1000),'state':'800.0'}]}).encode()
    def opener(request,timeout):calls.append(request.full_url);return Response(raw)
    args=dict(item='PV_Power',start=START,end=START+timedelta(hours=2),budget=ReadBudget(20,max_requests=4),token_reader=lambda:'fixture',opener=opener,pace=lambda size:None,clock=lambda:START+timedelta(days=2))
    original,path=capture_query(tmp_path,**args)
    again,_=capture_query(tmp_path,**dict(args,clock=lambda:START+timedelta(days=3)))
    assert len(calls)==1 and original==again
    assert original['raw']==raw.decode() and original['measurement_health_qualified'] is False
    with gzip.open(path,'rb') as f:changed=json.load(f)
    changed['raw']='changed';path.write_bytes(gzip.compress(json.dumps(changed).encode()))
    with pytest.raises(ValueError,match='identity'):capture_query(tmp_path,**args)
    with pytest.raises(ValueError,match='Item'):capture_query(tmp_path,**dict(args,item='AnythingElse'))


def test_conflicting_duplicate_numeric_states_remain_an_invalid_barrier():
    from weather_learning.pv_legacy_history import numeric_rows
    from weather_learning.contracts import identity
    source=dict(item='PV_Power',start=START.isoformat(),end=(START+timedelta(hours=1)).isoformat(),raw=json.dumps({'name':'PV_Power','data':[{'time':int(START.timestamp()*1000),'state':'800.0'},{'time':int(START.timestamp()*1000),'state':'UNDEF'}]}))
    source['source_sha256']=identity(source)
    assert numeric_rows([source],item='PV_Power')==[(START,None)]


def test_receipt_soc_can_support_old_pv_without_promoting_numeric_meter_health():
    from weather_learning.pv_legacy_history import atomic_proxy_intervals
    start=datetime(2026,9,17,14,tzinfo=timezone.utc);args=inputs();args.update(start=start,end=start+timedelta(minutes=5))
    args.pop('soc_receipt_start');args['power']=[(start+timedelta(seconds=5*i),800.) for i in range(61)]
    args['mode']=[(start-timedelta(hours=1),769.),(start+timedelta(hours=1),773.)];args['soc']=[]
    for i in range(-10,11):
        at=start+timedelta(seconds=30*i);t=int(at.timestamp()*1000)
        raw=json.dumps(dict(version=1,streamEpoch='00000000-0000-4000-8000-000000000001',recordedAt=t,status='valid',reason='ok',observedAt=t,scaleObservedAt=t,validUntil=t+120000,soc=79 if i<0 else 80))
        args['soc'].append((at,raw))
    result=atomic_proxy_intervals(**args)
    assert all(r['potential_proxy_eligible'] for r in result)
    assert all(r['soc_measurement_health_qualified'] for r in result)
    assert not any(r['measurement_health_qualified'] for r in result)
    assert not any(r['potential_proxy_eligible'] for r in atomic_proxy_intervals(**dict(args,soc=[])))


def test_selected_geometry_reuses_exact_minute_instants_and_original_clocks(tmp_path):
    from historical_pv_legacy_assess import target_geometry
    from weather_learning.config import Site
    from astro_geometry import build_cache
    runtime=dict(binding_version='5.2.3',libraries=dict(astro_binding='a'*64,openhab_core='b'*64),collector_sha256='c'*64)
    points=[START+timedelta(minutes=1),START+timedelta(minutes=7)];calls=[];now=START+timedelta(days=30)
    def capture(request,source,**kwargs):
        calls.append(request)
        raw=''.join(at+'\t30.0\t110.0\n' for at in request['instants']).encode()
        return build_cache(request,source,native_output=raw,computed_at=now)
    args=dict(points=points,site=Site(38.3739919,-105.7744609,'America/Denver'),runtime=runtime,libraries={},guard=lambda:None,capture=capture)
    first=target_geometry(tmp_path,clock=lambda:now,**args);second=target_geometry(tmp_path,clock=lambda:now+timedelta(days=1),**args)
    assert first.to_dict()==second.to_dict() and len(calls)==1
    assert calls[0]['instants']==[at.isoformat() for at in points]


def test_bank_epoch_config_uses_public_config_reader_and_rejects_ambiguous_current_bank(tmp_path):
    from historical_pv_legacy_assess import read_bank_epochs
    path=tmp_path/'epochs.json';value=dict(timezone='America/Denver',epochs=[dict(start_local_date='2026-01-01',current_analytics=False),dict(start_local_date='2026-07-19',current_analytics=True)])
    path.write_text(json.dumps(value));path.chmod(0o664)
    raw,start=read_bank_epochs(path)
    assert start==BANK and json.loads(raw)==value
    value['epochs'][0]['current_analytics']=True;path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='unique'):read_bank_epochs(path)


def test_pairing_uses_an_earlier_google_issue_and_does_not_fill_missing_geometry():
    from historical_pv_legacy_assess import pair_older
    from test_daily_pv_potential import ARRAY
    end=START+timedelta(minutes=1);hour=START.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    weather={hour.isoformat():{'station_head_temperature_2m':20.,'surface_solar_radiation_downwards_1hr':500.,'wind_speed_10m':1.}}
    runs=[(START-timedelta(hours=2),'a'*64,weather,'historical_assumption'),(START+timedelta(minutes=1),'b'*64,weather,'historical_assumption')]
    label=dict(start=START.isoformat(),end=end.isoformat(),outcome_w=800.,source_sha256='c'*64,censoring_basis='numeric_proxy',positive_charge_basis='recent_soc_rise')
    horizon=[dict(azimuth_degrees=i*7.5,elevation_degrees=5.) for i in range(48)];positions={end.isoformat():dict(elevation_degrees=30.,azimuth_degrees=110.)}
    rows,missing=pair_older([label],runs=runs,positions=positions,array=ARRAY,horizon=horizon)
    assert missing==0 and len(rows)==1
    assert rows[0]['forecast_sha256']=='a'*64 and rows[0]['origin']==(START-timedelta(hours=2)).isoformat()
    assert rows[0]['outcome_w']==800. and rows[0]['measurement_health_qualified'] is False
    rows,missing=pair_older([label],runs=runs,positions={},array=ARRAY,horizon=horizon)
    assert rows==[] and missing==1
