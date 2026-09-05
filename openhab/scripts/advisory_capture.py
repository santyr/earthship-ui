"""Default-off, bounded observational capture; never owns forecast side effects."""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from advisory_records import build_decision_record, build_result_record

POLICY_VERSION = "forecast-intel-thermal-v1"


def _make_store(dsn):
    from earthship_energy.advisory_store import AdvisoryStore
    return AdvisoryStore(dsn)


class _Capture:
    def __init__(self, store, decision_id, diagnostics, clock, identity_factory):
        self.store, self.decision_id = store, decision_id
        self.diagnostics, self.clock = diagnostics, clock
        self.identity_factory = identity_factory

    def _result(self, kind, target, status):
        try:
            encoded = build_result_record(result_id=self.identity_factory(),
                decision_id=self.decision_id, observed_at=self.clock(),
                kind=kind, target=target, status=status)
            self.store.put_result(encoded)
        except Exception:
            self.diagnostics.append("advisory capture gap: result")

    def publication(self, target, status):
        self._result("publication", target, status)

    def notification(self, status):
        self._result("notification", "deep_cycle_dm", status)


def start_capture(*, decision, diagnostics, source_path, environ=None,
                  store_factory=None, clock=None, identity_factory=None):
    env = os.environ if environ is None else environ
    if env.get("ADVISORY_CAPTURE_ENABLED") != "1":
        return None
    try:
        clock = clock or (lambda: datetime.now(timezone.utc))
        identity_factory = identity_factory or uuid4
        decision_id = identity_factory()
        encoded = build_decision_record(**decision, decision_id=decision_id,
            issued_at=clock(), source_revision=hashlib.sha256(Path(source_path).read_bytes()).hexdigest(),
            policy_version=POLICY_VERSION, bank_epoch=env["ADVISORY_CAPTURE_BANK_EPOCH"])
        store = (store_factory or _make_store)(env["ADVISORY_CAPTURE_DSN"])
        store.put_decision(encoded)
        return _Capture(store, decision_id, diagnostics, clock, identity_factory)
    except Exception:
        diagnostics.append("advisory capture gap: decision")
        return None
