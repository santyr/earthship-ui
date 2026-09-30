"""Actual JS producer -> disposable JDBC rows -> restricted Energy consumers.

All events/statuses/clocks are simulated; no OpenHAB endpoint or live BMS is
touched. This qualifies cross-language recovery semantics, not JVM/network
recovery or a complete naturally observed day.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

import pytest

fixture_module = pytest.importorskip(
    'advisory_db_fixture', reason='explicit disposable PostgreSQL harness required',
)
advisory_db = fixture_module.advisory_db

from bms_aux_evidence import parse_bms_aux_receipt, validate_receipt_successor
from earthship_energy.bms_aux_quality import read_current_bms_aux_health
from earthship_energy.config import load_source_config
from earthship_energy.scheduled import _live_sources_ok
from earthship_energy.ui_reader import fetch_live_subsystem_health
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
TRACE = r"""
import { harness, specs } from './tests/openhab/helpers/bms-aux-harness.js';
const h = harness(Date.UTC(2026, 9, 1, 6)), stages = [];
const stage = name => {
  stages.push({ name, now: h.now + 1,
    rows: h.queued.map(row => [row.at.micros, row.body]) });
  // Later events must lie beyond this as-of boundary, including persistence
  // rounding/ordering. Never let a later fault or recovery leak into a stage.
  h.advance(2);
};
h.run(); stage('bootstrap');
h.advance(); h.run(h.event('capacity')); h.run(h.event('temperature'));
stage('native_ready');
for (let poll = 0; poll < 6; poll++) {
  h.advance(); h.run(h.event('capacity')); h.run(h.event('temperature'));
}
stage('unchanged_native_ready');
h.advance(1); h.online.set(specs.temperature.thing, 'OFFLINE'); h.run();
stage('temperature_fault');
h.advance(); h.online.set(specs.temperature.thing, 'ONLINE'); h.run();
stage('online_without_event');
h.advance(); h.run(h.event('capacity')); h.run(h.event('temperature'));
stage('native_recovery');
h.advance(1); h.cache.clear(); h.run(); stage('restart_barrier');
h.advance(); h.run(h.event('capacity')); stage('restart_capacity_only');
h.run(h.event('temperature')); stage('restart_both_native');
h.advance(120000); h.run(); stage('exact_expiry');
h.advance(); h.run(h.event('capacity')); h.run(h.event('temperature'));
stage('expiry_native_recovery');
process.stdout.write(JSON.stringify(stages));
"""


def test_actual_producer_fault_restart_expiry_and_original_native_recovery(advisory_db):
    trace = subprocess.run(['node', '--input-type=module', '-e', TRACE],
                           cwd=ROOT, capture_output=True, text=True, timeout=15,
                           check=True)
    stages = json.loads(trace.stdout)
    expected = {
        'bootstrap': (False, False),
        'native_ready': (True, True),
        'unchanged_native_ready': (True, True),
        'temperature_fault': (True, False),
        'online_without_event': (True, False),
        'native_recovery': (True, True),
        'restart_barrier': (False, False),
        'restart_capacity_only': (True, False),
        'restart_both_native': (True, True),
        'exact_expiry': (False, False),
        'expiry_native_recovery': (True, True),
    }
    assert [stage['name'] for stage in stages] == list(expected)
    # Retain the producer's actual ordered persistence timestamps, including
    # independent native updates sharing a recording millisecond.
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    rows = [(epoch + timedelta(microseconds=micros), raw)
            for micros, raw in stages[-1]['rows']]
    receipts = [parse_bms_aux_receipt(raw, stamp) for stamp, raw in rows]
    for previous, latest in zip(receipts, receipts[1:]):
        validate_receipt_successor(previous, latest)
    assert len({receipt.epoch for receipt in receipts}) == 2
    assert any(a.recorded_at == b.recorded_at
               for a, b in zip(receipts, receipts[1:]))
    with closing(advisory_db.connect_owner()) as connection, connection:
        with connection.cursor() as cursor:
            cursor.execute('CREATE TABLE public.items (itemid integer, itemname text)')
            cursor.execute('INSERT INTO public.items VALUES (658, %s)',
                           ('BMS_Aux_Evidence_JSON',))
            cursor.execute('CREATE TABLE public.item0658 '
                           '(time timestamptz PRIMARY KEY, value text)')
            cursor.executemany('INSERT INTO public.item0658 VALUES (%s, %s)', rows)
            cursor.execute('GRANT SELECT ON public.items, public.item0658 '
                           'TO advisory_assessor')
    config = SimpleNamespace(sources=tuple(source for source in load_source_config().sources
        if source.canonical_name in ('battery.remaining_ah', 'battery.temperature_c')))
    # Definitions of the numeric Items must still exist independently of the
    # evidence reader. These controlled resolver inputs model those mappings.
    resolved = tuple(SimpleNamespace(canonical_name=source.canonical_name,
        required=True, status='ok', freshness_table_name='item0658') for source in config.sources)
    cutover = rows[0][0] - timedelta(seconds=1)
    with closing(advisory_db.connect_assessor()) as connection:
        connection.set_session(readonly=True, autocommit=False)
        for stage in stages:
            now = epoch + timedelta(milliseconds=stage['now'])
            wanted = dict(zip(('battery.remaining_ah', 'battery.temperature_c'),
                              expected[stage['name']]))
            assert read_current_bms_aux_health(connection, generated_at=now,
                cutover=cutover) == wanted, stage['name']
            ui = fetch_live_subsystem_health(connection, config, resolved,
                generated_at=now, bms_aux_cutover=cutover)
            assert ui['bms'] == ('ok' if all(wanted.values()) else 'fault'), stage['name']
            assert _live_sources_ok(connection, config, resolved, now,
                bms_aux_cutover=cutover) is all(wanted.values()), stage['name']
        with connection.cursor() as cursor:
            cursor.execute('SHOW transaction_read_only')
            assert cursor.fetchone() == ('on',)
            cursor.execute('SELECT count(*) FROM public.item0658')
            assert cursor.fetchone() == (len(rows),)
