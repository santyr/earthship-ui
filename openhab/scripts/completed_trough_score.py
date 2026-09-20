"""Forecast adapter for observational completed-night assessment only."""
import os
from datetime import datetime, timezone


def _assess(environ):
    from earthship_energy.trough_runtime import run_assessment_process
    return run_assessment_process(environ)


def _publish(report, *, token, now):
    from earthship_energy.trough_publish import publish_trough_diagnostic
    return publish_trough_diagnostic(report, token=token, now=now)


def update_completed_trough_score(*, diagnostics, token_provider, put_unknown,
                                 environ=None, assessor=None, publisher=None, clock=None):
    """Never replay forecast actions; keep legacy arrays and learned state untouched."""
    env = os.environ if environ is None else environ
    if env.get("ADVISORY_ASSESS_ENABLED") != "1":
        put_unknown()
        diagnostics.append("completed trough: disabled; diagnostic unavailable")
        return "disabled"
    try:
        report = (assessor or _assess)(env)
        if not isinstance(report, dict) or report.get("status") != "complete":
            raise ValueError()
    except Exception:
        put_unknown()
        diagnostics.append("completed trough: assessment unavailable")
        return "assessment_unavailable"
    try:
        receipt = (publisher or _publish)(report, token=token_provider(),
            now=(clock or (lambda: datetime.now(timezone.utc)))())
    except Exception:
        # An ambiguous PUT must not be followed by another write in this run.
        diagnostics.append("completed trough: publication failed or unknown")
        return "publication_unknown"
    diagnostics.append(f"completed trough: accepted; samples={receipt['sample_count']}")
    return "accepted"
