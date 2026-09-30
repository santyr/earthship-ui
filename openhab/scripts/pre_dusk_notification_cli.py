#!/usr/bin/env python3
"""Read-only pre-dusk source check or separately release-gated delivery.

No historical clock override, prompt, listener, journal write or control call.
The existing Hex identity signs; the approved operator is the recipient.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path

import pre_dusk_notification as notification
from pre_dusk_notification_source import read_notice
from pre_dusk_notification_worker import run
from pre_dusk_tuning import ZONE
from pre_dusk_tuning_history import local_get
from openhab_sanity_check import token
import thermal_confirmation as t
from thermal_messaging import (
    DEFAULT_NAK, DEFAULT_SHA256, Keyer, Relay, Routes,
    collector_public_key, read_private, require,
)

SENDER = collector_public_key('npub1qkjnsgk6zrszkmk2c7ywycvh46ylp3kw4kud8y8a20m93y5synvqewl0sq')
OPERATOR = collector_public_key('npub1v60thnx0gz0wq3n6xdnq46y069l9x70xgmjp6lprdl6fv0eux6mqgjj4rp')
JDBC = Path('/home/sat/.config/hex/energy-power-reader.jdbc')
STATE = Path('/home/sat/.local/state/hex/pre-dusk-notifications')
ROUTES = Path('/home/sat/.config/hex/pre-dusk-notification-routes.json')


def restricted_connection():
    import psycopg2
    from earthship_energy.db import parse_openhab_jdbc_config
    # Validate the private host file before parsing it. No DSN is printed.
    read_private(JDBC)
    settings = parse_openhab_jdbc_config(JDBC)
    require((settings.host, settings.port, settings.dbname, settings.user) ==
            ('127.0.0.1', 5432, 'openhab', 'energy_power_reader'),
            'restricted local source reader required')
    return lambda: psycopg2.connect(**settings.connect_kwargs, connect_timeout=3,
        options='-c default_transaction_read_only=on -c statement_timeout=3000')


def active_day(now):
    local = t.aware(now).astimezone(ZONE)
    return local.date() - timedelta(days=1) if local.hour < 11 else local.date()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-source', action='store_true')
    mode.add_argument('--deliver', action='store_true')
    parser.add_argument('--day', type=date.fromisoformat,
                        help='read-only check date; actual current clock still applies')
    args = parser.parse_args(argv)
    try:
        if args.deliver:
            require(notification.RELEASE_READY, 'pre-dusk notification release is off')
            require(args.day is None, 'delivery cannot override the active date')
        now = datetime.now(timezone.utc)
        day = args.day or active_day(now)
        auth = token()
        get = lambda path: local_get(path, token=auth)
        connect = restricted_connection()
        if args.check_source:
            prepared = read_notice(get, connect, day=day, now=now,
                                   sender=SENDER, operator=OPERATOR)
            result = {'status': 'qualified_source', 'prediction_day': day.isoformat(),
                      'notification_eligible': prepared is not None,
                      'outbox_writes': 0, 'message_published': False,
                      'identity_qualified': False, 'operator_read_verified': False}
        else:
            keyer = Keyer(DEFAULT_NAK, DEFAULT_SHA256)
            # Empty policy scopes only the reviewed signed relay inventory;
            # it creates no prompt and is never passed to thermal Delivery.
            policy = t.Policy(SENDER, frozenset((OPERATOR,)), ())
            routes = Routes(read_private(ROUTES), policy, keyer)
            result = run(get, connect, day=day, state_dir=STATE, routes=routes,
                keyer=keyer, relay=Relay(keyer, SENDER), sender=SENDER, operator=OPERATOR)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 3 if result.get('retryable') or result.get('deferred') else 0
    except Exception:
        # No secret, source JSON, signing connection or raw exception is logged.
        print('{"status":"withheld","reason":"pre-dusk notification unavailable"}')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
