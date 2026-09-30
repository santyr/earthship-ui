"""Bounded original-JDBC notification preparation; no outbox or network sends."""
from datetime import date, datetime

from advisory_windows import trough_window
from pre_dusk_issue_source import read_issue_input
from pre_dusk_tuning_history import (
    MORNING_ITEM, PRE_DUSK_ITEM, read_day_issues, select_pair,
)
from pre_dusk_notification import notice
from pre_dusk_tuning import ZONE
import thermal_confirmation as t
from thermal_messaging import require


def _read_inputs(get, connection_factory, *, day, now, sender, operator):
    """Internal original-input bundle for one linked, validated persisted issue.

    The GET transport must be the restricted local JDBC archive reader. The
    SQL connection must be the dedicated restricted reader. Those credential/
    endpoint checks belong to the future deployment adapter, not injected tests.
    Never print this result: original source JSON remains internal to the worker.
    The third tuple member is None for a non-low forecast. Missing/ambiguous/
    stale history is refused. Public callers should use read_notice instead.
    """
    try:
        require(isinstance(day, date) and not isinstance(day, datetime),
                'prediction date required')
        now = t.aware(now)
        t.identifier(sender); t.identifier(operator)
        target = trough_window(day, 'America/Denver')
        require(day <= now.astimezone(ZONE).date() and now < target.end,
                'pre-dusk notification target unavailable')
        morning_rows = read_day_issues(get, item=MORNING_ITEM, day=day)
        late_rows = read_day_issues(get, item=PRE_DUSK_ITEM, day=day)
        morning, issue = select_pair(morning_rows, late_rows)
        issued = t.aware(issue['issuedAt'])
        require(t.aware(late_rows[0]['persisted_at']) <= now,
                'pre-dusk issue not yet persisted')
        linked = [row for row in morning_rows if row['receipt'] == morning]
        require(len(linked) == 1 and t.aware(linked[0]['persisted_at']) <= issued,
                'morning origin not persisted before pre-dusk issue')
        original = read_issue_input(connection_factory, issue)
        # Validate before returning any private input to the worker.
        prepared = notice(issue, original['original_soc'],
                          original['metadata']['source_persisted_at'],
                          now, sender, operator)
        return issue, original, prepared
    except Exception:
        # Original source JSON, credentials and transport exceptions stay private.
        raise t.Refused('original pre-dusk notification evidence unavailable') from None


def read_notice(get, connection_factory, *, day, now, sender, operator):
    """Read-only public preparation API; never expose original source JSON."""
    _, _, prepared = _read_inputs(get, connection_factory, day=day, now=now,
                                  sender=sender, operator=operator)
    return prepared
