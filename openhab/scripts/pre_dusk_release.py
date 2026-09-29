"""Read-only first-natural-issue gate for the display-only pre-dusk forecast."""

from datetime import date, datetime, timezone
import math

from pre_dusk_tuning_history import (MORNING_ITEM, PRE_DUSK_ITEM, ZONE,
    IssueHistoryUnavailable, read_day_issues, read_numeric_day, select_pair)


class NaturalIssueUnavailable(ValueError):
    """The natural issue, numeric write or original SoC input is unqualified."""


def _instant(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('bounded aware timestamp required')
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if at.utcoffset() is None:
        raise ValueError('aware timestamp required')
    return at.astimezone(timezone.utc)


def qualify_day(get, source_reader, *, day, now):
    """Verify as-issued receipt, numeric history and exact source; never run it.

    `source_reader` must use a dedicated read-only snapshot of the original
    atomic-SoC JDBC table. This gate does not score the coming night or claim
    that a browser has rendered the value.
    """
    if (not isinstance(day, date) or isinstance(day, datetime)
            or not isinstance(now, datetime) or now.utcoffset() is None
            or not callable(get) or not callable(source_reader)
            or day > now.astimezone(ZONE).date()):
        raise NaturalIssueUnavailable('valid local day and readers required')
    try:
        mornings = read_day_issues(get, item=MORNING_ITEM, day=day)
        late_rows = read_day_issues(get, item=PRE_DUSK_ITEM, day=day)
        if not late_rows:
            return {'status': 'pending_natural_issue' if day == now.astimezone(ZONE).date()
                    else 'missing_natural_issue', 'prediction_day': day.isoformat(),
                    'morning_issue_count': len(mornings), 'pre_dusk_issue_count': 0,
                    'display_selection_verified': False}
        morning, late = select_pair(mornings, late_rows)
        numbers = read_numeric_day(get, day=day)
        if len(numbers) != 1:
            raise ValueError('one natural numeric write required')
        morning_at, issued_at = _instant(morning['issuedAt']), _instant(late['issuedAt'])
        sunset_at, soc_at = _instant(late['sunsetAt']), _instant(late['socRecordedAt'])
        numeric_at = _instant(numbers[0]['persisted_at'])
        value = late['overnightTroughSocPct']
        soc, drop = late['socAtIssuePct'], late['overnightDropPct']
        if (late.get('basis') != 'atomic_soc_pre_dusk_v1'
                or not morning_at < issued_at <= now.astimezone(timezone.utc)
                or sunset_at.astimezone(ZONE).date() != day
                or not 3600 <= (sunset_at-issued_at).total_seconds() < 5400
                or not 0 <= (issued_at-soc_at).total_seconds() <= 120
                or not 0 <= (numeric_at-issued_at).total_seconds() <= 600
                or type(soc) not in (int, float) or not math.isfinite(soc)
                or not 0 <= soc <= 100
                or type(drop) not in (int, float) or not math.isfinite(drop)
                or not 1 <= drop <= 50
                or type(value) is not int
                or value != math.floor(max(12, min(99, soc-drop)) + 0.5)
                or numbers[0]['value'] != value):
            raise ValueError('pre-dusk source, timing or value mismatch')
        source = source_reader(late)
        if (not isinstance(source, dict)
                or source.get('source_item') != 'BMS_SOC_Evidence_JSON'
                or source.get('source_stream_epoch') != late['socStreamEpoch']
                or source.get('source_digest_sha256') != late['socEvidenceSha256']
                or _instant(source.get('source_persisted_at')) > issued_at):
            raise ValueError('atomic source qualification missing')
        return {'status': 'qualified_natural_issue',
                'prediction_day': day.isoformat(),
                'morning_issued_at': morning_at.isoformat(),
                'pre_dusk_issued_at': issued_at.isoformat(),
                'pre_dusk_persisted_at': late_rows[0]['persisted_at'],
                'numeric_persisted_at': numbers[0]['persisted_at'],
                'trough_soc_pct': value,
                'source_item': source['source_item'],
                'source_persisted_at': source['source_persisted_at'],
                'source_stream_epoch': source['source_stream_epoch'],
                'source_digest_sha256': source['source_digest_sha256'],
                'display_selection_verified': False,
                'night_outcome_scored': False}
    except (IssueHistoryUnavailable, KeyError, TypeError, ValueError, OverflowError):
        raise NaturalIssueUnavailable('pre-dusk natural issue unavailable') from None
