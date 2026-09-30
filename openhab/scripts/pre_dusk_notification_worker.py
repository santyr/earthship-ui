"""Default-off locked notification worker, without CLI or automatic activation.

Transport/keyer/routes must be provisioned and qualified by the deployment
adapter. This module never creates a thermal prompt, listener or journal row.
"""
from datetime import datetime, timezone

import pre_dusk_notification as notification
from pre_dusk_notification_source import _read_inputs
from thermal_messaging import Outbox, require
from thermal_state_backup import state_lock


def run(get, connection_factory, *, day, state_dir, routes, keyer, relay,
        sender, operator, now=None):
    """Hold the dedicated private state lock across read/queue/flush.

    ``now`` is a deterministic disconnected-test clock. A production adapter
    must not expose it as a CLI override; live invocations use the actual clock.
    Relay acceptance counters are not operator-receipt or action evidence.
    """
    require(notification.RELEASE_READY, 'pre-dusk notification release is off')
    clock = (lambda: now) if now is not None else (lambda: datetime.now(timezone.utc))
    with state_lock(state_dir):
        issue, original, prepared = _read_inputs(get, connection_factory,
            day=day, now=clock(), sender=sender, operator=operator)
        if prepared is None:
            return {'status': 'not_eligible', 'relay_acceptances': 0,
                    'retryable': 0, 'deferred': 0, 'operator_read_verified': False}
        # Check both signed route scopes and the configured signer before opening
        # or mutating the delivery database. This does not verify operator receipt.
        routes.for_recipient(sender)
        routes.for_recipient(operator)
        keyer.check_identity(sender)
        box = Outbox(state_dir)
        try:
            args = (issue, original['original_soc'],
                    original['metadata']['source_persisted_at'])
            notification.queue(box, *args, clock(), sender, operator)
            counts = notification.flush(box, routes, keyer, relay,
                                         *args, clock(), sender, operator)
            return {'status': 'delivery_checked', **counts, 'operator_read_verified': False}
        finally:
            box.close()
