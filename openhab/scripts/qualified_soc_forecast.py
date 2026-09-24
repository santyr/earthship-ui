"""Read-only, atomic-SoC inputs for the forecast's energy calculations.

Numeric BMS_SOC JDBC rows are change-only and cannot prove night coverage or
current freshness. This adapter uses the same evidence and bank epoch as the
daily energy and completed-night outcome readers. It never writes Items.
"""

from datetime import date, datetime, timedelta, timezone
import os


def current_valid_soc(raw, now):
    """Return a currently valid atomic SoC, or None; never carry expired state."""
    from earthship_energy.bms_evidence import parse_evidence

    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("current SoC requires an aware clock")
    instant = now.astimezone(timezone.utc)
    record = parse_evidence(raw, instant)
    if (record is None or record.status != "valid"
            or not record.recorded_at <= instant < record.valid_until):
        return None
    return record.soc


def completed_night_troughs(ending_days, *, now, site_timezone, environ=None):
    """Return only fully qualified measured minima keyed by local ending day.

    A single bounded read-only DB session covers at most four nights. An absent
    or ambiguous mapping, missing physical bank boundary, coverage below 90%,
    incomplete night, or any transport failure yields no number for that night.
    The caller must not substitute legacy change-only numeric persistence.
    """
    from advisory_windows import trough_window
    from earthship_energy.advisory_store import AdvisoryStore
    from earthship_energy.materialize import load_epoch_config
    from earthship_energy.reader import fetch_freshness_observations
    from earthship_energy.series import local_day_bounds
    from earthship_energy.trough_assessment import assess_trough_measurement, MAX_OBSERVATIONS
    import psycopg2

    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("completed troughs require an aware clock")
    if (not isinstance(ending_days, (list, tuple)) or len(ending_days) > 4
            or any(not isinstance(day, date) or isinstance(day, datetime) for day in ending_days)
            or len(set(ending_days)) != len(ending_days)):
        raise ValueError("at most four distinct ending dates are allowed")
    env = os.environ if environ is None else environ
    if (env.get("ADVISORY_ASSESS_ENABLED") != "1"
            or env.get("ADVISORY_ASSESS_TIMEZONE") != site_timezone
            or not env.get("ADVISORY_ASSESS_DSN")
            or not env.get("ADVISORY_ASSESS_BANK_EPOCH")
            or env.get("PGSERVICE") or env.get("PGSERVICEFILE")):
        return {}
    bank = next((epoch for epoch in load_epoch_config()
                 if epoch.epoch_id == env["ADVISORY_ASSESS_BANK_EPOCH"]
                 and epoch.current_analytics), None)
    if bank is None or bank.start_local_date is None:
        return {}
    bank_start = local_day_bounds(bank.start_local_date, site_timezone)[0]
    bank_end = (local_day_bounds(bank.end_local_date_exclusive, site_timezone)[0]
                if bank.end_local_date_exclusive is not None else None)
    complete = [(day, trough_window(day - timedelta(days=1), site_timezone))
                for day in ending_days]
    complete = [(day, window) for day, window in complete if window.is_complete(now)]
    if not complete:
        return {}

    store = AdvisoryStore(env["ADVISORY_ASSESS_DSN"])
    connection = psycopg2.connect(
        store._dsn, hostaddr=store._hostaddr, sslmode="disable", connect_timeout=3,
        options="-c default_transaction_read_only=on -c statement_timeout=2000 "
                "-c lock_timeout=1000 -c idle_in_transaction_session_timeout=5000",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2",
                           ("BMS_SOC_Evidence_JSON",))
            matches = cursor.fetchall()
        if len(matches) != 1 or type(matches[0][0]) is not int or matches[0][0] < 0:
            return {}
        table = f"item{matches[0][0]:04d}"
        result = {}
        for day, window in complete:
            rows = fetch_freshness_observations(
                connection, table, window.start - timedelta(seconds=120), window.end,
                row_limit=MAX_OBSERVATIONS + 1,
            )
            measurement = assess_trough_measurement(
                prediction_day=day - timedelta(days=1), site_timezone=site_timezone,
                assessed_at=now, observations=rows, epoch_start=bank_start,
                epoch_end=bank_end,
            )
            if measurement["status"] == "measured":
                result[day] = measurement["min_soc_pct"]
        return result
    finally:
        connection.close()
