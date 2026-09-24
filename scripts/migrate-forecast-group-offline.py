#!/usr/bin/env python3
"""Attended, cold OpenHAB handoff of gForecast to its file definition.

--check is read-only. --apply requires the daily forecast Items to be verified,
backs up the stopped JSONDB privately, and preserves all ten Group references.
Never REST-delete this Group: OpenHAB removes its member references on delete.
"""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('forecast_transfer',
    ROOT / 'scripts/migrate-openmeteo-forecast-temperature-items.py')
transfer = module_from_spec(spec)
spec.loader.exec_module(transfer)
sanity_spec = spec_from_file_location('openhab_sanity',
    ROOT / 'openhab/scripts/openhab_sanity_check.py')
sanity = module_from_spec(sanity_spec)
sanity_spec.loader.exec_module(sanity)

SOURCE = ROOT / 'openhab/file-config/items/forecast-group.items'
SOURCE_SHA256 = 'a9816041107155acbaa7683208a32d82a0d31a5698e53e4400209b1cd6146506'
TARGET = Path('/etc/openhab/items/forecast-group.items')
REGISTRY = Path('/var/lib/openhab/jsondb/org.openhab.core.items.Item.json')
BACKUP_ROOT = Path('/home/sat/.local/state/openhab-config-migration')
MANIFEST = ROOT / 'openhab/file-config/ownership.json'
GROUP = 'gForecast'
PUMP_ITEMS = ('SouthOutlet_Outlet2_Switch', 'East_Bed_Socket_Outlet_2_Power')
SAFETY_RULES = ('hex_bms_comms_watchdog', 'hex_schneider_safety',
                'hex_southoutlet_cycle')
MEMBERS = frozenset({
    'Forecast_Temp', 'Forecast_Daily_High', 'Forecast_Daily_Low',
    'Forecast_Cloudiness', 'Forecast_Radiation', 'Forecast_PrecipProb',
    'Forecast_Daily_PrecipSum', 'Forecast_Daily_PrecipProbMax',
    'Forecast_Daily_WeatherCode', 'Forecast_Daily_UVIndex',
})
DAILY = frozenset({
    'Forecast_Daily_PrecipSum', 'Forecast_Daily_PrecipProbMax',
    'Forecast_Daily_WeatherCode', 'Forecast_Daily_UVIndex',
})
RELEASE_READY = True  # Attended window, physical pumps OFF, and protected-control review verified 2026-09-24.


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def command(*args, timeout=90):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    require(result.returncode == 0,
            'command failed (' + str(result.returncode) + '): ' + ' '.join(args[:3]))
    return result.stdout


def active():
    return subprocess.run(['systemctl', 'is-active', '--quiet', 'openhab.service'],
                          capture_output=True, timeout=10).returncode == 0


def private_file(directory, name, body):
    target = directory / name
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def registered_members():
    items = transfer.oh.get('/items?recursive=false')
    return {row['name'] for row in items if GROUP in row.get('groupNames', [])}


def member_providers_match():
    items = {row['name']: row for row in transfer.oh.get('/items?recursive=false')}
    links = transfer.oh.get('/links')
    for name in MEMBERS:
        row = items.get(name)
        matches = [link for link in links if link.get('itemName') == name]
        if (not row or row.get('editable') is not False
                or row.get('groupNames') != [GROUP]
                or len(matches) != 1 or matches[0].get('editable') is not False
                or matches[0].get('configuration')):
            return False
    return True


def pumps_off():
    return all(transfer.oh.get('/items/' + name).get('state') == 'OFF'
               for name in PUMP_ITEMS)


def protected_controls_healthy(now=None):
    """Read-only health gate; never substitutes for physical operator review."""
    now = datetime.now(timezone.utc) if now is None else now
    require(now.tzinfo is not None and now.utcoffset() is not None,
            'aware protected-control assessment required')
    for uid in SAFETY_RULES:
        status = transfer.oh.get('/rules/' + uid).get('status', {})
        require((status.get('status'), status.get('statusDetail'))
                in (('IDLE', 'NONE'), ('RUNNING', 'NONE')),
                'protected rule unhealthy: ' + uid)
    raw_soc = transfer.oh.get('/items/BMS_SOC_Evidence_JSON').get('state')
    require(sanity.atomic_soc_freshness(raw_soc, now.timestamp()) is None,
            'atomic BMS SoC evidence unavailable or stale')
    raw_stamp = transfer.oh.get('/items/Schneider_DCData_LastUpdate').get('state')
    try:
        stamp = datetime.fromisoformat(str(raw_stamp).replace('Z', '+00:00'))
        age = (now - stamp).total_seconds()
    except (TypeError, ValueError):
        age = float('inf')
    require(0 <= age <= 300, 'Schneider DC telemetry unavailable or stale')
    return True


def group_matches(*, file_owned):
    try:
        row = transfer.oh.get('/items/' + GROUP + '?metadata=.*')
        return (row.get('editable') is (not file_owned)
                and row.get('name') == GROUP and row.get('type') == 'Group'
                and row.get('label') == 'Forecast Items'
                and row.get('tags') == ['forecast']
                and row.get('groupNames') == [] and not row.get('metadata')
                and registered_members() == MEMBERS)
    except Exception:
        return False


def wait_group(*, file_owned, seconds=240):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if active() and group_matches(file_owned=file_owned):
            return True
        time.sleep(3)
    return False


def daily_gate():
    rows = json.loads(MANIFEST.read_text())['resources']
    expected = {(kind, name) for kind in ('item', 'link') for name in DAILY}
    found = set()
    for row in rows:
        name = row['id'].split(' -> ', 1)[0]
        key = (row['kind'], name)
        if key in expected and row.get('provider') == 'file' \
                and row.get('migration') == 'verified':
            found.add(key)
    return found == expected


def registry_record(body):
    items = json.loads(body)
    record = items.get(GROUP)
    require(record == {
        'class': 'org.openhab.core.items.ManagedItemProvider$PersistedItem',
        'value': {'groupNames': [], 'itemType': 'Group',
                  'tags': ['forecast'], 'label': 'Forecast Items'}},
        'managed Group JSONDB record changed')
    return items, record


def jdbc_baseline():
    db = transfer.psycopg2.connect(**transfer.parse_openhab_jdbc_config(
        '/var/lib/openhab/config/org/openhab/jdbc.config').connect_kwargs,
        connect_timeout=5)
    db.set_session(readonly=True, autocommit=True)
    try:
        baseline = {}
        with db.cursor() as cursor:
            for name in sorted(MEMBERS):
                cursor.execute('SELECT itemid FROM public.items WHERE itemname=%s', (name,))
                found = cursor.fetchall()
                require(len(found) == 1 and type(found[0][0]) is int,
                        'forecast JDBC identity missing: ' + name)
                identity = found[0][0]
                rows = transfer.history(db, identity)
                require(len(rows) >= 7, 'forecast JDBC history missing: ' + name)
                baseline[name] = (identity, rows)
        return baseline
    finally:
        db.close()


def verify_history(baseline, cutover):
    after = jdbc_baseline()
    for name, (identity, rows) in baseline.items():
        require(after[name][0] == identity, 'forecast JDBC identity changed: ' + name)
        past = Counter(row for row in rows if row[0] <= cutover)
        require(not (past - Counter(after[name][1])),
                'historical forecast JDBC rows lost: ' + name)


def install_registry(directory, items, name):
    data = json.dumps(items, separators=(',', ':'), allow_nan=False).encode()
    source = private_file(directory, name, data)
    command('sudo', '-n', 'install', '-o', 'openhab', '-g', 'openhab',
            '-m', '0644', str(source), str(REGISTRY))


def rollback(directory, original_record):
    command('sudo', '-n', 'systemctl', 'stop', 'openhab.service', timeout=180)
    require(not active(), 'OpenHAB did not stop for Group rollback')
    if TARGET.exists() or TARGET.is_symlink():
        require(not TARGET.is_symlink() and sha256(TARGET.read_bytes()).hexdigest()
                == SOURCE_SHA256, 'Group source drifted before rollback')
        command('sudo', '-n', 'rm', '--', str(TARGET))
    items = json.loads(REGISTRY.read_bytes())
    require(GROUP not in items or items[GROUP] == original_record,
            'unexpected Group JSONDB record during rollback')
    items[GROUP] = original_record
    install_registry(directory, items, 'rollback-items.json')
    command('sudo', '-n', 'systemctl', 'start', 'openhab.service', timeout=180)
    require(wait_group(file_owned=False), 'managed Group rollback or members failed')


def main(apply):
    require(active(), 'OpenHAB service is not active')
    require(not TARGET.exists() and not TARGET.is_symlink(),
            'forecast Group file target already exists')
    source_hash = sha256(SOURCE.read_bytes()).hexdigest()
    require(source_hash == SOURCE_SHA256, 'prepared Group source changed')
    require(group_matches(file_owned=False), 'managed Group or ten members drifted')
    require(member_providers_match(), 'forecast member Item/link providers drifted')
    _, original_record = registry_record(REGISTRY.read_bytes())
    require(transfer.healthy_thing(), 'forecast Thing is not ONLINE')
    baseline = jdbc_baseline()
    eligible = daily_gate()
    if not apply:
        print(json.dumps({'status': 'preflight_passed',
            'daily_natural_writer_gate': 'verified' if eligible else 'pending',
            'member_count': len(MEMBERS),
            'jdbc_item_ids': {name: entry[0] for name, entry in baseline.items()},
            'source_sha256': source_hash}, sort_keys=True), flush=True)
        return
    require(eligible, 'daily natural writer gate not verified in ownership manifest')
    require(RELEASE_READY, 'forecast Group live transfer is not release-qualified')
    require(pumps_off(), 'greywater pump active or state unknown; refuse OpenHAB stop')
    protected_controls_healthy()
    root = BACKUP_ROOT.lstat()
    require(stat.S_ISDIR(root.st_mode) and root.st_uid == os.getuid()
            and stat.S_IMODE(root.st_mode) == 0o700,
            'private backup root unsafe')
    directory = BACKUP_ROOT / ('forecast-group-'
        + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    directory.mkdir(mode=0o700)
    stopped = False
    changed = False
    cutover = datetime.now(timezone.utc)
    try:
        require(pumps_off(), 'greywater pump changed before OpenHAB stop')
        protected_controls_healthy()
        command('sudo', '-n', 'systemctl', 'stop', 'openhab.service', timeout=180)
        stopped = True
        require(not active(), 'OpenHAB did not stop for Group handoff')
        body = REGISTRY.read_bytes()
        items, stopped_record = registry_record(body)
        require(stopped_record == original_record, 'Group changed during stop')
        private_file(directory, 'item-jsondb.json', body)
        private_file(directory, 'source.items', SOURCE.read_bytes())
        handle = os.open(directory, os.O_DIRECTORY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)
        print('private_backup=' + str(directory), flush=True)
        require(not TARGET.exists() and not TARGET.is_symlink(),
                'Group target appeared during stop')
        del items[GROUP]
        changed = True
        install_registry(directory, items, 'file-items.json')
        command('sudo', '-n', 'install', '-o', 'sat', '-g', 'openhab',
                '-m', '0644', str(SOURCE), str(TARGET))
        command('sudo', '-n', 'systemctl', 'start', 'openhab.service', timeout=180)
        require(wait_group(file_owned=True), 'file Group or ten members failed')
        require(member_providers_match(), 'forecast member providers changed after restart')
        verify_history(baseline, cutover)
    except BaseException:
        if changed:
            rollback(directory, original_record)
            print('managed_group_rollback_verified=true', flush=True)
        elif stopped:
            command('sudo', '-n', 'systemctl', 'start', 'openhab.service', timeout=180)
            require(wait_group(file_owned=False), 'unchanged managed Group failed restart')
        raise
    print(json.dumps({'status': 'file_provider_provisional',
        'backup': str(directory), 'member_count': len(MEMBERS),
        'jdbc_item_ids': {name: entry[0] for name, entry in baseline.items()},
        'natural_series_pending': True}, sort_keys=True), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] not in (['--check'], ['--apply']):
        raise SystemExit('usage: migrate-forecast-group-offline.py --check|--apply')
    main(apply=sys.argv[1:] == ['--apply'])
