import base64
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from services.lorawan.decoders import decode
from services.lorawan.registry import Registry
from services.lorawan.engine import Engine
from services.lorawan.storage import Store

NOW = datetime(2026, 10, 13, 18, tzinfo=timezone.utc)
APP = '11111111-1111-4111-8111-111111111111'
EUI = '0000000000000001'


def config(**overrides):
    device = dict(device_id=EUI, sensor_id='opening_01', name='Commissioning 01',
        location='Unassigned', zone='unassigned', device_type='window',
        decoder='milesight_ws301/v1', hardware_epoch='22222222-2222-4222-8222-222222222222',
        radio_verified=False, state_stale_seconds=120, communication_stale_seconds=120,
        offline_seconds=300, battery_low_percent=20, battery_low_volts=2.7)
    device.update(overrides)
    return dict(schema='earthship-sensor-registry/v1', environment='simulation',
                application_id=APP, devices=[device])


def packet(counter=1, state=1, at=NOW, *, data=None, port=85, address='01020304', eui=EUI, event='up'):
    row = dict(deduplicationId=str(uuid4()), time=at.isoformat(),
        deviceInfo=dict(devEui=eui, applicationId=APP), devAddr=address)
    if event == 'up':
        row.update(fCnt=counter, fPort=port, data=base64.b64encode(data if data is not None else bytes([1,0x75,90,3,0,state])).decode(),
            rxInfo=[dict(rssi=-80,snr=7.5,gatewayId='0101010101010101')])
    return json.dumps(row).encode(), f'application/{APP}/device/{eui}/event/{event}'


def setup(tmp_path, **overrides):
    registry = Registry(config(**overrides))
    store = Store.sqlite(tmp_path/'state.sqlite')
    return Engine(registry, store), store


@pytest.mark.parametrize('raw,port,profile,state,battery', [
    ('0b880100009300002500',10,'dragino_lds02/v1','CLOSED',2.952),
    ('8b880100009300002500',10,'dragino_lds02/v1','OPEN',2.952),
    ('01755a030001040001',85,'milesight_ws301/v1','OPEN',90),
    ('017564030000040000',85,'milesight_ws301/v1','CLOSED',100),
    ('0100000100002569cd2960',2,'dragino_ds03a_lb/v1','OPEN',None),
])
def test_manufacturer_vectors(raw,port,profile,state,battery):
    point=decode(profile,bytes.fromhex(raw),port)[0]
    assert point['contact_state']==state
    assert point['battery'].get('percent',point['battery'].get('volts'))==battery


def test_ds03_status_and_datalog_are_not_live_contact():
    assert decode('dragino_ds03a_lb/v1',bytes.fromhex('1b010002020b45'),5)[0]['contact_state'] is None
    point=decode('dragino_ds03a_lb/v1',bytes.fromhex('8100000100002569cd2960'),3)[0]
    assert point['historical'] is True
    assert point['contact_state']=='OPEN'


@pytest.mark.parametrize('profile,data,port', [
    ('dragino_lds02/v1',b'',10),('dragino_lds02/v1',bytes.fromhex('8b880000000000000000'),10),
    ('dragino_lds02/v1',bytes.fromhex('8b88000001'),7),
    ('milesight_ws301/v1',bytes.fromhex('030002'),85),
    ('milesight_ws301/v1',bytes.fromhex('0175ff'),85),
    ('milesight_ws301/v1',bytes.fromhex('030001aaab00'),85),
    ('milesight_ws301/v1',bytes.fromhex('030001030000'),85),
    ('dragino_ds03a_lb/v1',b'123',2),
])
def test_invalid_or_unsupported_payload_refused(profile,data,port):
    with pytest.raises(ValueError):decode(profile,data,port)


def test_registry_rejects_duplicate_identity_secrets_and_unsafe_names():
    value=config();value['devices'].append(dict(value['devices'][0]))
    with pytest.raises(ValueError):Registry(value)
    for changes in [dict(sensor_id='../bad'),dict(app_key='secret'),dict(offline_seconds=60),dict(radio_verified='true')]:
        with pytest.raises(ValueError):Registry(config(**changes))


def test_open_to_offline_preserves_last_known_and_does_not_count_valid_open(tmp_path):
    engine,_=setup(tmp_path);engine.ingest(*packet(),received_at=NOW)
    assert engine.snapshot(NOW)['sensors'][0]['contact_state']=='OPEN'
    sensor=engine.snapshot(NOW+timedelta(seconds=301))['sensors'][0]
    assert sensor['contact_state']=='OPEN'
    assert sensor['current_state']=='UNKNOWN'
    assert sensor['health']=='OFFLINE'


def test_duplicate_and_old_packet_do_not_refresh_or_reverse(tmp_path):
    engine,store=setup(tmp_path)
    raw,topic=packet(2,1);engine.ingest(raw,topic,received_at=NOW)
    assert engine.ingest(raw,topic,received_at=NOW+timedelta(seconds=200))=='duplicate'
    assert engine.ingest(*packet(1,0,at=NOW-timedelta(seconds=1)),received_at=NOW+timedelta(seconds=201))=='out_of_order'
    sensor=engine.snapshot(NOW+timedelta(seconds=201))['sensors'][0]
    assert sensor['last_received_at']==NOW.isoformat()
    assert sensor['contact_state']=='OPEN' and sensor['current_state']=='UNKNOWN'
    assert store.count('raw_events')==3


def test_status_only_does_not_refresh_contact(tmp_path):
    engine,_=setup(tmp_path)
    engine.ingest(*packet(),received_at=NOW)
    engine.ingest(*packet(2,at=NOW+timedelta(seconds=200),data=bytes.fromhex('01755a')),received_at=NOW+timedelta(seconds=200))
    sensor=engine.snapshot(NOW+timedelta(seconds=200))['sensors'][0]
    assert sensor['health']=='ONLINE' and sensor['current_state']=='UNKNOWN'


def test_invalid_registered_payload_invalidates_then_contact_recovers(tmp_path):
    engine,_=setup(tmp_path);engine.ingest(*packet(),received_at=NOW)
    engine.ingest(*packet(2,at=NOW+timedelta(seconds=1),data=b'bad'),received_at=NOW+timedelta(seconds=1))
    assert engine.snapshot(NOW+timedelta(seconds=1))['sensors'][0]['current_state']=='UNKNOWN'
    engine.ingest(*packet(3,at=NOW+timedelta(seconds=2)),received_at=NOW+timedelta(seconds=2))
    assert engine.snapshot(NOW+timedelta(seconds=2))['sensors'][0]['current_state']=='OPEN'


def test_counter_conflict_and_reset_require_trusted_join(tmp_path):
    engine,_=setup(tmp_path);engine.ingest(*packet(10),received_at=NOW)
    assert engine.ingest(*packet(10,0),received_at=NOW)=='counter_conflict'
    assert engine.ingest(*packet(1,at=NOW+timedelta(seconds=1)),received_at=NOW+timedelta(seconds=1))=='counter_regression'
    assert engine.snapshot(NOW+timedelta(seconds=1))['sensors'][0]['current_state']=='UNKNOWN'
    join_at=NOW+timedelta(seconds=2)
    assert engine.ingest(*packet(at=join_at,address='02030405',event='join'),received_at=join_at)=='joined'
    assert engine.ingest(*packet(1,0,at=join_at+timedelta(seconds=1),address='02030405'),received_at=join_at+timedelta(seconds=1))=='accepted'
    assert engine.ingest(*packet(11,1,at=join_at+timedelta(seconds=2)),received_at=join_at+timedelta(seconds=2))=='wrong_session'


def test_retained_unknown_future_and_wrong_application_never_supply_state(tmp_path):
    engine,store=setup(tmp_path)
    assert engine.ingest(*packet(),received_at=NOW,retained=True)=='retained_input'
    assert engine.ingest(*packet(eui='0000000000000002'),received_at=NOW)=='unknown_device'
    assert engine.ingest(*packet(at=NOW+timedelta(seconds=1)),received_at=NOW)=='future_timestamp'
    raw,topic=packet();row=json.loads(raw);row['deviceInfo']['applicationId']='wrong'
    assert engine.ingest(json.dumps(row).encode(),topic,received_at=NOW)=='identity_mismatch'
    assert engine.snapshot(NOW)['sensors'][0]['current_state']=='UNKNOWN'
    assert store.count('raw_events')==4


def test_persistent_restart_and_history_transition_duration(tmp_path):
    engine,store=setup(tmp_path);engine.ingest(*packet(),received_at=NOW)
    later=NOW+timedelta(seconds=60)
    engine.ingest(*packet(2,0,at=later),received_at=later)
    assert any(row['event_type']=='closed' for row in engine.snapshot(later)['recent_events'])
    assert engine.snapshot(later)['daily_durations'][0]['open_seconds']==60
    store.close()
    restarted=Engine(Registry(config()),Store.sqlite(tmp_path/'state.sqlite'))
    assert restarted.snapshot(later)['sensors'][0]['contact_state']=='CLOSED'
    assert restarted.ingest(*packet(1,1),received_at=later)=='out_of_order'


def test_hardware_epoch_change_refuses_old_state(tmp_path):
    engine,store=setup(tmp_path);engine.ingest(*packet(),received_at=NOW)
    newer=Engine(Registry(config(hardware_epoch='33333333-3333-4333-8333-333333333333')),store)
    assert newer.snapshot(NOW)['sensors'][0]['current_state']=='UNKNOWN'


def test_history_is_censored_at_invalid_payload_barrier(tmp_path):
    engine,_=setup(tmp_path);engine.ingest(*packet(),received_at=NOW)
    bad=NOW+timedelta(seconds=30)
    engine.ingest(*packet(2,at=bad,data=b'bad'),received_at=bad)
    later=NOW+timedelta(seconds=100)
    engine.ingest(*packet(3,0,at=later),received_at=later)
    assert engine.snapshot(later)['daily_durations'][0]['open_seconds']==30


def test_delayed_datalog_is_archived_without_refreshing_contact(tmp_path):
    engine,store=setup(tmp_path,decoder='dragino_ds03a_lb/v1')
    data=bytes.fromhex('01000001000025')+int(NOW.timestamp()).to_bytes(4,'big')
    engine.ingest(*packet(data=data,port=2),received_at=NOW)
    later=NOW+timedelta(seconds=200)
    older=bytes.fromhex('80000001000025')+int((NOW-timedelta(seconds=100)).timestamp()).to_bytes(4,'big')
    engine.ingest(*packet(2,at=later,data=older,port=3),received_at=later)
    sensor=engine.snapshot(later)['sensors'][0]
    assert sensor['contact_state']=='OPEN' and sensor['current_state']=='UNKNOWN'
    assert any(p.get('historical') for p in store.history())


def test_deterministic_replay_of_sixteen_devices_and_faults(tmp_path):
    from services.lorawan.simulate import registry,events
    from services.observations.replay import replay
    reg=Registry(registry());batch=events(NOW,faults=True)
    left=Engine(reg,Store.sqlite());right=Engine(reg,Store.sqlite())
    assert replay(left,batch)==replay(right,batch)
    view=left.snapshot(NOW+timedelta(seconds=5))
    assert len(view['sensors'])==16
    assert len(set(s['device_id'] for s in view['sensors']))==16
    assert view['sensors'][2]['current_state']=='UNKNOWN'


def test_gateway_stats_activity_expires_and_never_supplies_contact(tmp_path):
    from services.lorawan.simulate import registry
    from services.lorawan.health import gateway_health
    engine=Engine(Registry(registry()),Store.sqlite())
    assert engine.gateway_activity(b'opaque stats','us915_1/gateway/aaaaaaaaaaaaaaaa/event/stats',NOW)=='gateway_activity'
    assert gateway_health(engine,NOW)[0]['health']=='ONLINE'
    assert gateway_health(engine,NOW+timedelta(seconds=121))[0]['health']=='OFFLINE'
    assert engine.snapshot(NOW)['sensors'][0]['current_state']=='UNKNOWN'


def test_equal_timestamp_counter_order_is_deterministic_for_history(tmp_path):
    engine,store=setup(tmp_path);engine.ingest(*packet(1,1),received_at=NOW)
    engine.ingest(*packet(2,0),received_at=NOW)
    assert store.history()[0]['contact_state']=='CLOSED'
    later=NOW+timedelta(seconds=30)
    assert engine.snapshot(later)['daily_durations'][0]['open_seconds']==0


def test_missing_contact_frame_followed_by_status_withdraws_old_state(tmp_path):
    engine,_=setup(tmp_path);engine.ingest(*packet(),received_at=NOW)
    at=NOW+timedelta(seconds=50)
    engine.ingest(*packet(3,at=at,data=bytes.fromhex('01755a')),received_at=at)
    assert engine.snapshot(at)['sensors'][0]['current_state']=='UNKNOWN'
    later=NOW+timedelta(seconds=100)
    engine.ingest(*packet(4,0,at=later),received_at=later)
    assert sum(row['open_seconds'] for row in engine.snapshot(later)['daily_durations'])==0


def test_initial_report_does_not_invent_a_physical_transition_time(tmp_path):
    engine,_=setup(tmp_path);engine.ingest(*packet(),received_at=NOW)
    sensor=engine.snapshot(NOW)['sensors'][0]
    assert sensor['last_transition_at'] is None
    assert sensor['last_observed_at']==NOW.isoformat()


def test_configured_simulator_uses_selected_identities_application_and_profiles():
    from services.lorawan.simulate import registry,events
    cfg=registry();cfg['application_id']='44444444-4444-4444-8444-444444444444';cfg['devices']=cfg['devices'][:3]
    for device,profile in zip(cfg['devices'],['dragino_lds02/v1','dragino_ds03a_lb/v1','milesight_ws301/v1']):
        device['decoder']=profile
    reg=Registry(cfg);engine=Engine(reg,Store.sqlite())
    for event in events(NOW,registered=reg):engine.ingest(event['raw'],event['topic'],received_at=event['received_at'])
    view=engine.snapshot(NOW+timedelta(seconds=2))
    assert len(view['sensors'])==3
    assert [s['current_state'] for s in view['sensors']]==['OPEN','CLOSED','OPEN']
