"""Archive reads must keep issue provenance and reject ambiguous histories."""

from copy import deepcopy
from datetime import date, datetime, timezone
import json

import pytest

from pre_dusk_tuning_history import (IssueHistoryUnavailable, MORNING_ITEM,
    PRE_DUSK_ITEM, local_get, read_day_issues, select_pair)


DAY = date(2026, 9, 29)
MORNING = {'version': 1, 'predictionDay': DAY.isoformat(),
           'issuedAt': '2026-09-29T06:40:00-06:00', 'overnightTroughSocPct': 53}
LATE = {'version': 1, 'predictionDay': DAY.isoformat(),
        'issuedAt': '2026-09-29T17:30:00-06:00',
        'morningIssuedAt': MORNING['issuedAt'], 'overnightTroughSocPct': 81}


def row(receipt, seconds=2):
    at = datetime.fromisoformat(receipt['issuedAt']).astimezone(timezone.utc)
    return {'time': int(at.timestamp() * 1000) + seconds * 1000,
            'state': json.dumps(receipt, separators=(',', ':'))}


def fake_get(item, rows):
    calls = []
    def get(path):
        calls.append(path)
        return {'name': item, 'datapoints': str(len(rows)), 'data': rows}
    return get, calls


def test_reads_exact_local_day_from_jdbc_not_current_item():
    get, calls = fake_get(MORNING_ITEM, [row(MORNING)])
    issues = read_day_issues(get, item=MORNING_ITEM, day=DAY)
    assert len(issues) == 1 and issues[0]['receipt'] == MORNING
    assert calls[0].startswith('/persistence/items/Forecast_Prediction_Receipt_JSON?')
    assert 'serviceId=jdbc' in calls[0]
    assert 'starttime=2026-09-29T06%3A00%3A00Z' in calls[0]


def test_selects_explicitly_linked_origin_instead_of_latest_morning():
    rerun = {**MORNING, 'issuedAt': '2026-09-29T07:00:00-06:00'}
    mornings = [{'receipt': MORNING}, {'receipt': rerun}]
    assert select_pair(mornings, [{'receipt': LATE}]) == (MORNING, LATE)


@pytest.mark.parametrize('mutate', [
    lambda body: body.update(name=PRE_DUSK_ITEM),
    lambda body: body.update(datapoints=2),
    lambda body: body.update(datapoints='01'),
    lambda body: body['data'].append(body['data'][0]),
    lambda body: body['data'][0].update(state='{"version":1,"version":1}'),
    lambda body: body['data'][0].update(state=json.dumps({**MORNING, 'predictionDay':'2026-09-28'})),
    lambda body: body['data'][0].update(state=json.dumps({**MORNING, 'issuedAt':'2026-09-29T08:00:00-06:00'})),
    lambda body: body['data'][0].update(time=0),
])
def test_refuses_truncated_duplicate_or_wrong_origin_archive(mutate):
    body = {'name': MORNING_ITEM, 'datapoints': 1, 'data': [row(MORNING)]}
    mutate(body)
    with pytest.raises(IssueHistoryUnavailable):
        read_day_issues(lambda _: body, item=MORNING_ITEM, day=DAY)


def test_pair_requires_one_late_issue_and_exact_morning_link():
    with pytest.raises(IssueHistoryUnavailable):
        select_pair([{'receipt': MORNING}], [])
    with pytest.raises(IssueHistoryUnavailable):
        select_pair([{'receipt': MORNING}], [{'receipt': LATE}, {'receipt': LATE}])
    wrong = deepcopy(LATE)
    wrong['morningIssuedAt'] = '2026-09-29T06:41:00-06:00'
    with pytest.raises(IssueHistoryUnavailable):
        select_pair([{'receipt': MORNING}], [{'receipt': wrong}])


def test_local_transport_is_bounded_and_rejects_other_paths():
    class Response:
        status = 200
        def __init__(self, content):
            self.content = content
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def read(self, size):
            return self.content[:size]
    class Opener:
        def __init__(self, content):
            self.content = content
            self.requests = []
        def open(self, request, timeout):
            self.requests.append((request.full_url, timeout))
            return Response(self.content)
    path='/persistence/items/Forecast_Prediction_Receipt_JSON?serviceId=jdbc'
    opener=Opener(b'{"name":"Forecast_Prediction_Receipt_JSON","data":[],"datapoints":"0"}')
    assert local_get(path, token='private-test-token', opener=opener)['data'] == []
    assert opener.requests == [('http://127.0.0.1:8080/rest'+path, 5)]
    with pytest.raises(IssueHistoryUnavailable):
        local_get('/items/BMS_SOC/state', token='private-test-token', opener=opener)
    oversized=Opener(b'x'*32769)
    with pytest.raises(IssueHistoryUnavailable):
        local_get(path, token='private-test-token', opener=oversized)
