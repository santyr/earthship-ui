"""Original receipt transport plus restricted SQL-reader test doubles."""
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
from pre_dusk_notification_source import read_notice
from pre_dusk_tuning_history import MORNING_ITEM, PRE_DUSK_ITEM
import thermal_confirmation as t
from test_pre_dusk_notification import NOW, SENDER, OPERATOR, inputs
from test_pre_dusk_issue_source import Connection

DAY = date(2026, 9, 29)


def history_fixture(soc=40):
    issue, raw, stored = inputs(soc=soc)
    morning = {'version': 1, 'predictionDay': DAY.isoformat(),
               'issuedAt': issue['morningIssuedAt']}
    stamp = lambda at: int(datetime.fromisoformat(at).timestamp() * 1000)
    archives = {
        MORNING_ITEM: [{'time': stamp(morning['issuedAt']) + 100, 'state': json.dumps(morning)}],
        PRE_DUSK_ITEM: [{'time': stamp(issue['issuedAt']) + 100, 'state': json.dumps(issue)}],
    }
    gets, connections = [], []

    def get(path):
        gets.append(path)
        parsed = urlsplit(path)
        assert parsed.path.startswith('/persistence/items/')
        assert 'serviceId=jdbc' in parsed.query
        name = parsed.path.rsplit('/', 1)[1]
        rows = deepcopy(archives[name])
        return {'name': name, 'datapoints': str(len(rows)), 'data': rows}

    def connect():
        connection = Connection(rows=((datetime.fromisoformat(stored), raw),))
        connections.append(connection)
        return connection

    return archives, gets, connections, get, connect


def read(get, connect, **changes):
    kwargs = {'day': DAY, 'now': NOW + timedelta(seconds=1),
              'sender': SENDER, 'operator': OPERATOR, **changes}
    return read_notice(get, connect, **kwargs)


def test_original_history_and_source_prepare_one_notice_without_writes():
    _, gets, connections, get, connect = history_fixture()
    prepared = read(get, connect)
    assert prepared['intent'] == 'pre-dusk-notice:2026-09-29'
    assert '20%' in prepared['rumor']['content']
    assert len(gets) == 2 and len(connections) == 1
    assert {urlsplit(path).path for path in gets} == {
        f'/persistence/items/{MORNING_ITEM}', f'/persistence/items/{PRE_DUSK_ITEM}'}
    connection = connections[0]
    assert connection.closed and connection.session['readonly'] is True
    assert all(sql.startswith(('SET LOCAL ', 'SHOW ', 'SELECT '))
               for sql, _ in connection.cursor_instance.calls)
    assert 'original_soc' not in prepared
    assert 'socStreamEpoch' not in prepared['rumor']['content']


def test_valid_high_forecast_prepares_no_alert():
    _, _, connections, get, connect = history_fixture(soc=99)
    assert read(get, connect) is None
    assert len(connections) == 1 and connections[0].closed


@pytest.mark.parametrize('case', ['missing_late', 'duplicate_late', 'missing_morning',
                                 'late_not_persisted', 'morning_persisted_after_issue'])
def test_ambiguous_or_misordered_archive_refuses_before_source_query(case):
    archives, _, connections, get, connect = history_fixture()
    if case == 'missing_late':
        archives[PRE_DUSK_ITEM] = []
    elif case == 'duplicate_late':
        row = deepcopy(archives[PRE_DUSK_ITEM][0]); row['time'] += 1
        archives[PRE_DUSK_ITEM].append(row)
    elif case == 'missing_morning':
        archives[MORNING_ITEM] = []
    elif case == 'late_not_persisted':
        archives[PRE_DUSK_ITEM][0]['time'] += 2000
    else:
        # Still within the archive's 600s issue/persistence allowance; the
        # notification bridge must reject the origin's impossible chronology.
        issue = json.loads(archives[PRE_DUSK_ITEM][0]['state'])
        morning_at = NOW - timedelta(seconds=1)
        issue['morningIssuedAt'] = morning_at.isoformat()
        archives[PRE_DUSK_ITEM][0]['state'] = json.dumps(issue)
        archives[MORNING_ITEM][0] = {'time': int((NOW + timedelta(seconds=1)).timestamp() * 1000),
            'state': json.dumps({'version': 1, 'predictionDay': DAY.isoformat(),
                                 'issuedAt': morning_at.isoformat()})}
    with pytest.raises(t.Refused):
        read(get, connect)
    assert connections == []


def test_changed_original_input_is_not_replaced_with_a_current_item():
    _, gets, _, get, _ = history_fixture()
    connection = Connection(rows=())
    with pytest.raises(t.Refused):
        read(get, lambda: connection)
    assert connection.closed
    assert len(gets) == 2


@pytest.mark.parametrize('day,now', [
    (DAY, NOW.replace(day=30, hour=17, minute=0, second=0)),
    (date(2026, 9, 30), NOW),
])
def test_expired_or_future_target_refuses_before_io(day, now):
    _, gets, connections, get, connect = history_fixture()
    with pytest.raises(t.Refused):
        read(get, connect, day=day, now=now)
    assert gets == [] and connections == []
