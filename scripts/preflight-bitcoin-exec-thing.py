#!/usr/bin/env python3
"""Read-only preflight for the staged, display-only Bitcoin polling Thing.

No apply path, command execution, provider write, backup or service operation.
Syntax qualification is distinct from actual binding/provider qualification.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import openhab_sanity_check as oh  # noqa: E402

UID = 'exec:command:BTC_Price'
SOURCE = ROOT / 'openhab/file-config/things/bitcoin-price.things'
TARGET = Path('/etc/openhab/things/bitcoin-price.things')
CONFIG = {'command': '/etc/openhab/scripts/bitcoin.py',
          'interval': 30, 'timeout': 15, 'autorun': False}
CHANNELS = {'output': 'String', 'input': 'String', 'exit': 'Number',
            'run': 'Switch', 'lastexecution': 'DateTime',
            'stdout': 'String', 'stderr': 'String'}
LINKS = {'BTC_USD_Price': {},
         'BTC_Output_Receipt_JSON': {'profile': 'transform:JS',
                                     'toItemScript': 'bitcoin_output_receipt.js'}}
SOURCE_BYTES = b'''// Staged only: the live Exec Thing remains managed until qualified handoff.
// Keep the existing private-credential script and polling policy unchanged.
Thing exec:command:BTC_Price "BTC_Price" [
    command="/etc/openhab/scripts/bitcoin.py",
    interval=30,
    timeout=15,
    autorun=false
]
'''


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def definition(thing):
    """Provider-neutral full contract; membership order is not a definition."""
    result = {key: deepcopy(thing.get(key)) for key in (
        'UID', 'thingTypeUID', 'label', 'bridgeUID', 'location', 'properties', 'configuration')}
    channels = deepcopy(thing.get('channels', []))
    for channel in channels:
        if 'linkedItems' in channel:
            channel['linkedItems'] = sorted(channel['linkedItems'])
    result['channels'] = sorted(channels, key=lambda channel: channel['id'])
    return result


def validate_source(path):
    require(not path.is_symlink() and path.read_bytes() == SOURCE_BYTES,
            'prepared Bitcoin Thing source changed')


def validate(thing, links):
    require(isinstance(thing, dict) and all(thing.get(k) == v for k, v in {
        'UID': UID, 'thingTypeUID': 'exec:command', 'label': 'BTC_Price',
        'bridgeUID': None, 'location': None,
        'properties': {'thingTypeVersion': '1'},
    }.items()) and thing.get('editable') is True,
            'live managed Bitcoin Thing identity or metadata changed')
    require(thing.get('statusInfo') == {'status': 'ONLINE', 'statusDetail': 'NONE'},
            'Bitcoin polling Thing is not ONLINE')
    config = thing.get('configuration')
    require(config == CONFIG and all(type(config[k]) is type(v) for k, v in CONFIG.items()),
            'Bitcoin command or polling configuration changed')
    channels = thing.get('channels')
    require(isinstance(channels, list) and len(channels) == len(CHANNELS),
            'Bitcoin channel count changed')
    require(all(isinstance(c, dict) for c in channels)
            and {c.get('id') for c in channels} == set(CHANNELS),
            'Bitcoin channel identities changed')
    for channel in channels:
        name = channel['id']
        require(channel.get('uid') == UID + ':' + name
                and channel.get('channelTypeUID') == 'exec:' + name
                and channel.get('itemType') == CHANNELS[name]
                and channel.get('kind') == 'STATE'
                and channel.get('configuration') == {}
                and not channel.get('properties'),
                'Bitcoin channel definition changed')
    require(isinstance(links, list) and all(isinstance(link, dict) for link in links),
            'complete link inventory required')
    selected = [link for link in links
                if str(link.get('channelUID', '')).startswith(UID + ':')]
    require(len(selected) == len(LINKS)
            and {link.get('itemName') for link in selected} == set(LINKS),
            'Bitcoin output membership or command-channel links changed')
    for link in selected:
        require(link.get('channelUID') == UID + ':output'
                and link.get('editable') is False
                and link.get('configuration') == LINKS[link['itemName']],
                'Bitcoin output provider or transform changed')


def qualify_syntax():
    jars = sorted(Path('/usr/share/openhab/runtime/system').rglob('*.jar'))
    parsers = [p for p in jars if p.name.startswith('org.openhab.core.model.thing-')]
    require(len(parsers) == 1 and parsers[0].name == 'org.openhab.core.model.thing-5.2.1.jar',
            'review installed Thing parser version before qualification')
    result = subprocess.run([
        'java', '-Xmx256m', '-XX:ActiveProcessorCount=2', '--class-path',
        ':'.join(map(str, jars)), str(ROOT / 'scripts/HexOpenMeteoThingsParse.java'),
        str(SOURCE), '1',
    ], capture_output=True, text=True, timeout=45)
    lines = [line for line in result.stdout.splitlines() if line.startswith((
        'model=', 'declarations=', 'negative_syntax_rejected=', 'syntax_errors='))]
    require(result.returncode == 0 and lines == [
        'model=ThingModel', 'declarations=1',
        'negative_syntax_rejected=true', 'syntax_errors=0'],
        'offline Bitcoin Thing syntax qualification failed')


def check(*, syntax=False):
    require(not TARGET.exists() and not TARGET.is_symlink(),
            'Bitcoin Thing file target already exists')
    validate_source(SOURCE)
    original = oh.get('/things/' + UID + '?summary=false')
    validate(original, oh.get('/links'))
    if syntax:
        qualify_syntax()
    return {'scope': 'read_only_bitcoin_exec_thing_preflight', 'uid': UID,
            'source_sha256': sha256(SOURCE_BYTES).hexdigest(),
            'managed_dto_sha256': sha256(json.dumps(original, sort_keys=True,
                separators=(',', ':')).encode()).hexdigest(),
            'live_provider': 'managed', 'linked_outputs': sorted(LINKS),
            'syntax': 'qualified' if syntax else 'not_tested',
            'provider_handoff': 'not_qualified', 'restart_and_rollback': 'not_qualified',
            'production_writes': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--syntax', action='store_true',
                        help='Also run the installed offline OpenHAB 5.2.1 grammar parser')
    args = parser.parse_args()
    try:
        print(json.dumps(check(syntax=args.syntax), sort_keys=True))
    except Exception:
        # Transport/driver output may contain credentials. Do not print it.
        raise SystemExit('Bitcoin Exec Thing preflight refused; no production writes') from None
