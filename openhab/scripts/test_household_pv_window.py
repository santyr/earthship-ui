"""Captured-PV scoring must not bridge missing, ambiguous or wrong-scope power."""
from datetime import datetime,timedelta,timezone
import importlib,json
import pytest
from household.codec import identity

START=datetime(2026,10,15,16,tzinfo=timezone.utc);END=START+timedelta(hours=1)
EPOCH='00000000-0000-4000-8000-000000000001'
POLICY=json.dumps(dict(version=1,policy='qualified_power_evidence_v1',item_name='Power_Evidence_JSON',cutover=(START-timedelta(days=1)).isoformat()))


def raw(at,sequence=1,watts=1000,epoch=EPOCH):
    stamp=int(at.timestamp()*1000)
    field=dict(status='valid',reason='ok',observedAt=stamp,validUntil=stamp+120000,watts=watts)
    return json.dumps(dict(version=1,streamEpoch=epoch,sequence=sequence,recordedAt=stamp,fields={name:dict(field) for name in ('battery.dc_power_w','pv.input_power_w','pv.output_power_w')}))


def packet(rows=None,start=START):
    api=importlib.import_module('household_pv_window');end=start+timedelta(hours=1)
    if rows is None:rows=[(start+timedelta(seconds=s),raw(start+timedelta(seconds=s),i+1)) for i,s in enumerate(range(0,3600,60))]
    return api,api.build_hour_source(rows=rows,start=start,end=end,requested_at=end+timedelta(minutes=5),received_at=end+timedelta(minutes=5,seconds=1),item_id=612,policy_raw=POLICY)


def test_controller_output_and_predicted_energy_use_identical_covered_intervals():
    api,source=packet([(START,raw(START)),(START+timedelta(seconds=60),'invalid')])
    out=api.account_hour(source,assessed_at=END+timedelta(minutes=6),start=START,end=END,source_epoch=EPOCH)
    assert out['known_controller_dc_kwh']==pytest.approx(1/60)
    assert out['covered_seconds']==60 and out['missing_seconds']==3540
    assert source['rows'][-1][1]=='invalid'


@pytest.mark.parametrize('damage',['sequence','epoch','different_epoch'])
def test_ambiguous_or_changed_stream_is_not_scored(damage):
    rows=[(START,raw(START,2)),(START+timedelta(seconds=60),raw(START+timedelta(seconds=60),3))]
    if damage=='sequence':rows[1]=(rows[1][0],raw(rows[1][0],1))
    if damage=='epoch':rows[1]=(rows[1][0],raw(rows[1][0],1,epoch='00000000-0000-4000-8000-000000000002'))
    api,source=packet(rows)
    out=api.account_hour(source,assessed_at=END+timedelta(minutes=6),start=START,end=END,source_epoch=EPOCH if damage!='different_epoch' else '00000000-0000-4000-8000-000000000003')
    assert out['status']=='unavailable' and out['known_controller_dc_kwh'] is None


@pytest.mark.parametrize('damage',['hash','identity','policy','future','wrong_hour','duplicate','oversize'])
def test_bad_original_packet_refuses_before_numeric_accounting(damage):
    api,source=packet();end=END
    if damage=='hash':source['source_sha256']='f'*64
    elif damage=='identity':source['source_identity']='PV_Daily_Energy'
    elif damage=='policy':source['policy_raw']=source['policy_raw'].replace('Power_Evidence_JSON','Other')
    elif damage=='future':source['received_at']=(END+timedelta(minutes=7)).isoformat()
    elif damage=='wrong_hour':end+=timedelta(hours=1)
    elif damage=='duplicate':source['rows'][1][0]=source['rows'][0][0]
    else:source['rows'][0][1]='x'*4097
    if damage!='hash':source['source_sha256']=identity({k:v for k,v in source.items() if k!='source_sha256'})
    with pytest.raises(ValueError):api.account_hour(source,assessed_at=END+timedelta(minutes=6),start=START,end=end,source_epoch=EPOCH)


def test_cutover_is_retained_and_never_inferred_from_available_history():
    api,source=packet();policy=json.loads(POLICY);policy['cutover']=(START+timedelta(minutes=30)).isoformat()
    source=api.build_hour_source(rows=[(datetime.fromisoformat(at),value) for at,value in source['rows']],start=START,end=END,requested_at=END+timedelta(minutes=5),received_at=END+timedelta(minutes=5,seconds=1),item_id=612,policy_raw=json.dumps(policy))
    out=api.account_hour(source,assessed_at=END+timedelta(minutes=6),start=START,end=END,source_epoch=EPOCH)
    assert out['covered_seconds']==1740 and out['known_controller_dc_kwh']==pytest.approx(29/60)


def test_fixed_controller_query_is_bounded_readonly_and_retains_policy(tmp_path):
    class Connection:
        def __init__(self):self.calls=[];self.closed=False
        def set_session(self,**kw):self.session=kw
        def cursor(self):return self
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,query,args=None):self.calls.append((query,args));self.query=query
        def fetchone(self):return ('on',)
        def fetchall(self):return [(612,)] if 'public.items' in self.query else [(START,raw(START))]
        def close(self):self.closed=True
    api=importlib.import_module('household_pv_window');policy=tmp_path/'policy.json';policy.write_text(POLICY);connection=Connection()
    times=iter([END+timedelta(minutes=5),END+timedelta(minutes=5,seconds=1)])
    source=api.capture_hour(connect=lambda **kw:connection,start=START,end=END,clock=lambda:next(times),remaining=lambda:10.,policy_path=policy)
    assert source['policy_raw']==POLICY and connection.closed and connection.session['readonly'] is True
    query,args=next((q,a) for q,a in connection.calls if 'FROM public.item0612' in q)
    assert 'LIMIT 6001' in query and args==(START-timedelta(seconds=120),END)
    assert all(q.split()[0] in {'SELECT','SHOW','SET'} for q,_ in connection.calls)


def test_controller_output_target_is_distinct_from_array_input_and_battery_charge():
    at=START;payload=json.loads(raw(at));payload['fields']['pv.input_power_w']['watts']=2000;payload['fields']['battery.dc_power_w']['watts']=-500
    api,source=packet([(at,json.dumps(payload))]);out=api.account_hour(source,assessed_at=END+timedelta(minutes=6),start=START,end=END,source_epoch=EPOCH)
    assert out['known_controller_dc_kwh']==pytest.approx(1/30) and out['covered_seconds']==120


def test_valid_zero_generation_is_distinct_from_an_empty_meter_hour():
    api,source=packet([(START+timedelta(seconds=s),raw(START+timedelta(seconds=s),i+1,0)) for i,s in enumerate(range(0,3600,60))])
    out=api.account_hour(source,assessed_at=END+timedelta(minutes=6),start=START,end=END,source_epoch=EPOCH)
    assert out['known_controller_dc_kwh']==0 and out['coverage']==1
    _,empty=packet([]);unknown=api.account_hour(empty,assessed_at=END+timedelta(minutes=6),start=START,end=END,source_epoch=EPOCH)
    assert unknown['coverage']==0 and unknown['missing_seconds']==3600


def test_repeated_local_clock_hour_is_one_elapsed_UTC_hour():
    start=datetime.fromisoformat('2026-11-01T01:30:00-06:00');end=datetime.fromisoformat('2026-11-01T01:30:00-07:00');api=importlib.import_module('household_pv_window')
    rows=[(start+timedelta(seconds=s),raw(start+timedelta(seconds=s),i+1)) for i,s in enumerate(range(0,3600,60))]
    source=api.build_hour_source(rows=rows,start=start,end=end,requested_at=end+timedelta(minutes=5),received_at=end+timedelta(minutes=5,seconds=1),item_id=612,policy_raw=POLICY)
    out=api.account_hour(source,assessed_at=end+timedelta(minutes=6),start=start,end=end,source_epoch=EPOCH)
    assert out['covered_seconds']==3600 and out['known_controller_dc_kwh']==pytest.approx(1)
