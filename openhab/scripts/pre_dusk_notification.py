"""Default-off pre-dusk forecast notification candidate; no listener or controls.

Callers must read the original persisted issue and its exact atomic SoC input.
This module performs no reads itself and does not change forecast publication.
Its dedicated outbox retains the same encrypted event across uncertain retries.
Relay acceptance is never labelled operator receipt or an action outcome.
"""
from datetime import date, timedelta
from hashlib import sha256
import json
import math
import time

from advisory_windows import trough_window
from pre_dusk_tuning import verify_issue_soc, ZONE
import thermal_confirmation as t
from thermal_messaging import require

RELEASE_READY = False
THRESHOLD_PCT = 30  # Existing full-bank notification policy; strictly below.
FIELDS = frozenset(('version', 'basis', 'predictionDay', 'issuedAt', 'sunsetAt',
                    'morningIssuedAt', 'socRecordedAt', 'socStreamEpoch',
                    'socEvidenceSha256', 'socAtIssuePct', 'overnightDropPct',
                    'overnightTroughSocPct'))


def notice(issue, original_soc, soc_persisted_at, now, sender, operator):
    """Validate a genuine issue input; return a deterministic rumor or no alert.

    ``original_soc`` must come from the exact original JDBC lookup, not a held
    current Item. Validation here cannot prove that the caller did that lookup.
    """
    now = t.aware(now)
    t.identifier(sender); t.identifier(operator)
    require(sender != operator, 'sender and operator must differ')
    require(isinstance(issue, dict) and set(issue) == FIELDS,
            'pre-dusk issue fields invalid')
    try:
        day = date.fromisoformat(issue['predictionDay'])
        issued = t.aware(issue['issuedAt'])
        sunset = t.aware(issue['sunsetAt'])
        morning = t.aware(issue['morningIssuedAt'])
        value, soc, drop = (issue[k] for k in
                            ('overnightTroughSocPct', 'socAtIssuePct', 'overnightDropPct'))
        target = trough_window(day, 'America/Denver')
        require(type(issue['version']) is int and issue['version'] == 1
                and issue['basis'] == 'atomic_soc_pre_dusk_v1'
                and day.isoformat() == issue['predictionDay']
                and issued.astimezone(ZONE).date() == day
                and sunset.astimezone(ZONE).date() == day
                and morning.astimezone(ZONE).date() == day
                and morning < issued <= now < target.end
                and 3600 <= (sunset - issued).total_seconds() < 5400,
                'pre-dusk issue origin or validity invalid')
        require(type(value) is int and type(soc) in (int, float)
                and type(drop) in (int, float) and math.isfinite(soc)
                and math.isfinite(drop) and 0 <= soc <= 100 and 1 <= drop <= 50
                and value == math.floor(max(12, min(99, soc - drop)) + 0.5),
                'pre-dusk issue calculation invalid')
        verify_issue_soc(issue, original_soc, soc_persisted_at)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise t.Refused('pre-dusk issue unavailable') from None
    if value >= THRESHOLD_PCT:
        return None
    rumor = {'kind': 14, 'pubkey': sender, 'created_at': int(issued.timestamp()),
             'tags': [['p', operator], ['x', sha256(t.canonical(issue)).hexdigest()]],
             'content': (f"🔋 Pre-dusk forecast: overnight SoC trough estimated at {value}% "
                         f"(below {THRESHOLD_PCT}%). Issued {issued.astimezone(ZONE):%b %d %H:%M %Z}; "
                         f"target through {target.end.astimezone(ZONE):%b %d %H:%M %Z}. "
                         "Forecast only, not a measured battery state or control instruction.")}
    rumor['id'] = t.event_id(rumor)
    return {'intent': 'pre-dusk-notice:' + day.isoformat(), 'rumor': rumor}


def queue(outbox, issue, original_soc, soc_persisted_at, now, sender, operator):
    require(RELEASE_READY, 'pre-dusk notification release is off')
    prepared = notice(issue, original_soc, soc_persisted_at, now, sender, operator)
    if prepared is None:
        return False
    outbox.queue(prepared['intent'], prepared['rumor'], sender, operator)
    return True


def flush(outbox, routes, keyer, relay, issue, original_soc, soc_persisted_at,
          now, sender, operator):
    """Retry only this exact, still-valid issue, preserving durable ciphertext.

    Production caller must hold the dedicated state lock throughout queue and
    flush. Revalidate the original issue on each invocation. No new wrapping is
    performed for a persisted envelope, including after an uncertain publish.
    """
    require(RELEASE_READY, 'pre-dusk notification release is off')
    prepared = notice(issue, original_soc, soc_persisted_at, now, sender, operator)
    counts = {'relay_acceptances': 0, 'retryable': 0, 'deferred': 0}
    if prepared is None:
        return counts
    body = t.canonical(prepared['rumor']).decode()
    rows = [row for row in outbox.rows() if row['intent'] == prepared['intent']]
    require(len(rows) == 2 and {row['target'] for row in rows} == {sender, operator},
            'pre-dusk outbox pair missing')
    require(all(row['body'] == body for row in rows), 'pre-dusk outbox issue changed')
    started = time.monotonic()
    for row in rows:
        approved = routes.for_recipient(row['target'])
        require(1 <= len(approved) <= 3, 'pre-dusk routes unavailable')
        remaining = set(approved) - set(json.loads(row['accepted']))
        if not remaining:
            continue
        if row['next_attempt'] > t.aware(now).timestamp():
            counts['deferred'] += 1
            continue
        try:
            event = outbox.ciphertext(row, keyer)
            for url in sorted(remaining):
                # Slow signing/publishing may cross the target's expiry.
                notice(issue, original_soc, soc_persisted_at,
                       t.aware(now) + timedelta(seconds=time.monotonic() - started), sender, operator)
                relay.publish(url, event)
                outbox.accepted(row, url)
                counts['relay_acceptances'] += 1
        except t.Retryable:
            outbox.retry(row, t.aware(now).timestamp())
            counts['retryable'] += 1
    return counts
