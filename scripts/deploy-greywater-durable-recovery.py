#!/usr/bin/env python3
"""Exact attended greywater durability repair; default is read-only preflight.

No provider migration, restart, rule run, synthetic input or pump command.
--apply additionally requires reviewed attendance and physical OFF confirmation.
"""
import argparse
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from urllib.error import HTTPError

import sky_control_probe as sky

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('greywater_durable_guard',
    ROOT / 'scripts/deploy-greywater-timer-guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
guard.OLD_SHA = 'e697e2626a5e1ab4e4d079612c4b85d16dd79178a4ff80a5208b4bb108970d18'
guard.NEW_SHA = '4c34780e544d80af8eb36d047a949fa30e0198bb50fa57650285052db3c52d9b'
INPUTS = ('BMS_Comms_Status', 'BMS_SOC_Evidence_JSON', 'DCData_Voltage',
          'SchneiderTelemetry_Status', 'Schneider_DCData_LastUpdate',
          'Sun_Position_Elevation', 'SouthOutlet_LastCycleStart')
RELATED = (*guard.PUMPS, 'SouthOutlet_ManualRequest', 'SouthOutlet_ManualResult',
           'SouthOutlet_LastCycleStart', 'SouthOutlet_LastCycle', 'SouthOutlet_LastAutoRun')


def timestamp(value):
    value = re.sub(r'\[[^\]]+\]$', '', value)
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def number(value):
    result = float(str(value).split()[0])
    if not math.isfinite(result): raise ValueError('nonfinite input')
    return result


def check_values(values, now):
    try:
        if values['BMS_Comms_Status'] != 'OK': raise ValueError('BMS comms')
        if guard.oh.atomic_soc_freshness(values['BMS_SOC_Evidence_JSON'], now.timestamp()):
            raise ValueError('native SoC receipt')
        if not 40 <= number(values['DCData_Voltage']) <= 60: raise ValueError('voltage')
        if not values['SchneiderTelemetry_Status'].startswith('OK,'): raise ValueError('Schneider status')
        age = (now - timestamp(values['Schneider_DCData_LastUpdate'])).total_seconds()
        if not -5 <= age <= 300: raise ValueError('Schneider stamp')
        elevation = number(values['Sun_Position_Elevation'])
        if elevation > 0:
            elapsed = (now - timestamp(values['SouthOutlet_LastCycleStart'])).total_seconds()
            if not 0 <= elapsed <= 3600 - 300: raise ValueError('five-minute cooldown window')
    except (ValueError, KeyError, TypeError):
        raise RuntimeError('fresh healthy telemetry and safe cooldown window required') from None


def definitions():
    keys = ('name', 'type', 'label', 'category', 'tags', 'groupNames', 'metadata')
    result = {name: {key: value for key, value in guard.oh.get('/items/' + name + '?metadata=.*').items()
                     if key in keys} for name in RELATED}
    result['links'] = [link for link in guard.oh.get('/links') if link.get('itemName') in RELATED]
    return result


def history_snapshot(name, query):
    try:
        return guard.oh.get('/persistence/items/' + name + '?' + query)
    except HTTPError as error:
        if error.code != 404: raise
        return {'status': 404, 'data': []}  # Explicitly retain absence, not a fabricated row.


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--attended', action='store_true')
    parser.add_argument('--physical-pumps-off', action='store_true')
    args = parser.parse_args(argv)
    if args.apply and not (args.attended and args.physical_pumps_off):
        raise RuntimeError('fresh operator attendance and physical OFF confirmation required')
    source = guard.SOURCE.read_text()
    if guard.digest(source) != guard.NEW_SHA: raise RuntimeError('qualified candidate drift')
    baseline = guard.oh.get('/rules/' + guard.UID)
    sky.control_payload(baseline, baseline['actions'][0]['configuration']['script'].encode())
    replacement = copy.deepcopy(baseline)
    replacement['actions'][0]['configuration']['script'] = source
    before_dto, after_dto = guard.dto(baseline), guard.dto(replacement)
    original_off, original_put, original_backup = guard.pumps_off, guard.put, guard.backup
    continuity = {}

    def verify_continuity():
        if not continuity: return
        if definitions() != continuity['definitions']:
            raise RuntimeError('related Item/link definition drift; refuse release/rollback')
        for name, previous in continuity['histories'].items():
            if history_snapshot(name, continuity['history_query']) != previous:
                raise RuntimeError('fixed-window original JDBC history changed')

    def healthy_off():
        original_off()
        values = {name: guard.oh.get('/items/' + name)['state'] for name in INPUTS}
        check_values(values, datetime.now(timezone.utc))
        original_off()  # Recheck after telemetry reads, never command a device.
        verify_continuity()  # Inside the original guarded transaction/rollback.

    def guarded_put(rule):
        current = guard.dto(guard.oh.get('/rules/' + guard.UID))
        if current not in (before_dto, after_dto) or guard.dto(rule) not in (before_dto, after_dto):
            raise RuntimeError('unowned protected-rule drift; refuse overwrite')
        original_put(rule)

    def backup_with_continuity(rule):
        if guard.dto(rule) != before_dto: raise RuntimeError('baseline changed before backup')
        now = datetime.now(timezone.utc)
        query = urlencode({'serviceId': 'jdbc', 'starttime': (now - timedelta(days=1)).isoformat(),
                           'endtime': now.isoformat()})
        continuity.update({'definitions': definitions(), 'history_query': query,
                           'histories': {name: history_snapshot(name, query)
                                         for name in RELATED}})
        directory = original_backup(rule)
        with (directory / 'continuity.json').open('x') as stream:
            json.dump(continuity, stream, sort_keys=True)
            stream.write('\n')
        return directory

    original_argv = sys.argv
    try:
        guard.pumps_off, guard.put, guard.backup = healthy_off, guarded_put, backup_with_continuity
        sys.argv = [original_argv[0], *(['--apply'] if args.apply else [])]
        guard.main()
        if args.apply:
            print('related_definitions_and_fixed_day_jdbc_history=unchanged', flush=True)
        else:
            query = urlencode({'serviceId': 'jdbc',
                               'starttime': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
                               'endtime': datetime.now(timezone.utc).isoformat()})
            definitions()
            for name in RELATED: history_snapshot(name, query)
            print('related_definition_and_bounded_history_reads=available', flush=True)
    finally:
        sys.argv = original_argv
        guard.pumps_off, guard.put, guard.backup = original_off, original_put, original_backup


if __name__ == '__main__':
    os.umask(0o077)
    main()
