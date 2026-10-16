#!/usr/bin/env python3
"""Qualify two observational Items/links in owned isolation; no live apply path."""
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import argparse
import importlib.util
import json
import io
import tarfile
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import weather_health_age_items as age
spec = importlib.util.spec_from_file_location('age_fixture_base', ROOT/'scripts/qualify-weather-health-group.py')
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)
q.LABEL = 'hex.weather.health.age.qualification'
SOURCE_SHA = 'c1cba28d41c685d40eb61628d866b488365543d7f7bbff45a139a81aad3768e4'
TARGET = '/openhab/conf/items/'+age.SOURCE.name


class Fixture(q.Fixture):
    def wait_catalogs(self, *, inert=False):
        deadline = time.monotonic()+120
        while time.monotonic() < deadline:
            try:
                for path in ('/links', '/things', '/rules'):
                    rows = self.rest(path)
                    if path == '/things' and inert:
                        expected = {spec['channel'] for spec in age.ITEMS.values()}
                        age.require(len(rows) == 1 and rows[0]['UID'] == 'http:url:weatherHealth'
                                    and {c['uid'] for c in rows[0]['channels']} == expected,
                                    'inert fixture channel registry drift')
                    else:
                        age.require(rows == [], 'unexpected fixture catalog content')
                return
            except RuntimeError:
                time.sleep(2)
        raise RuntimeError('owned REST catalogs did not register')

    def seed_fixture_channels(self, record):
        self.info(self.oh)
        age.require(self.rest('/things') == [], 'fixture already contains Things')
        q.f.run(['docker', 'stop', '-t', '30', self.oh], timeout=60)
        age.require(not self.info(self.oh)['State']['Running'], 'owned JVM still running')
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w') as archive:
            body = q.b.encoded({'http:url:weatherHealth': record})
            member = tarfile.TarInfo('org.openhab.core.thing.Thing.json')
            member.size = len(body); member.mode = 0o600
            archive.addfile(member, io.BytesIO(body))
        # Docker's packaged client cannot read host private paths; use standard input.
        q.p.run(['docker', 'cp', '-', self.oh+':/openhab/userdata/jsondb'], output.getvalue())
        q.p.run(['docker', 'start', self.oh])
        self.wait_group(True)
        deadline = time.monotonic()+120
        expected = {spec['channel'] for spec in age.ITEMS.values()}
        while time.monotonic() < deadline:
            try:
                things = self.rest('/things')
                if len(things) == 1 and things[0]['UID'] == 'http:url:weatherHealth' and {c['uid'] for c in things[0]['channels']} == expected:
                    self.wait_catalogs(inert=True)
                    return
            except (RuntimeError, KeyError):
                pass
            time.sleep(2)
        raise RuntimeError('inert native channel registry did not recover')

    def mutation(self, method, path, body=None):
        age.allowed_mutation(method, path, body)
        self.info(self.oh)
        code, response = q.p.request(self.oh, ('Authorization: Bearer '+q.b.oh.token()+'\n').encode(),
                             path, method, None if body is None else json.dumps(body), 'application/json')
        self.rest_events.append({'at': datetime.now(timezone.utc).isoformat(),
            'method': method, 'path': path, 'code': code, 'response': response})
        age.require(code in (200, 201, 202, 204), 'owned definition mutation refused: HTTP '+str(code))

    def wait_absent(self):
        deadline = time.monotonic()+120
        while time.monotonic() < deadline:
            members = {i['name'] for i in self.rest('/items?metadata=.*')}
            links = self.rest('/links')
            if not members.intersection(age.ITEMS) and not any(l['itemName'] in age.ITEMS for l in links):
                return
            time.sleep(1)
        raise RuntimeError('selected Item/link withdrawal did not settle')

    def install_file(self):
        self.info(self.oh)
        age.require(sha256(age.SOURCE.read_bytes()).hexdigest() == SOURCE_SHA, 'age source drift')
        q.f.install_bytes(self.oh, '/openhab/conf/items', age.SOURCE.name, age.SOURCE.read_bytes())

    def withdraw_managed(self):
        for name in age.ITEMS:
            self.mutation('DELETE', age.link_path(name))
            self.mutation('DELETE', '/items/'+name+'/metadata/stateDescription')
            self.mutation('DELETE', '/items/'+name)
        self.wait_absent()

    def restore_managed(self):
        self.info(self.oh)
        found = q.p.run(['docker', 'exec', self.oh, 'sha256sum', TARGET]).decode().split()[0]
        age.require(found == SOURCE_SHA, 'owned watched-source drift before withdrawal')
        q.p.run(['docker', 'exec', self.oh, 'rm', TARGET])
        self.wait_absent()
        for name in age.ITEMS:
            self.mutation('PUT', '/items/'+name, age.original_item(name))
            self.mutation('PUT', '/items/'+name+'/metadata/stateDescription', age.METADATA)
            self.mutation('PUT', age.link_path(name), age.original_link(name))

    def checkpoint(self, directory, phase, histories, baseline=None, managed=True):
        deadline = time.monotonic()+240
        while time.monotonic() < deadline:
            try:
                group = self.rest('/items/'+q.g.GROUP+'?metadata=.*')
                q.g.validate_group(group, managed=True)
                rows = self.rest('/items?metadata=.*')
                age.require({i['name'] for i in rows} == q.g.MEMBERS|{q.g.GROUP}, 'fixture Item scope drift')
                members = {i['name']: i for i in rows if i['name'] != q.g.GROUP}
                links = self.rest('/links')
                age.require(len(links) == 2, 'fixture link scope drift')
                for name in age.ITEMS:
                    age.validate_item(members[name], name, managed=managed)
                    age.validate_links([l for l in links if l['itemName'] == name], name, managed=managed)
                age.require(all(i['state'] not in ('NULL', 'UNDEF') for i in members.values()), 'state not restored')
                if baseline is not None:
                    for name, row in members.items():
                        if name in age.ITEMS:
                            age.require(Decimal(row['state']) == Decimal(baseline[name]['state']), 'age state changed')
                        else:
                            age.require(row == baseline[name], 'unselected member definition/state drift')
                break
            except (RuntimeError, ValueError, KeyError):
                time.sleep(2)
        else:
            raise RuntimeError('age Item/link/metadata/provider recovery timed out')
        age.require(self.rest('/rules') == [], 'fixture contains executable rules')
        things = self.rest('/things')
        age.require(len(things) == 1, 'inert fixture Thing cardinality drift')
        age.validate_fixture_thing(things[0])
        age.require(self.sql("SELECT count(*) FROM public.items WHERE itemname='gWeatherHealth';").strip() == b'0',
                    'Group JDBC identity appeared')
        for name, row in histories.items():
            table = 'item'+str(row['id']).zfill(4)
            data = self.sql("SET TIME ZONE 'UTC'; COPY (SELECT time,value FROM public."+table+
                " WHERE time<='"+row['cutoff']+"' ORDER BY time,value) TO STDOUT WITH CSV;")
            age.require(len(data) == row['bytes'] and sha256(data).hexdigest() == row['sha256'], 'history prefix drift')
            age.require(self.sql("SELECT itemid FROM public.items WHERE itemname='"+name+"';").strip()
                        == str(row['id']).encode(), 'JDBC identity drift')
        value = {'at': datetime.now(timezone.utc).isoformat(), 'phase': phase, 'group': group,
            'members': members, 'links': links, 'container_host_pid': self.info(self.oh)['State']['Pid'],
            'all_six_history_prefixes_preserved': True, 'selected_provider_managed': managed,
            'production_writes': 0, 'scope': 'native_provider_history_not_binding_fetch',
            'auth_events': self.auth_events, 'rest_events': self.rest_events}
        q.save(directory, phase+'.json', value)
        print(json.dumps({'phase': phase, 'selected_items': 2, 'selected_links': 2,
                          'managed': managed, 'container_host_pid': value['container_host_pid']}), flush=True)
        return members


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-directory', required=True, type=Path)
    directory = parser.parse_args().report_directory
    age.require(directory.is_dir() and not directory.is_symlink()
                and directory.stat().st_mode & 0o777 == 0o700, 'private report directory required')
    age.require(sha256(age.SOURCE.read_bytes()).hexdigest() == SOURCE_SHA, 'candidate source drift')
    age.require(not Path('/etc/openhab/items/'+age.SOURCE.name).exists(), 'candidate already installed')
    links = q.b.oh.get('/links')
    for name in age.ITEMS:
        age.validate_item(q.b.oh.get('/items/'+name+'?metadata=.*'), name, managed=True)
        age.validate_links([l for l in links if l['itemName'] == name], name, managed=True)
    _, selected, metadata, users, histories, guard = q.capture(directory)
    q.save(directory, 'age-source.items', age.SOURCE.read_bytes())
    q.save(directory, 'age-original-links.json', [l for l in links if l['itemName'] in age.ITEMS])
    native = json.loads(Path('/var/lib/openhab/jsondb/org.openhab.core.thing.Thing.json').read_text())
    inert = age.inert_fixture_thing(native['http:url:weatherHealth'])
    q.save(directory, 'inert-channel-registry.json', {'http:url:weatherHealth': inert})
    fixture = Fixture()
    try:
        fixture.start(selected, metadata, users, histories, directory)
        fixture.wait_group(True)
        fixture.wait_catalogs()
        fixture.seed_fixture_channels(inert)
        for name in age.ITEMS:
            fixture.mutation('PUT', age.link_path(name), age.original_link(name))
        baseline = fixture.checkpoint(directory, 'managed-baseline', histories)
        fixture.withdraw_managed()
        fixture.install_file()
        fixture.checkpoint(directory, 'file-handoff', histories, baseline, managed=False)
        before = fixture.info(fixture.oh)['State']['Pid']
        q.f.run(['docker', 'restart', fixture.oh], timeout=90)
        fixture.checkpoint(directory, 'file-cold-restart', histories, baseline, managed=False)
        age.require(fixture.info(fixture.oh)['State']['Pid'] != before, 'owned cold process unchanged')
        fixture.restore_managed()
        fixture.checkpoint(directory, 'original-managed-rollback', histories, baseline)
        fixture.withdraw_managed()
        fixture.install_file()
        fixture.checkpoint(directory, 'final-file-handoff', histories, baseline, managed=False)
    except BaseException:
        if fixture.oh is not None:
            try:
                q.save(directory, 'failed-docker.log', q.f.run(['docker', 'logs', fixture.oh], check=False).stdout)
                result = q.f.run(['docker', 'exec', fixture.oh, 'cat', '/openhab/userdata/logs/openhab.log'], check=False)
                q.save(directory, 'failed-application.log', result.stdout+result.stderr)
                q.save(directory, 'failed-rest-events.json', fixture.rest_events)
            except Exception:
                pass
        raise
    finally:
        fixture.cleanup()
    age.require(q.live_guard() == guard, 'production definitions/sources/JVM drift')
    db = q.connect()
    try:
        with db:
            for name, row in histories.items():
                age.require(q.native_history(db, name, row['id'], cutoff=datetime.fromisoformat(row['cutoff'])) == row,
                            'production history prefix drift')
    finally:
        db.close()
    for name in age.ITEMS:
        age.validate_item(q.b.oh.get('/items/'+name+'?metadata=.*'), name, managed=True)
    q.g.validate_group(q.b.oh.get('/items/'+q.g.GROUP+'?metadata=.*'), managed=True)
    q.save(directory, 'qualification-proof.json', {'at': datetime.now(timezone.utc).isoformat(),
        'source_sha256': SOURCE_SHA, 'selected_items': age.ITEMS, 'member_histories': histories,
        'production_guard': guard, 'native_hot_round_trip': True, 'native_cold_restart': True,
        'production_writes': 0, 'production_restart_qualified': False,
        'production_items_still_managed': True, 'owned_fixture_removed': True,
        'binding_fetch_qualified': False, 'inert_fixture_channels_registered': True})
    print('qualification=passed production_writes=0 selected_production_providers=managed', flush=True)


if __name__ == '__main__':
    main()
