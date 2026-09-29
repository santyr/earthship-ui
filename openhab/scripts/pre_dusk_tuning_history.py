"""Bounded, read-only OpenHAB JDBC archive transport for trough issue receipts.

The caller supplies an authenticated local OpenHAB GET function. This module
never reads a current Item state as historical evidence or writes anything.
"""

from datetime import date, datetime, time, timedelta, timezone
import json
import re
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo


ZONE = ZoneInfo('America/Denver')
MORNING_ITEM = 'Forecast_Prediction_Receipt_JSON'
PRE_DUSK_ITEM = 'Forecast_PreDusk_Trough_Receipt_JSON'
NUMERIC_ITEM = 'Predicted_SoC_Trough_PreDusk'
ALLOWED_ITEMS = frozenset((MORNING_ITEM, PRE_DUSK_ITEM))
TRANSPORT_ITEMS = ALLOWED_ITEMS | {NUMERIC_ITEM}
MAX_ROWS = 8
MAX_STATE_BYTES = 1024
MAX_RESPONSE_BYTES = 32768


class IssueHistoryUnavailable(ValueError):
    """The archive cannot establish an unambiguous issue history."""


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def local_get(path, *, token, opener=None):
    """GET only the three local JDBC history endpoints with a hard byte budget."""
    endpoint = path.split('?', 1)[0] if isinstance(path, str) else ''
    if (endpoint not in {f'/persistence/items/{item}' for item in TRANSPORT_ITEMS}
            or not isinstance(path, str) or '?' not in path
            or not isinstance(token, str) or not token.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in token)):
        raise IssueHistoryUnavailable('local archive request invalid')
    request = Request('http://127.0.0.1:8080/rest' + path,
                      headers={'Authorization': 'Bearer ' + token.strip()})
    try:
        with (opener or build_opener(ProxyHandler({}), _NoRedirects())).open(
                request, timeout=5) as response:
            if not 200 <= response.status < 300:
                raise ValueError('archive HTTP status invalid')
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('archive response too large')
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except Exception:
        # Never surface token-bearing transport diagnostics to a caller/log.
        raise IssueHistoryUnavailable('local archive request unavailable') from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate receipt key')
        result[key] = value
    return result


def _instant(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError('invalid issue timestamp')
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.utcoffset() is None:
        raise ValueError('issue timestamp lacks offset')
    return at.astimezone(timezone.utc)


def read_day_issues(get, *, item, day):
    """Return original persisted issue records for one local calendar day.

    A same-day rerun may yield multiple valid origins; callers must select an
    exact issue identity, never silently replace the morning origin with the
    latest current Item state.
    """
    if item not in ALLOWED_ITEMS or not isinstance(day, date) or isinstance(day, datetime):
        raise IssueHistoryUnavailable('exact Item and local date required')
    if not callable(get):
        raise IssueHistoryUnavailable('authenticated GET function required')
    start = datetime.combine(day, time.min, ZONE).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, ZONE).astimezone(timezone.utc)
    query = urlencode({
        'serviceId': 'jdbc',
        'starttime': start.isoformat().replace('+00:00', 'Z'),
        'endtime': end.isoformat().replace('+00:00', 'Z'),
    })
    try:
        payload = get(f'/persistence/items/{item}?{query}')
        count = payload.get('datapoints') if isinstance(payload, dict) else None
        # OpenHAB REST serializes this integer as a decimal string on the
        # installed runtime; accept only that exact bounded representation.
        if isinstance(count, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', count):
            count = int(count)
        if (not isinstance(payload, dict) or payload.get('name') != item
                or type(count) is not int
                or not isinstance(payload.get('data'), list)
                or count != len(payload['data'])
                or len(payload['data']) > MAX_ROWS):
            raise ValueError('archive metadata invalid')
        result = []
        previous = None
        for row in payload['data']:
            if not isinstance(row, dict) or set(row) != {'time', 'state'}:
                raise ValueError('archive row invalid')
            millis = row['time']
            raw = row['state']
            if (type(millis) is not int or not isinstance(raw, str)
                    or not 1 <= len(raw.encode('utf-8')) <= MAX_STATE_BYTES):
                raise ValueError('archive row type or size invalid')
            persisted = datetime.fromtimestamp(millis / 1000, timezone.utc)
            if not start <= persisted < end or (previous is not None and persisted <= previous):
                raise ValueError('archive row timestamp invalid')
            previous = persisted
            receipt = json.loads(raw, object_pairs_hook=_unique_object,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
            if (not isinstance(receipt, dict) or type(receipt.get('version')) is not int
                    or receipt['version'] != 1 or receipt.get('predictionDay') != day.isoformat()):
                raise ValueError('receipt identity invalid')
            issued = _instant(receipt.get('issuedAt'))
            if (issued.astimezone(ZONE).date() != day
                    or not 0 <= (persisted - issued).total_seconds() <= 600):
                raise ValueError('receipt issue/persistence ordering invalid')
            result.append({'persisted_at': persisted.isoformat(), 'receipt': receipt})
        return result
    except (KeyError, TypeError, ValueError, OverflowError, OSError) as error:
        raise IssueHistoryUnavailable('issue history unavailable') from error


def read_numeric_day(get, *, day):
    """Read bounded, original same-day numeric trough writes, not current state."""
    if not isinstance(day, date) or isinstance(day, datetime) or not callable(get):
        raise IssueHistoryUnavailable('local date and authenticated GET required')
    start = datetime.combine(day, time.min, ZONE).astimezone(timezone.utc)
    end = datetime.combine(day + timedelta(days=1), time.min, ZONE).astimezone(timezone.utc)
    query = urlencode({'serviceId': 'jdbc',
                       'starttime': start.isoformat().replace('+00:00', 'Z'),
                       'endtime': end.isoformat().replace('+00:00', 'Z')})
    try:
        payload = get(f'/persistence/items/{NUMERIC_ITEM}?{query}')
        count = payload.get('datapoints') if isinstance(payload, dict) else None
        if isinstance(count, str) and re.fullmatch(r'0|[1-9][0-9]{0,2}', count):
            count = int(count)
        if (not isinstance(payload, dict) or payload.get('name') != NUMERIC_ITEM
                or type(count) is not int or not isinstance(payload.get('data'), list)
                or count != len(payload['data']) or len(payload['data']) > MAX_ROWS):
            raise ValueError('numeric archive metadata invalid')
        result = []
        previous = None
        for row in payload['data']:
            if not isinstance(row, dict) or set(row) != {'time', 'state'}:
                raise ValueError('numeric archive row invalid')
            millis, raw = row['time'], row['state']
            if (type(millis) is not int or not isinstance(raw, str)
                    or not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})(?:\.0+)?', raw)):
                raise ValueError('numeric archive value invalid')
            at = datetime.fromtimestamp(millis / 1000, timezone.utc)
            if (not start <= at < end or (previous is not None and at <= previous)
                    or not 0 <= float(raw) <= 100):
                raise ValueError('numeric archive timestamp or range invalid')
            previous = at
            result.append({'persisted_at': at.isoformat(), 'value': int(float(raw))})
        return result
    except (TypeError, ValueError, OverflowError, OSError) as error:
        raise IssueHistoryUnavailable('numeric issue history unavailable') from error


def select_pair(morning_rows, pre_dusk_rows):
    """Select only the morning issue explicitly referenced by one late issue."""
    try:
        if not isinstance(morning_rows, list) or not isinstance(pre_dusk_rows, list):
            raise ValueError('archive rows invalid')
        if len(pre_dusk_rows) != 1:
            raise ValueError('one natural pre-dusk issue required')
        late = pre_dusk_rows[0]['receipt']
        linked = _instant(late['morningIssuedAt'])
        matches = [row['receipt'] for row in morning_rows
                   if _instant(row['receipt']['issuedAt']) == linked]
        if len(matches) != 1:
            raise ValueError('exact morning issue unavailable')
        return matches[0], late
    except (KeyError, TypeError, ValueError) as error:
        raise IssueHistoryUnavailable('paired issue history unavailable') from error
