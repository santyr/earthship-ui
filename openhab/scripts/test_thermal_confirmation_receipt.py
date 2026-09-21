"""Exact acknowledgement boundary for trusted thermal journal ingestion."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import json

import pytest
import thermal_intel


@pytest.mark.parametrize('fault', [None, 'missing', 'changed', 'duplicate', 'unexpected_mode', 'read_error'])
@pytest.mark.parametrize('inserted', [0, 1])
@pytest.mark.parametrize('body', ['vent: open', 'effective: 2026-09-20T05:00:00-06:00\nvent: open'])
def test_confirmation_acknowledges_only_exact_readback(tmp_path, monkeypatch, capsys, fault, inserted, body):
    message = tmp_path / 'message.txt'
    message.write_text('THERMAL\n' + body + '\n')
    args = SimpleNamespace(message_file=message, idempotency_key='test-receipt',
        received_at=datetime(2026, 9, 20, 12, tzinfo=timezone.utc))
    monkeypatch.setenv('THERMAL_DATABASE_URL', 'unused-test-dsn')

    class Journal:
        def __init__(self, dsn):
            assert dsn == 'unused-test-dsn'

        def append_batch(self, actions, modes, *, payload):
            self.actions, self.modes = actions, modes
            assert payload == message.read_bytes()
            return inserted

        def events_for_receipt(self, key):
            assert key == args.idempotency_key
            if fault == 'read_error':
                raise RuntimeError('unavailable')
            if fault == 'missing':
                return ()
            if fault == 'changed':
                return (replace(self.actions[0], state='closed'),)
            if fault == 'duplicate':
                return (*self.actions, *self.actions)
            return self.actions

        def modes_for_receipt(self, key):
            return self.actions if fault == 'unexpected_mode' else self.modes

    monkeypatch.setattr(thermal_intel, 'ActionJournal', Journal)
    if fault:
        with pytest.raises((ValueError, RuntimeError)):
            thermal_intel._journal(args, None, now=args.received_at)
        assert capsys.readouterr().out == ''
    else:
        thermal_intel._journal(args, None, now=args.received_at)
        receipt = json.loads(capsys.readouterr().out)
        assert receipt['inserted'] == inserted
        assert len(receipt['action_event_ids']) == 1
        assert receipt['mode_event_ids'] == []


@pytest.mark.parametrize('body,received', [
    ('vent: open', '2026-09-21T12:00:00+00:00'),
    ('effective: 2026-09-21T06:00:00-06:00\nvent: closed', '2026-09-20T12:00:00+00:00'),
    ('effective: 2026-09-21T06:00:00-06:00\nmode: winter', '2026-09-20T12:00:00+00:00'),
    ('vent: 20:30-07:00', '2026-09-20T12:00:00+00:00'),
])
def test_future_plans_never_reach_confirmation_journal(tmp_path, monkeypatch, capsys, body, received):
    message = tmp_path / 'message.txt'
    message.write_text('THERMAL\n' + body + '\n')
    args = SimpleNamespace(message_file=message, idempotency_key='test-future',
        received_at=datetime.fromisoformat(received))
    monkeypatch.setenv('THERMAL_DATABASE_URL', 'unused-test-dsn')
    def forbidden(dsn):
        pytest.fail('future confirmation must be refused before constructing journal')
    monkeypatch.setattr(thermal_intel, 'ActionJournal', forbidden)
    with pytest.raises(ValueError, match='future'):
        thermal_intel._journal(args, None, now=datetime(2026, 9, 20, 12, tzinfo=timezone.utc))
    assert capsys.readouterr().out == ''
