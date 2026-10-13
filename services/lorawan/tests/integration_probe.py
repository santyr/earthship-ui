"""Disposable stack probe and browser-test stimulus. Never targets production."""
import argparse
import json
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from services.lorawan.runtime import private_config,mqtt_client
from services.lorawan.simulate import uplink,registry
from services.observations.registry import Registry

OPENHAB='http://127.0.0.1:18084'


def item(name):
    return urllib.request.urlopen(OPENHAB+'/rest/items/'+name+'/state',timeout=5).read().decode()


def wait_for(predicate,seconds=20):
    start=time.monotonic()
    while time.monotonic()-start<seconds:
        try:
            value=predicate()
            if value:return value
        except (OSError,ValueError,KeyError):pass
        time.sleep(.1)
    raise AssertionError('isolated integration deadline exceeded')


def publisher():
    config=private_config('deploy/lorawan/private/simulator.json')
    if config['environment']!='simulation':raise ValueError('integration probe refuses production')
    config.update(mqtt_host='127.0.0.1',mqtt_port=18884)
    client=mqtt_client(config,'probe-'+uuid4().hex[:8]);client.connect(config['mqtt_host'],config['mqtt_port'],30);client.loop_start()
    return client


def transition(state,sid='opening_01'):
    client=publisher()
    try:
        view=json.loads(item('Earthship_Sensor_View_JSON'))
        sensor=next(s for s in view['sensors'] if s['sensor_id']==sid)
        device=Registry(registry()).devices[sid]
        at=datetime.now(timezone.utc)
        raw,topic=uplink(device,counter=(sensor['frame_counter'] or 0)+1,state=state,at=at)
        started=time.monotonic();client.publish(topic,raw,qos=1).wait_for_publish(timeout=5)
        expected='OPEN' if state else 'CLOSED'
        wait_for(lambda:item('Sensor_'+sid+'_Contact')==expected and any(s['sensor_id']==sid and s['current_state']==expected and s['frame_counter']==sensor['frame_counter']+1 for s in json.loads(item('Earthship_Sensor_View_JSON'))['sensors']))
        return (time.monotonic()-started)*1000
    finally:client.disconnect();client.loop_stop()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state',type=int,choices=[0,1],required=True);args=parser.parse_args()
    print(json.dumps(dict(contact_item_ms=round(transition(args.state),2))))


if __name__=='__main__':main()
