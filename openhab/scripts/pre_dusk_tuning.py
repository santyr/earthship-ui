"""Pure origin-paired scoring for morning and pre-dusk SoC trough issues.

The caller must obtain immutable as-issued receipts and the strict completed-
night assessment. This module has no database, Item, model, or control writes.
"""

from datetime import date, datetime, timezone
from hashlib import sha256
import math
import re
from uuid import UUID
from zoneinfo import ZoneInfo

from advisory_windows import trough_window


ZONE = ZoneInfo('America/Denver')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')


class PairUnavailable(ValueError):
    """The issues and outcome do not form one qualified comparison."""


def verify_issue_soc(pre_dusk, raw_evidence, persisted_at):
    """Match the late issue to the exact earlier persisted atomic SoC receipt.

    The caller must obtain ``raw_evidence`` from the original JDBC history,
    not a current held Item. This is issue-input provenance, not a night outcome.
    """
    from earthship_energy.bms_evidence import parse_evidence

    try:
        issue_at = _instant(pre_dusk['issuedAt'])
        stored_at = _instant(persisted_at)
        expected_recorded_at = _instant(pre_dusk['socRecordedAt'])
        expected_epoch = pre_dusk['socStreamEpoch']
        expected_digest = pre_dusk['socEvidenceSha256']
        expected_soc = pre_dusk['socAtIssuePct']
        if (not isinstance(raw_evidence, str) or not isinstance(expected_digest, str)
                or not DIGEST.fullmatch(expected_digest)
                or not _number(expected_soc)
                or sha256(raw_evidence.encode('utf-8')).hexdigest() != expected_digest
                or stored_at > issue_at):
            raise ValueError()
        record = parse_evidence(raw_evidence, stored_at)
        if (record is None or record.status != 'valid'
                or record.stream_epoch != expected_epoch
                or record.recorded_at != expected_recorded_at
                or record.soc != expected_soc
                or not record.recorded_at <= issue_at < record.valid_until):
            raise ValueError()
    except (KeyError, TypeError, ValueError, UnicodeError) as error:
        raise PairUnavailable('pre-dusk SoC source receipt unavailable') from error
    return True


def _instant(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise PairUnavailable('timestamp unavailable')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise PairUnavailable('timestamp invalid') from error
    if parsed.utcoffset() is None:
        raise PairUnavailable('timestamp lacks offset')
    return parsed.astimezone(timezone.utc)


def _number(value, lower=0, upper=100):
    return type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper


def score_pair(morning, pre_dusk, outcome):
    """Compare two genuine same-day issues against one qualified target night.

    Positive signed error means the forecast was above the measured trough;
    positive absolute-error improvement means pre-dusk was more accurate.
    This is observational accuracy only, never an advisory/action reward.
    """
    if not all(isinstance(value, dict) for value in (morning, pre_dusk, outcome)):
        raise PairUnavailable('issue or outcome unavailable')
    try:
        day = date.fromisoformat(morning['predictionDay'])
        if day.isoformat() != morning['predictionDay']:
            raise ValueError()
        window = trough_window(day, 'America/Denver')
        morning_at = _instant(morning['issuedAt'])
        late_at = _instant(pre_dusk['issuedAt'])
        sunset_at = _instant(pre_dusk['sunsetAt'])
        soc_at = _instant(pre_dusk['socRecordedAt'])
        soc_epoch = pre_dusk['socStreamEpoch']
        soc_evidence_digest = pre_dusk['socEvidenceSha256']
        if not isinstance(soc_epoch, str) or str(UUID(soc_epoch)) != soc_epoch:
            raise ValueError()
        claimed_morning_at = _instant(pre_dusk['morningIssuedAt'])
        assessed_at = _instant(outcome['assessed_at'])
        outcome_start = _instant(outcome['window_start'])
        outcome_end = _instant(outcome['window_end'])
        actual = outcome['min_soc_pct']
        observed_min = outcome['observed_min_soc_pct']
        morning_value = morning['overnightTroughSocPct']
        late_value = pre_dusk['overnightTroughSocPct']
        soc = pre_dusk['socAtIssuePct']
        drop = pre_dusk['overnightDropPct']
        coverage = outcome['coverage']
        digest = outcome['evidence_digest']
    except (KeyError, TypeError, ValueError) as error:
        raise PairUnavailable('issue or outcome fields invalid') from error
    if (type(morning.get('version')) is not int or morning['version'] != 1
            or type(pre_dusk.get('version')) is not int or pre_dusk['version'] != 1
            or pre_dusk.get('basis') != 'atomic_soc_pre_dusk_v1'
            or pre_dusk.get('predictionDay') != day.isoformat()
            or morning_at.astimezone(ZONE).date() != day
            or late_at.astimezone(ZONE).date() != day
            or sunset_at.astimezone(ZONE).date() != day
            or claimed_morning_at != morning_at
            or not morning_at < late_at < window.start
            or not 0 <= (late_at - soc_at).total_seconds() <= 120
            or not isinstance(soc_evidence_digest, str)
            or not DIGEST.fullmatch(soc_evidence_digest)
            or not 3600 <= (sunset_at - late_at).total_seconds() < 5400
            or type(morning_value) is not int or not _number(morning_value)
            or not _number(soc) or not _number(drop, 1, 50)
            or type(late_value) is not int
            or late_value != math.floor(max(12, min(99, soc - drop)) + 0.5)):
        raise PairUnavailable('forecast origin invalid')
    if (outcome.get('assessment_version') != 'atomic-soc-trough-v1'
            or outcome.get('source') != 'BMS_SOC_Evidence_JSON'
            or outcome.get('site_timezone') != 'America/Denver'
            or outcome.get('prediction_day') != day.isoformat()
            or outcome.get('status') != 'measured'
            or outcome_start != window.start or outcome_end != window.end
            or assessed_at < window.end
            or not _number(actual) or observed_min != actual
            or not _number(coverage, 0.9, 1)
            or not isinstance(digest, str) or not DIGEST.fullmatch(digest)):
        raise PairUnavailable('qualified completed-night outcome unavailable')
    morning_error = morning_value - actual
    late_error = late_value - actual
    return {
        'prediction_day': day.isoformat(),
        'morning_issued_at': morning_at.isoformat(),
        'pre_dusk_issued_at': late_at.isoformat(),
        'target_start': window.start.isoformat(),
        'target_end': window.end.isoformat(),
        'actual_trough_pct': actual,
        'morning_forecast_pct': morning_value,
        'pre_dusk_forecast_pct': late_value,
        'morning_signed_error_pp': morning_error,
        'pre_dusk_signed_error_pp': late_error,
        'absolute_error_improvement_pp': abs(morning_error) - abs(late_error),
        'coverage': coverage,
        'evidence_digest': digest,
        'causal_reward_proven': False,
    }
