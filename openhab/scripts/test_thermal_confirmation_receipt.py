"""Exact acknowledgement boundary for trusted thermal journal ingestion."""
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
import json

import pytest
import thermal_intel


@pytest.mark.parametrize('fault', [None, 'missing', 'changed', 'duplicate', 'unexpected_mode', 'read_error'])
@pytest.mark.parametrize('inserted', [0, 1])
def test_confirmation_acknowledges_only_exact_readback(tmp_path, monkeypatch, capsys, fault, inserted):
    message = tmp_path / 'message.txt'
    message.write_text('THERMAL\nvent: open\n')
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
            thermal_intel._journal(args, None)
        assert capsys.readouterr().out == ''
    else:
        thermal_intel._journal(args, None)
        receipt = json.loads(capsys.readouterr().out)
        assert receipt['inserted'] == inserted
        assert len(receipt['action_event_ids']) == 1
        assert receipt['mode_event_ids'] == []
