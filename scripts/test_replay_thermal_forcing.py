import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).with_name('replay-thermal-forcing.py')
SPEC = importlib.util.spec_from_file_location('thermal_forcing_replay', SOURCE)
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def test_cli_requires_explicit_complete_runtime():
    runtime = SOURCE.resolve().parents[1] / 'openhab/scripts'
    help_result = subprocess.run([sys.executable, str(SOURCE), '--runtime-root',
                                  str(runtime), '--help'], capture_output=True, text=True)
    assert help_result.returncode == 0
    assert '--assume-vents-closed' in help_result.stdout
    missing = subprocess.run([sys.executable, str(SOURCE), '--runtime-root',
                              str(runtime / 'missing'), '--help'],
                             capture_output=True, text=True)
    assert missing.returncode != 0
    assert 'runtime root required' in missing.stderr


def test_closed_vent_schedule_changes_only_vent_assumptions():
    original = {'vent': 'open', 'ventFlow': 'baseline', 'ventForcing': 1.0,
                'ventOpenAt': 'later', 'airflowSegments': ('vent',),
                'indoorShadeInitial': 'closed'}
    changed = replay._closed_vent_schedule(None, [], lambda *_: original)
    assert original['vent'] == 'open'
    assert changed['vent'] == changed['ventFlow'] == 'closed'
    assert changed['ventForcing'] == 0.0
    assert changed['ventOpenAt'] is None
    assert changed['airflowSegments'] == ()
    assert changed['indoorShadeInitial'] == 'closed'


def test_horizon_deltas_keep_exact_target_and_sign():
    issued = {'forecast': {'trajectory': [
        {'at': '2026-09-28T01:00:00+00:00', 'hallwayF': 70.0},
        {'at': '2026-09-28T06:00:00+00:00', 'hallwayF': 66.0}]}}
    closed = {'forecast': {'trajectory': [
        {'at': '2026-09-28T01:00:00+00:00', 'hallwayF': 70.0},
        {'at': '2026-09-28T06:00:00+00:00', 'hallwayF': 67.25}]}}
    decision = replay.datetime.fromisoformat('2026-09-28T00:00:00+00:00')
    rows = replay._horizon_deltas(issued, closed, decision)
    assert [(row['hours'], row['delta_f']) for row in rows] == [(1, 0.0), (6, 1.25)]
    closed['forecast']['trajectory'][1]['at'] = '2026-09-28T06:05:00+00:00'
    with pytest.raises(ValueError, match='timestamps changed'):
        replay._horizon_deltas(issued, closed, decision)


def test_v1_and_source_mismatch_fail_before_simulation(monkeypatch):
    monkeypatch.setattr(replay, 'verify_capture', lambda _: {'schema': 'earthship-thermal-shadow-forcing-capture/v1'})
    with pytest.raises(ValueError, match='requires a v2'):
        replay.replay('capture')
    monkeypatch.setattr(replay, 'verify_capture', lambda _: {
        'schema': 'earthship-thermal-shadow-forcing-capture/v2', 'artifact': {}})
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'b' * 64)
    monkeypatch.setattr(replay, '_run', lambda *_: pytest.fail('simulation must not run'))
    with pytest.raises(ValueError, match='does not match selected runtime'):
        replay.replay('capture')


def test_counterfactual_requires_exact_as_issued_replay(monkeypatch):
    issued = {'generatedAt': '2026-09-28T14:20:30.123000+00:00', 'status': 'shadow'}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
               'artifact': {}, 'decision_at': issued['generatedAt'], 'output': issued,
               'sha256': {'output': 'c' * 64}}
    monkeypatch.setattr(replay, 'verify_capture', lambda _: capture)
    monkeypatch.setattr(replay, '_artifact_from_payload', lambda _: SimpleNamespace(code_revision='a' * 64))
    monkeypatch.setattr(replay, '_runtime_manifest_revision', lambda _: 'a' * 64)
    monkeypatch.setattr(replay, '_run', lambda *_: {
        'generatedAt': '2026-09-28T14:20:30+00:00', 'status': 'unavailable'})
    with pytest.raises(ValueError, match='failed exact replay'):
        replay.replay('capture', assume_vents_closed=True)
