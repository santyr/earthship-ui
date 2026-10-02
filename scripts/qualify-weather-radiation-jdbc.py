#!/usr/bin/env python3
"""Real file-owned HTTP/JDBC and restart tests in disconnected containers only."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
from weather_radiation_evidence import RadiationPolicy, invalid
from weather_radiation_receiver import RadiationCollector

def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

jdbc = load('radiation_jdbc_fixture', 'qualify-persistence-jdbc.py')
aqi = load('radiation_rest_fixture', 'qualify-openmeteo-aqi-jdbc.py')
ITEM = 'Weather_Radiation_Evidence_JSON'
THING = 'http:url:weatherRadiationEvidence'
ITEM_SOURCE = ROOT / 'openhab/file-config/items/weather-radiation-evidence.items'
THING_SOURCE = ROOT / 'openhab/file-config/things/weather-radiation-evidence.things'


def install(container, path, body):
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w') as tar:
        entry = tarfile.TarInfo(path)
        entry.mode, entry.size = 0o644, len(body)
        tar.addfile(entry, io.BytesIO(body))
    jdbc.run(['docker', 'exec', '-i', container, 'tar', '-xf', '-', '-C', '/'],
             archive.getvalue())


def wait(check, label, seconds=100):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except (RuntimeError, ValueError, KeyError):
            pass
        time.sleep(2)
    raise AssertionError('isolated radiation qualification timeout: ' + label)


def snapshot(lux=12670):
    at = datetime.now(timezone.utc)
    collector = RadiationCollector(RadiationPolicy(206), clock=lambda: at)
    collector.observe({'model': 'Fineoffset-WH65B', 'id': 206,
                       'light_lux': lux, 'solarradiation': round(min(lux/126.7, 1200), 2),
                       'radio_decode_utc': at.strftime('%Y-%m-%d %H:%M:%S')})
    return collector.snapshot()


class RadiationDatabase(jdbc.Database):
    def __enter__(self):
        # Check fixture code before allocating a database.
        self.http_probe = jdbc.compile_probe('HexRadiationHttpProbe', ['org.osgi.framework'])
        self.http_binding = (jdbc.CACHE / 'org/openhab/addons/bundles/'
                             'org.openhab.binding.http/5.2.1/'
                             'org.openhab.binding.http-5.2.1.jar').read_bytes()
        self.radiation_checked = False
        return super().__enter__()

    def stage(self, container):
        super().stage(container)
        for path, body in [
            ('openhab/conf/items/weather-radiation-evidence.items', ITEM_SOURCE.read_bytes()),
            ('openhab/conf/things/weather-radiation-evidence.things', THING_SOURCE.read_bytes()),
            ('openhab/addons/radiation-http-binding.jar', self.http_binding),
            ('openhab/addons/radiation-http-fixture.jar', self.http_probe),
            ('tmp/radiation-http-response', b'503\n{}'),
        ]:
            install(container, path, body)

    def rows(self, container, header):
        code, body = aqi.request(container, header,
                                 '/persistence/items/'+ITEM+'?serviceId=jdbc')
        return json.loads(body).get('data', []) if code == 200 else []

    def current(self, container, header):
        code, body = aqi.request(container, header, '/items/'+ITEM+'/state')
        return body if code == 200 else None

    def write_source(self, container, payload, status=200):
        body = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        install(container, 'tmp/radiation-http-response',
                (str(status)+'\n'+body).encode())
        return body

    def received(self, container, header, body):
        if self.current(container, header) != body:
            return False
        rows = self.rows(container, header)
        return rows if rows and rows[-1]['state'] == body else False

    def definitions(self, container, header):
        code, raw = aqi.request(container, header, '/items/'+ITEM)
        if code != 200:
            return False
        item = json.loads(raw)
        code, raw = aqi.request(container, header, '/things/'+THING)
        if code != 200:
            return False
        thing = json.loads(raw)
        channel = next(c for c in thing['channels'] if c['uid']==THING+':snapshot')
        code, raw = aqi.request(container, header, '/links')
        if code != 200:
            return False
        links = [v for v in json.loads(raw) if v['itemName']==ITEM]
        return (item['editable'] is False and item['type']=='String'
                and thing['editable'] is False
                and thing['configuration']['baseURL']=='http://127.0.0.1:5000/radiation_evidence'
                and thing['configuration']['stateMethod']=='GET'
                and thing['configuration']['refresh']==30
                and channel['configuration']['mode']=='READONLY'
                and len(links)==1 and links[0]['editable'] is False
                and links[0]['channelUID']==THING+':snapshot')

    def checkpoint(self, container, header, label):
        super().checkpoint(container, header, label)
        if self.radiation_checked:
            return
        wait(lambda: self.definitions(container, header), 'exact file definitions')
        original = snapshot()
        body = self.write_source(container, original)
        prefix = wait(lambda: self.received(container, header, body), 'original receipt JDBC')
        time.sleep(34)  # At least one unchanged 30-second poll, no everyUpdate renewal.
        assert self.rows(container, header)==prefix
        assert json.loads(self.current(container, header))['record']['receivedAt']==original['record']['receivedAt']
        print('original_receipt_and_unchanged_poll_history=verified', flush=True)

        expired = {**original, 'record': invalid(original['record'], 'expired')}
        invalid_body = self.write_source(container, expired)
        wait(lambda: self.received(container, header, invalid_body), 'expiry barrier JDBC')
        # Restore the actual producer's fresh source; no synthetic Item PUT.
        body = self.write_source(container, snapshot(25340))
        prefix = wait(lambda: self.received(container, header, body), 'fresh source recovery')
        self.write_source(container, {}, status=503)
        # HTTP binding need not mark the Thing OFFLINE for a non-200 reply.
        # Prove the real binding fetched our error response, then assess the
        # receipt/history boundary rather than assert framework status policy.
        wait(lambda: jdbc.run(['docker','exec',container,'cat',
                              '/tmp/radiation-http-last-status']).strip()==b'503',
             'binding received HTTP source fault')
        time.sleep(3)
        assert self.current(container, header)==body
        assert self.rows(container, header)==prefix  # Held state has unchanged source expiry.
        body = self.write_source(container, snapshot(38010))
        prefix = wait(lambda: self.received(container, header, body), 'HTTP source recovery')
        print('expiry_barrier_http_fault_and_fresh_recovery=verified', flush=True)

        path = '/openhab/conf/items/weather-radiation-evidence.items'
        jdbc.run(['docker','exec',container,'mv',path,'/tmp/radiation.items.parked'])
        wait(lambda: aqi.request(container, header, '/items/'+ITEM)[0]==404,
             'file Item withdrawal')
        code, links = aqi.request(container, header, '/links')
        assert code==200 and not any(v['itemName']==ITEM for v in json.loads(links))
        jdbc.run(['docker','exec',container,'mv','/tmp/radiation.items.parked',path])
        wait(lambda: self.definitions(container, header), 'file Item/link recovery')
        wait(lambda: self.current(container, header)==body, 'preserved original receipt recovery')
        assert self.rows(container, header)[:len(prefix)]==prefix
        self.radiation_prefix=self.rows(container, header)
        self.radiation_body=body
        self.radiation_checked=True
        print('file_item_link_recovery_and_history_prefix=verified', flush=True)

    def restart(self, container, header):
        super().restart(container, header)
        wait(lambda: self.definitions(container, header), 'post-restart definitions')
        wait(lambda: self.current(container, header)==self.radiation_body,
             'restart restores exact old source receipt, not fresh timestamps')
        assert self.rows(container, header)[:len(self.radiation_prefix)]==self.radiation_prefix
        body=self.write_source(container, snapshot(50680))
        wait(lambda: self.received(container, header, body), 'new post-restart source receipt')
        assert self.rows(container, header)[:len(self.radiation_prefix)]==self.radiation_prefix
        print('radiation_jvm_restart_exact_history_and_new_source=verified', flush=True)


def main():
    assert ITEM_SOURCE.is_file() and THING_SOURCE.is_file(), 'radiation collection definitions missing'
    with RadiationDatabase() as database:
        jdbc.provider.main(database)


if __name__=='__main__':
    main()
