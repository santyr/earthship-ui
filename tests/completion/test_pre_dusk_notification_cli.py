"""CLI release/clock/identity boundaries without real credentials or sends."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import pre_dusk_notification_cli as cli
import pre_dusk_notification as notification


def test_default_off_delivery_refuses_before_credentials_or_signer(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError('no credential/source/signer operation permitted')
    monkeypatch.setattr(cli, 'token', forbidden)
    monkeypatch.setattr(cli, 'restricted_connection', forbidden)
    monkeypatch.setattr(cli, 'Keyer', forbidden)
    assert cli.main(['--deliver']) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'withheld'


@pytest.mark.parametrize('instant,wanted', [
    ('2026-09-30T16:59:59+00:00', '2026-09-29'),
    ('2026-09-30T17:00:00+00:00', '2026-09-30'),
    ('2026-11-01T17:59:59+00:00', '2026-10-31'),
    ('2026-11-01T18:00:00+00:00', '2026-11-01'),
])
def test_active_target_rolls_at_local_11_including_dst(instant, wanted):
    assert cli.active_day(datetime.fromisoformat(instant)).isoformat() == wanted


def test_read_only_check_does_not_open_outbox_or_load_keyer(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'token', lambda: 'test-token-not-a-credential')
    monkeypatch.setattr(cli, 'restricted_connection', lambda: 'connection-factory')
    calls = []
    def read(get, connect, **kwargs):
        calls.append((connect, kwargs))
        return None
    monkeypatch.setattr(cli, 'read_notice', read)
    monkeypatch.setattr(cli, 'Keyer', lambda *a: (_ for _ in ()).throw(AssertionError('signer forbidden')))
    monkeypatch.setattr(cli, 'run', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('worker forbidden')))
    assert cli.main(['--check-source', '--day', '2026-09-30']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['notification_eligible'] is False
    assert result['outbox_writes'] == 0 and result['message_published'] is False
    assert calls[0][1]['sender'] == cli.SENDER
    assert calls[0][1]['operator'] == cli.OPERATOR
    assert cli.SENDER != cli.OPERATOR
    assert calls[0][1]['now'].tzinfo is not None


def test_delivery_cannot_override_date_even_when_release_is_open(monkeypatch, capsys):
    monkeypatch.setattr(notification, 'RELEASE_READY', True)
    monkeypatch.setattr(cli, 'token', lambda: (_ for _ in ()).throw(AssertionError('credential forbidden')))
    assert cli.main(['--deliver', '--day', '2026-09-29']) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'withheld'


def test_cli_does_not_expose_historical_clock_override(capsys):
    with pytest.raises(SystemExit):
        cli.main(['--check-source', '--now', '2026-09-29T23:31:00Z'])
    capsys.readouterr()


def test_private_transport_failures_are_not_printed(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'token', lambda: (_ for _ in ()).throw(RuntimeError('TEST-SECRET-DO-NOT-LOG')))
    assert cli.main(['--check-source']) == 2
    output = capsys.readouterr()
    assert 'TEST-SECRET' not in output.out + output.err
    assert json.loads(output.out)['status'] == 'withheld'
