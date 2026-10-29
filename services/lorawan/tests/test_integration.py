"""Opt-in tests against only compose.test.yaml's loopback endpoints."""
import json
import os
import time
import urllib.request
from datetime import datetime,timedelta,timezone
import pytest
from services.lorawan.tests.integration_probe import item,wait_for,transition,publisher
from services.lorawan.simulate import events,environmental_events
from services.observations.contract import canonical
from services.lorawan.tests.stack_ownership import assert_owned_stack, SERVICES, run_compose, owned_urlopen, guarded_mqtt_client

pytestmark=pytest.mark.skipif(os.environ.get('SENSOR_INTEGRATION')!='1',reason='isolated container qualification is explicitly opt-in')


@pytest.fixture(scope='module',autouse=True)
def ready_software_path():
    assert_owned_stack(require_running=SERVICES)
    # HTTP readiness precedes asynchronous file-provider/addon registration on cold boot.
    wait_for(lambda:item('Earthship_Sensor_Service')=='online' and
        json.loads(item('Earthship_Sensor_View_JSON'))['schema']=='earthship-sensor-view/v1',seconds=180)
    client=publisher()
    try:
        at=datetime.now(timezone.utc)
        for event in events(at):
            delay=datetime.fromisoformat(event['received_at']).timestamp()-time.time()
            if delay>0:time.sleep(delay)
            client.publish(event['topic'],event['raw'],qos=1).wait_for_publish(timeout=5)
        wait_for(lambda:all(item(f'Sensor_opening_{i:02d}_Contact') in ('OPEN','CLOSED') for i in range(1,16)),seconds=120)
    finally:client.disconnect();client.loop_stop()


def test_fifteen_devices_contact_diagnostics_and_history():
    client=publisher()
    try:
        at=datetime.now(timezone.utc)
        batch=events(at,faults=True)
        for event in batch:
            delay=datetime.fromisoformat(event['received_at']).timestamp()-time.time()
            if delay>0:time.sleep(delay)
            client.publish(event['topic'],event['raw'],qos=1).wait_for_publish(timeout=5)
        for raw,topic in environmental_events(datetime.now(timezone.utc)):
            client.publish(topic,raw,qos=1).wait_for_publish(timeout=5)
        view=wait_for(lambda: (v if len(v.get('environmental',[]))>=7 and v['sensors'][2]['quality']=='invalid_payload' and all(datetime.fromisoformat(e['received_at'])>=at for e in v['environmental']) else None) if (v:=json.loads(item('Earthship_Sensor_View_JSON'))) else None)
        assert len(view['sensors'])==16
        assert all(s['accepted_uplinks']>=2 for s in view['sensors'])
        assert item('Sensor_opening_01_Contact')=='OPEN'
        assert item('Sensor_opening_01_BatteryPercent')=='15'
        assert view['sensors'][2]['current_state']=='UNKNOWN'
        assert view['sensors'][2]['contact_state'] is not None
        assert len(view['recent_events'])>=15
        assert view['environment']=='simulation'
        assert len(view['normalized_observations'])>=15
    finally:client.disconnect();client.loop_stop()


def test_contact_latency_and_persistent_restart():
    assert transition(0)<5000
    assert transition(1)<5000
    before=json.loads(item('Earthship_Sensor_View_JSON'))['sensors'][0]['frame_counter']
    run_compose(['restart','ingest'],check=True,capture_output=True,timeout=30)
    wait_for(lambda:item('Earthship_Sensor_Service')=='online')
    wait_for(lambda:json.loads(item('Earthship_Sensor_View_JSON'))['sensors'][0]['frame_counter']==before)
    assert transition(0)<5000


def test_runtime_cannot_rewrite_raw_journal():
    code="from services.lorawan.runtime import private_config;from services.lorawan.storage import Store;s=Store.postgres(private_config('/run/private/ingest.json')['database_dsn']);s.execute(\"UPDATE raw_events SET decision='rewritten'\")"
    result=run_compose(['exec','-T','ingest','python','-c',code],capture_output=True,text=True,timeout=15)
    assert result.returncode!=0 and 'permission denied' in result.stderr.lower()


def test_chirpstack_database_migrations_and_login():
    result=run_compose(['exec','-T','postgres','psql','-U','postgres','-d','chirpstack','-At','-c',"select count(*) from information_schema.tables where table_schema='public'"],capture_output=True,text=True,check=True,timeout=15)
    assert int(result.stdout.strip())>=20
    import struct
    payload=b'\x0a\x05admin\x12\x05admin'
    frame=b'\x00'+struct.pack('>I',len(payload))+payload
    request=urllib.request.Request('http://127.0.0.1:28085/api.InternalService/Login',data=frame,headers={'Content-Type':'application/grpc-web+proto','x-grpc-web':'1'})
    response=owned_urlopen(request,timeout=5).read()
    valid_login=b'grpc-status:0' in response and len(response)>100
    assert valid_login # Default login belongs only to the disposable instance.


def test_actual_simulator_command_runs_independent_devices():
    result=run_compose(['--profile','simulation','run','--rm','simulator'],capture_output=True,text=True,timeout=30)
    assert result.returncode==0, 'the actual simulator command must complete'
    view=wait_for(lambda: (v if v['sensors'][0]['frame_counter']==2 and v['sensors'][2]['quality']=='invalid_payload' else None) if (v:=json.loads(item('Earthship_Sensor_View_JSON'))) else None)
    assert len(view['sensors'])==16


def test_retained_live_input_does_not_change_contact():
    from services.lorawan.simulate import uplink,registry
    from services.observations.registry import Registry
    transition(1);view=json.loads(item('Earthship_Sensor_View_JSON'));sensor=view['sensors'][0]
    client=publisher()
    try:
        raw,topic=uplink(Registry(registry()).devices['opening_01'],counter=sensor['frame_counter']+1,state=0,at=datetime.now(timezone.utc))
        client.publish(topic,raw,qos=1,retain=True).wait_for_publish(timeout=5)
        time.sleep(.5)
        assert item('Sensor_opening_01_Contact')=='OPEN'
        client.publish(topic,b'',qos=1,retain=True).wait_for_publish(timeout=5) # Remove only the test retained input.
    finally:client.disconnect();client.loop_stop()


def test_message_queued_during_ingestion_outage_recovers():
    from services.lorawan.simulate import uplink,registry
    from services.observations.registry import Registry
    transition(1);sensor=json.loads(item('Earthship_Sensor_View_JSON'))['sensors'][0]
    client=publisher()
    try:
        run_compose(['stop','ingest'],check=True,capture_output=True,timeout=30)
        raw,topic=uplink(Registry(registry()).devices['opening_01'],counter=sensor['frame_counter']+1,state=0,at=datetime.now(timezone.utc))
        client.publish(topic,raw,qos=1).wait_for_publish(timeout=5)
    finally:
        run_compose(['start','ingest'],check=True,capture_output=True,timeout=30)
        client.disconnect();client.loop_stop()
    wait_for(lambda:item('Sensor_opening_01_Contact')=='CLOSED',seconds=30)


def test_observer_cannot_publish_raw_uplinks():
    from services.lorawan.runtime import private_config
    config=private_config('.superpowers/lorawan-private/observer.json');config.update(mqtt_host='127.0.0.1',mqtt_port=18884)
    client=guarded_mqtt_client(config,'observer-acl-test');reasons=[]
    client.on_publish=lambda client,userdata,mid,reason,properties:reasons.append(reason.is_failure)
    client.connect('127.0.0.1',18884,30);client.loop_start()
    try:
        client.publish('application/11111111-1111-4111-8111-111111111111/device/0000000000000001/event/up',b'{}',qos=1).wait_for_publish(timeout=5)
        wait_for(lambda:len(reasons)>0)
        assert reasons==[True]
    finally:client.disconnect();client.loop_stop()


def test_backup_restores_sensor_history_into_disposable_database(tmp_path):
    dump=run_compose(['exec','-T','postgres','pg_dump','-U','postgres','-Fc','sensors_test'],capture_output=True,check=True,timeout=30).stdout
    assert len(dump)>1000
    run_compose(['exec','-T','postgres','createdb','-U','postgres','sensors_restore_test'],check=True,capture_output=True,timeout=15)
    try:
        run_compose(['exec','-T','postgres','pg_restore','-U','postgres','-d','sensors_restore_test'],input=dump,check=True,capture_output=True,timeout=30)
        counts=[]
        for db in ['sensors_test','sensors_restore_test']:
            result=run_compose(['exec','-T','postgres','psql','-U','postgres','-d',db,'-At','-c','select count(*) from earthship_observations.observations'],capture_output=True,text=True,check=True,timeout=10)
            counts.append(int(result.stdout.strip()))
        assert counts[1]>0 and counts[1]<=counts[0]
    finally:run_compose(['exec','-T','postgres','dropdb','-U','postgres','sensors_restore_test'],check=True,capture_output=True,timeout=15)


def test_broker_restart_recovers_and_source_health_resumes():
    transition(1)
    run_compose(['restart','mqtt'],check=True,capture_output=True,timeout=30)
    wait_for(lambda:item('Earthship_Sensor_Service')=='online',seconds=30)
    assert transition(0)<5000


def test_unacknowledged_packet_recovers_after_database_outage():
    from services.lorawan.simulate import uplink,registry
    from services.observations.registry import Registry
    transition(1);sensor=json.loads(item('Earthship_Sensor_View_JSON'))['sensors'][0];client=publisher()
    try:
        run_compose(['stop','postgres'],check=True,capture_output=True,timeout=30)
        raw,topic=uplink(Registry(registry()).devices['opening_01'],counter=sensor['frame_counter']+1,state=0,at=datetime.now(timezone.utc))
        client.publish(topic,raw,qos=1).wait_for_publish(timeout=5)
        time.sleep(2)
    finally:
        run_compose(['start','postgres'],check=True,capture_output=True,timeout=30)
        client.disconnect();client.loop_stop()
    wait_for(lambda:item('Sensor_opening_01_Contact')=='CLOSED',seconds=45)
