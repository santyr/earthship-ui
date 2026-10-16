"""Authenticated MQTT service, single writer, commit-before-publish, local health."""
import argparse
import base64
import json
import logging
import os
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from services.observations.contract import canonical,digest,instant,strict_json,normalize
from services.observations.registry import Registry
from .engine import Engine
from .storage import Store

LOG=logging.getLogger('earthship.observations')


def private_config(path):
    source=Path(path)
    if source.stat().st_mode&0o077:raise ValueError('private configuration requires mode 0600')
    config=strict_json(source.read_bytes())
    required={'environment','mqtt_host','mqtt_port','mqtt_username','mqtt_password','database_dsn'}
    if not required<=set(config) or config['environment'] not in ('simulation','production'):
        raise ValueError('private service configuration required')
    return config


def mqtt_client(config,identity='ingest'):
    import paho.mqtt.client as mqtt
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='earthship-'+identity,protocol=mqtt.MQTTv5,manual_ack=True)
    client.username_pw_set(config['mqtt_username'],config['mqtt_password'])
    if config.get('mqtt_ca'):
        client.tls_set(ca_certs=config['mqtt_ca'])
    elif config['environment']=='production' and config['mqtt_host'] not in ('localhost','127.0.0.1','::1'):
        raise ValueError('production MQTT requires TLS outside loopback')
    client.reconnect_delay_set(1,30);client.max_queued_messages_set(256)
    return client


def synthetic_ingest(engine,raw,topic,received_at,retained=False):
    if engine.registry.config['environment']!='simulation' or topic!='earthship/simulation/event' or retained:
        return 'refused_synthetic'
    row=strict_json(raw);device=engine.registry.devices[row['sensor_id']]
    if row['schema']!='earthship-synthetic-event/v1' or device['transport']!='simulation':raise ValueError('explicit synthetic source required')
    at=instant(row['observed_at']);received_at=instant(received_at)
    if at>received_at:raise ValueError('future synthetic source')
    from uuid import UUID
    event_id=str(UUID(row['event_id']));points=[]
    if not isinstance(row['readings'],list) or not 1<=len(row['readings'])<=32:raise ValueError('bounded synthetic readings required')
    for reading in row['readings']:
        point=normalize(sensor=device,kind=reading['observation_type'],value=reading['value'],unit=reading['unit'],
            observed_at=at,received_at=received_at,valid_until=at+timedelta(seconds=device['state_stale_seconds']),
            source_identity='synthetic/'+device['device_id'],raw_sha256=digest(raw),source_epoch=device['hardware_epoch'],
            timestamp_basis='device_clock',synthetic=True)
        point.update(hardware_epoch=device['hardware_epoch'],event_type='measurement',contact_state=None,historical=False)
        points.append(point)
    raw_id=str(uuid4())
    with engine.store.transaction():
        if engine.store.seen('synthetic:'+event_id) is not None:return 'duplicate'
        engine.store.execute('INSERT INTO raw_events(id,received_at,topic,raw_sha256,raw_base64,decision) VALUES(?,?,?,?,?,?)',
            (raw_id,received_at.isoformat(),topic,digest(raw),base64.b64encode(raw).decode(),'synthetic'))
        for point in points:engine.store.observation(raw_id,point)
        engine.store.mark_seen('synthetic:'+event_id,digest(raw))
    return 'synthetic'


def publish_view(client,engine,now,metrics):
    view=engine.snapshot(now)
    with engine.store.transaction():
        latest={}
        for point in engine.store.history(limit=500):
            if point.get('schema')!='earthship-observation/v1':continue
            device=engine.registry.devices.get(point['sensor_id'])
            if not device or not device['enabled'] or device['hardware_epoch']!=point['provenance']['hardware_epoch'] or point['observation_type'] not in device['observation_types']:continue
            key=(point['sensor_id'],point['observation_type'])
            if key not in latest:
                latest[key]={**point,'name':engine.registry.devices[point['sensor_id']]['name'],
                    'zone':engine.registry.devices[point['sensor_id']]['zone'],'location':engine.registry.devices[point['sensor_id']]['location'],'current_quality':point['quality'] if now<instant(point['valid_until']) else 'stale'}
    view['environmental']=list(latest.values())
    with engine.store.transaction():
        normalized={}
        for row in engine.store.history(limit=5000):
            for point in row.get('measurements',[]):
                device=engine.registry.devices.get(point['sensor_id'])
                if not device or not device['enabled'] or device['hardware_epoch']!=point['provenance']['hardware_epoch'] or point['observation_type'] not in device['observation_types']:continue
                key=point['sensor_id']+':'+point['observation_type']
                if key not in normalized:normalized[key]=point
    current={s['sensor_id']:s for s in view['sensors']}
    view['normalized_observations']={k:p for k,p in normalized.items() if current.get(p['sensor_id'],{}).get('valid')}
    from .health import gateway_health
    with engine.store.transaction():gateways=gateway_health(engine,now)
    view['gateways']=gateways
    view['operations']={**metrics,'mqtt_connected':client.is_connected(),
        'gateway':gateways[0]['health'].lower() if gateways else 'not_configured','registered_devices':len(engine.registry.devices)}
    body=canonical(view)
    if len(body)>1048576:raise ValueError('bounded sensor view exceeded')
    client.publish('earthship/sensors/v1/view',body,qos=1,retain=True)
    for sensor in view['sensors']:
        projection={**sensor,'available':sensor['health']=='ONLINE','battery_condition':sensor['battery']['condition'],
            'battery_percent':sensor['battery'].get('percent','UNDEF'),'battery_volts':sensor['battery'].get('volts','UNDEF')}
        for key,value in projection.items():
            if value is None:projection[key]='UNDEF'
        client.publish(f'earthship/sensors/v1/{sensor["sensor_id"]}/state',canonical(projection),qos=1,retain=True)
    return view


def run(config,registry,health_path):
    if registry.config['environment']!=config['environment']:raise ValueError('registry/service environment mismatch')
    store=Store.postgres(config['database_dsn']) if not config['database_dsn'].startswith('sqlite:') else Store.sqlite(config['database_dsn'][7:])
    with store.transaction():
        binding=store.execute("SELECT value FROM metadata WHERE id='environment'").fetchone()
        if binding is None and not store.postgres and config['environment']=='simulation':
            store.execute("INSERT INTO metadata(id,value) VALUES('environment','simulation')")
        elif binding is None or binding[0]!=config['environment']:
            raise ValueError('journal environment must match registry and service')
    if store.postgres:
        if not store.execute('SELECT pg_try_advisory_lock(654907231)').fetchone()[0]:
            raise ValueError('single observation writer already active')
        store.connection.commit()
    engine=Engine(registry,store);client=mqtt_client(config)
    metrics=dict(chirpstack='not_probed',accepted=0,rejected=0,decode_failures=0,integration_failures=0,last_event_at=None,processing_ms=0)
    client.will_set('earthship/sensors/v1/service','offline',qos=1,retain=True)
    def connected(client,userdata,flags,reason,properties):
        if reason.is_failure:LOG.error('mqtt connection rejected');return
        import paho.mqtt.client as mqtt
        options=mqtt.SubscribeOptions(qos=1,retainAsPublished=True)
        client.subscribe('us915_1/gateway/+/event/stats',options=options)
        client.subscribe(f'application/{registry.config["application_id"]}/device/+/event/+',options=options)
        if config['environment']=='simulation':client.subscribe('earthship/simulation/event',options=options)
        client.publish('earthship/sensors/v1/service','online',qos=1,retain=True)
        LOG.info('mqtt connected; subscriptions restored')
    def message(client,userdata,msg):
        start=time.monotonic();now=datetime.now(timezone.utc)
        try:
            if len(msg.payload)>65536:decision=engine.ingest(msg.payload,msg.topic,received_at=now,retained=msg.retain)
            elif msg.topic.startswith('us915_1/gateway/'):
                decision=engine.gateway_activity(msg.payload,msg.topic,now,msg.retain)
            elif msg.topic=='earthship/simulation/event':decision=synthetic_ingest(engine,msg.payload,msg.topic,now,msg.retain)
            else:decision=engine.ingest(msg.payload,msg.topic,received_at=now,retained=msg.retain)
            metrics['accepted' if decision in ('accepted','joined','synthetic') else 'rejected']+=1
            metrics['decode_failures']+=int(decision=='invalid_payload')
            metrics['last_event_at']=now.isoformat()
            metrics['processing_ms']=round((time.monotonic()-start)*1000,3)
            client.ack(msg.mid,msg.qos)
            if decision in ('accepted','joined','synthetic','invalid_payload','counter_conflict','counter_regression'):
                publish_view(client,engine,now,metrics)
            LOG.info('event result=%s processing_ms=%.3f',decision,metrics['processing_ms'])
        except (ValueError,KeyError,TypeError,UnicodeError):
            metrics['rejected']+=1;client.ack(msg.mid,msg.qos);LOG.warning('invalid input refused')
        except Exception:
            metrics['integration_failures']+=1
            LOG.error('journal unavailable; event not acknowledged')
            # Termination makes the service restart with a clean DB connection.
            raise
    client.on_connect=connected;client.on_message=message
    stop=False
    def terminate(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,terminate);signal.signal(signal.SIGINT,terminate)
    from paho.mqtt.properties import Properties
    from paho.mqtt.packettypes import PacketTypes
    properties=Properties(PacketTypes.CONNECT);properties.SessionExpiryInterval=86400
    client.connect(config['mqtt_host'],config['mqtt_port'],30,clean_start=False,properties=properties)
    last_sweep=0
    try:
        while not stop:
            rc=client.loop(timeout=1)
            if rc!=0:
                time.sleep(1)
                try:client.reconnect()
                except OSError:continue
            now=datetime.now(timezone.utc)
            if time.monotonic()-last_sweep>=15:
                from .health import chirpstack_probe
                metrics['chirpstack']=chirpstack_probe(config.get('chirpstack_probe_url'))
                publish_view(client,engine,now,metrics);last_sweep=time.monotonic()
                health=Path(health_path);health.parent.mkdir(parents=True,exist_ok=True)
                health.write_bytes(canonical(dict(at=now.isoformat(),mqtt_connected=client.is_connected())))
    finally:
        if client.is_connected():
            client.publish('earthship/sensors/v1/service','offline',qos=1,retain=True)
            client.loop(timeout=0.2);client.disconnect()
        store.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--registry',required=True);parser.add_argument('--health',default='/tmp/sensor-health.json')
    args=parser.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    try:run(private_config(args.config),Registry.read(args.registry),args.health)
    except Exception as error:
        LOG.error('service stopped error_type=%s',type(error).__name__)
        raise SystemExit(1) from None


if __name__=='__main__':main()
