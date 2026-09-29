"""Natural publication is qualified from archives, not a manual timer run."""

from datetime import date, datetime, timedelta, timezone
import json

import pytest

from pre_dusk_release import NaturalIssueUnavailable, qualify_day
from pre_dusk_tuning_history import MORNING_ITEM, PRE_DUSK_ITEM, NUMERIC_ITEM


DAY = date(2026, 9, 29)
MORNING = {'version': 1, 'predictionDay': DAY.isoformat(),
    'issuedAt': '2026-09-29T06:40:17-06:00', 'overnightTroughSocPct': 53}
LATE = {'version': 1, 'basis': 'atomic_soc_pre_dusk_v1',
    'predictionDay': DAY.isoformat(), 'issuedAt': '2026-09-29T17:30:00-06:00',
    'sunsetAt': '2026-09-29T18:48:23-06:00',
    'morningIssuedAt': MORNING['issuedAt'],
    'socRecordedAt': '2026-09-29T17:29:40-06:00',
    'socStreamEpoch': '123e4567-e89b-42d3-a456-426614174000',
    'socEvidenceSha256': 'a'*64, 'socAtIssuePct': 99,
    'overnightDropPct': 18, 'overnightTroughSocPct': 81}
NOW = datetime(2026, 9, 30, 0, 5, tzinfo=timezone.utc)


def history(receipt, seconds):
    at = datetime.fromisoformat(receipt['issuedAt']).astimezone(timezone.utc)
    return {'time': int((at + timedelta(seconds=seconds)).timestamp()*1000),
            'state': json.dumps(receipt)}


def archive(*, morning=(MORNING,), late=(LATE,), numeric=('81',)):
    issue = datetime.fromisoformat(LATE['issuedAt']).astimezone(timezone.utc)
    rows = {
        MORNING_ITEM: [history(value, 2) for value in morning],
        PRE_DUSK_ITEM: [history(value, 3) for value in late],
        NUMERIC_ITEM: [{'time': int((issue + timedelta(seconds=1+i)).timestamp()*1000),
                        'state': value} for i, value in enumerate(numeric)],
    }
    calls = []
    def get(path):
        item = path.split('?', 1)[0].rsplit('/', 1)[-1]
        calls.append(item)
        return {'name': item, 'datapoints': str(len(rows[item])), 'data': rows[item]}
    return get, calls


def source(_):
    return {'source_item': 'BMS_SOC_Evidence_JSON',
        'source_persisted_at': '2026-09-29T23:29:45+00:00',
        'source_stream_epoch': LATE['socStreamEpoch'],
        'source_digest_sha256': LATE['socEvidenceSha256']}


def test_pending_does_not_query_numeric_or_source():
    get, calls = archive(late=(), numeric=())
    result = qualify_day(get, lambda _: pytest.fail('source must not be read'),
                         day=DAY, now=datetime(2026, 9, 29, 21, tzinfo=timezone.utc))
    assert result['status'] == 'pending_natural_issue'
    assert calls == [MORNING_ITEM, PRE_DUSK_ITEM]
    assert result['display_selection_verified'] is False


def test_exact_archived_issue_numeric_and_source_qualify_without_ui_claim():
    get, calls = archive()
    result = qualify_day(get, source, day=DAY, now=NOW)
    assert result['status'] == 'qualified_natural_issue'
    assert result['trough_soc_pct'] == 81
    assert result['source_item'] == 'BMS_SOC_Evidence_JSON'
    assert result['display_selection_verified'] is False
    assert result['night_outcome_scored'] is False
    assert calls == [MORNING_ITEM, PRE_DUSK_ITEM, NUMERIC_ITEM]


@pytest.mark.parametrize('changes', [
    {'numeric': ()},
    {'numeric': ('80',)},
    {'numeric': ('81', '81')},
    {'late': (LATE, LATE)},
    {'late': ({**LATE, 'overnightTroughSocPct': 80},)},
    {'late': ({**LATE, 'morningIssuedAt': '2026-09-29T06:41:00-06:00'},)},
])
def test_incomplete_or_conflicting_natural_history_refuses(changes):
    get, _ = archive(**changes)
    with pytest.raises(NaturalIssueUnavailable):
        qualify_day(get, source, day=DAY, now=NOW)


def test_source_reader_must_return_exact_atomic_source():
    get, _ = archive()
    with pytest.raises(NaturalIssueUnavailable):
        qualify_day(get, lambda _: {'source_item': 'BMS_SOC'}, day=DAY, now=NOW)
    with pytest.raises(NaturalIssueUnavailable):
        qualify_day(get, lambda _: {**source(LATE), 'source_digest_sha256': 'b'*64},
                    day=DAY, now=NOW)
