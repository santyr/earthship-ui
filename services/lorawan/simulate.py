"""Explicitly synthetic devices and deterministic fault/replay fixtures."""
import argparse
import base64
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid5, NAMESPACE_URL
from services.observations.contract import canonical, instant
from services.observations.registry import Registry

APP='11111111-1111-4111-8111-111111111111'


def registry():
    devices=[]
    for i in range(1,17):
        devices.append(dict(device_id=f'{i:016x}',sensor_id=f'opening_{i:02d}' if i<=15 else 'outdoor_gate',
            name=f'Commissioning opening {i:02d}' if i<=15 else 'Simulated outdoor gate',location='Unassigned',zone='unassigned',
            device_type=['window','skylight','door'][(i-1)%3] if i<=15 else 'gate',transport='lorawan',
            manufacturer='Milesight',model='WS301',decoder='milesight_ws301/v1',
            capabilities=['contact_state','battery','radio_health','tamper'],observation_types=['contact_state','tamper'],
            units={'contact_state':'state','tamper':'boolean'},enabled=True,hardware_epoch=str(uuid5(NAMESPACE_URL,f'synthetic-device-{i}')),
            radio_verified=False,state_stale_seconds=120,communication_stale_seconds=120,offline_seconds=300,
            battery_low_percent=20,battery_low_volts=2.7,security_policy='observe_only' if i==16 else None))
    for sid,kinds in [('environment_01',['air_temperature','relative_humidity']),('cistern_01',['water_depth']),
        ('flow_01',['water_counter','water_flow']),('planter_01',['soil_moisture_raw']),('leak_01',['leak'])]:
        from services.observations.contract import TYPES
        devices.append(dict(device_id='synthetic:'+sid,sensor_id=sid,name='Simulated '+sid,location='Unassigned',zone='unassigned',
            device_type='environmental',transport='simulation',decoder=None,capabilities=kinds,observation_types=kinds,
            units={k:TYPES[k][0] for k in kinds},hardware_epoch=str(uuid5(NAMESPACE_URL,sid)),radio_verified=False,
            state_stale_seconds=300,communication_stale_seconds=300,offline_seconds=900,battery_low_percent=20,battery_low_volts=2.7))
    return dict(schema='earthship-sensor-registry/v1',environment='simulation',application_id=APP,devices=devices,gateways=[dict(gateway_id='aaaaaaaaaaaaaaaa',name='Simulated gateway',offline_seconds=120)])


def uplink(device,*,counter,state,at,battery=90,tamper=False,port=None,data=None,address='01020304',application_id=APP):
    if data is None:
        if device['decoder']=='dragino_lds02/v1':
            voltage=2500 if battery<=20 else 2952
            data=((0x8000 if state else 0)|voltage).to_bytes(2,'big')+b'\x01'+(counter%0x1000000).to_bytes(3,'big')+b'\x00\x00\x00\x00'
        elif device['decoder']=='dragino_ds03a_lb/v1':
            data=bytes([state])+(counter%0x1000000).to_bytes(3,'big')+b'\x00\x00\x00'+int(at.timestamp()).to_bytes(4,'big')
        else:data=bytes([1,0x75,battery,3,0,state,4,0,int(tamper)])
    if port is None:port={'dragino_lds02/v1':10,'dragino_ds03a_lb/v1':2,'milesight_ws301/v1':85}[device['decoder']]
    identity=f'{device["device_id"]}:{counter}:{at.isoformat()}:{state}:{data!r}'
    body=dict(deduplicationId=str(uuid5(NAMESPACE_URL,identity)),time=at.isoformat(),
        deviceInfo=dict(devEui=device['device_id'],applicationId=application_id),devAddr=address,fCnt=counter,fPort=port,
        data=base64.b64encode(data).decode(),
        rxInfo=[dict(gatewayId='aaaaaaaaaaaaaaaa',rssi=-80,snr=7.5)])
    return canonical(body),f'application/{application_id}/device/{device["device_id"]}/event/up'


def events(at,*,faults=False,registered=None):
    registered=registered or Registry(registry());out=[]
    application_id=registered.config['application_id']
    for i,device in enumerate(registered.by_lorawan.values()):
        raw,topic=uplink(device,counter=1,state=i%2,at=at+timedelta(microseconds=1),application_id=application_id)
        join=json.loads(raw);join.pop('data');join.pop('fCnt');join.pop('fPort');join.pop('rxInfo')
        join['deduplicationId']=str(uuid5(NAMESPACE_URL,'join:'+device['device_id']+at.isoformat()));join['time']=at.isoformat()
        out.append(dict(raw=canonical(join),topic=topic.replace('/up','/join'),received_at=at.isoformat()))
        out.append(dict(raw=raw,topic=topic,received_at=(at+timedelta(microseconds=1)).isoformat()))
    for i,device in enumerate(registered.by_lorawan.values()):
        next_at=at+timedelta(seconds=1,microseconds=i*1000)
        raw,topic=uplink(device,counter=2,state=1-i%2,at=next_at,battery=15 if i==0 else 90,tamper=i==1,application_id=application_id)
        out.append(dict(raw=raw,topic=topic,received_at=next_at.isoformat()))
        if faults and i==0:
            out.append(dict(raw=raw,topic=topic,received_at=(next_at+timedelta(seconds=1)).isoformat()))
            old,topic=uplink(device,counter=1,state=0,at=at,application_id=application_id)
            out.append(dict(raw=old,topic=topic,received_at=(next_at+timedelta(seconds=2)).isoformat()))
        if faults and i==2:
            corrupt,topic=uplink(device,counter=3,state=1,at=at+timedelta(seconds=3),data=b'bad',application_id=application_id)
            out.append(dict(raw=corrupt,topic=topic,received_at=(at+timedelta(seconds=3)).isoformat()))
    return out


def environmental_events(at,registered=None):
    values={'air_temperature':22.4,'relative_humidity':48,'water_depth':1.3,'water_counter':1200,
            'water_flow':1.2,'soil_moisture_raw':450,'leak':False}
    for device in (registered or Registry(registry())).devices.values():
        if device['transport']!='simulation' or not device['enabled']:continue
        row=dict(schema='earthship-synthetic-event/v1',sensor_id=device['sensor_id'],observed_at=at.isoformat(),
            event_id=str(uuid5(NAMESPACE_URL,device['sensor_id']+at.isoformat())),
            readings=[dict(observation_type=k,value=values.get(k,False if device['units'][k]=='boolean' else 'CLOSED' if k=='contact_state' else 0),unit=device['units'][k]) for k in device['observation_types']])
        yield canonical(row),'earthship/simulation/event'


def main():
    from .runtime import mqtt_client,private_config
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--faults',action='store_true');parser.add_argument('--cycles',type=int,default=1);parser.add_argument('--registry')
    args=parser.parse_args();cfg=private_config(args.config)
    if cfg['environment']!='simulation':raise ValueError('simulator refuses production environment')
    registered=Registry.read(args.registry) if args.registry else Registry(registry())
    if registered.config['environment']!='simulation':raise ValueError('simulator refuses a production registry')
    client=mqtt_client(cfg,'simulator');client.connect(cfg['mqtt_host'],cfg['mqtt_port'],30);client.loop_start()
    try:
        for cycle in range(args.cycles):
            at=datetime.now(timezone.utc);batch=events(at,faults=args.faults,registered=registered)
            # Offset counters across successive scenarios, while keeping fault replay deterministic.
            for event in batch:
                target=instant(event['received_at']);remaining=(target-datetime.now(timezone.utc)).total_seconds()
                if remaining>0:time.sleep(remaining)
                raw=json.loads(event['raw'])
                if 'fCnt' in raw:raw['fCnt']+=cycle*10
                client.publish(event['topic'],canonical(raw),qos=1,retain=False).wait_for_publish(timeout=5)
            client.publish('us915_1/gateway/aaaaaaaaaaaaaaaa/event/stats',canonical(dict(synthetic=True,at=datetime.now(timezone.utc).isoformat())),qos=1).wait_for_publish(timeout=5)
            for raw,topic in environmental_events(datetime.now(timezone.utc),registered=registered):
                client.publish(topic,raw,qos=1).wait_for_publish(timeout=5)
            if cycle+1<args.cycles:time.sleep(5)
    finally:client.disconnect();client.loop_stop()
    print('Published explicit synthetic application events; no radio path exercised.')


if __name__=='__main__':main()
