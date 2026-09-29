"""The optional score CLI must bind its outcome to the physical bank registry."""

from datetime import date, datetime, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).with_name('qualify-pre-dusk-natural-issue.py')
SPEC = importlib.util.spec_from_file_location('qualify_pre_dusk_natural_issue', SCRIPT)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


DAY = date(2026, 9, 29)
ASSESSMENT = datetime(2026, 9, 30, 17, 10, tzinfo=timezone.utc)


def epoch(*, start=date(2026, 7, 19), end=None, current=True):
    return SimpleNamespace(start_local_date=start,
                           end_local_date_exclusive=end,
                           current_analytics=current)


def test_outcome_uses_one_current_physical_bank_boundary(monkeypatch):
    connection = object()
    calls = []
    monkeypatch.setattr(cli, 'load_epoch_config', lambda: (epoch(current=False), epoch()))
    monkeypatch.setattr(cli, 'restricted_connection', lambda: connection)
    monkeypatch.setattr(cli, 'read_completed_outcome',
                        lambda factory, **kwargs: calls.append((factory, kwargs)) or {'status': 'measured'})

    assert cli.outcome_reader(DAY, ASSESSMENT) == {'status': 'measured'}
    assert calls == [(connection, {'day': DAY, 'as_of': ASSESSMENT,
                                  'epoch_start': datetime(2026, 7, 19, 6,
                                                          tzinfo=timezone.utc),
                                  'epoch_end': None})]


@pytest.mark.parametrize('epochs', [(), (epoch(current=False),),
                                      (epoch(), epoch())])
def test_outcome_refuses_missing_or_ambiguous_bank_before_database(monkeypatch, epochs):
    monkeypatch.setattr(cli, 'load_epoch_config', lambda: epochs)
    monkeypatch.setattr(cli, 'restricted_connection',
                        lambda: pytest.fail('bank selection must precede database'))
    with pytest.raises(ValueError, match='one physical bank epoch required'):
        cli.outcome_reader(DAY, ASSESSMENT)
