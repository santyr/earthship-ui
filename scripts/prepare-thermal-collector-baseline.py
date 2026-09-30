#!/usr/bin/env python3
"""Stage an UNSENT v2 question proposal and an empty private collector baseline.

No journal connection, signing, queueing, relay request, listener or control.
The proposal is not an observation, approval, or production sending policy.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'openhab/scripts'))
import thermal_confirmation as t
import thermal_messaging as m
import thermal_state_backup as b
from thermal_model import action_history, airflow_migration, journal

C = m.collector_public_key('npub1qkjnsgk6zrszkmk2c7ywycvh46ylp3kw4kud8y8a20m93y5synvqewl0sq')
O = m.collector_public_key('npub1v60thnx0gz0wq3n6xdnq46y069l9x70xgmjp6lprdl6fv0eux6mqgjj4rp')


def require_gates_closed():
    flags = (action_history.V2_FETCH_RELEASE_READY, airflow_migration.RELEASE_READY,
             journal.V2_WRITE_RELEASE_READY, t.POSITION_INGRESS_RELEASE_READY,
             m.POSITION_DELIVERY_RELEASE_READY, m.POLL_RELEASE_READY)
    if any(flag is not False for flag in flags):
        raise t.Refused('baseline preparation requires all release gates closed')


def prepare(state, policy_path, routes_path, *, window, skylight, now=None, keyer=None):
    require_gates_closed()
    state, policy_path, routes_path = map(Path, (state, policy_path, routes_path))
    b._private_directory(state.parent)
    b._private_directory(policy_path.parent)
    if (state.exists() or state.is_symlink() or policy_path.exists() or policy_path.is_symlink()
            or policy_path.name != 'policy.proposed.json'):
        raise t.Refused('only new baseline and proposed policy paths are permitted')
    if window not in {'open', 'closed'} or skylight not in {'open', 'closed'}:
        raise t.Refused('invalid proposed opening state')
    now = t.aware(now or datetime.now(timezone.utc))
    draft = {'version': 2, 'recipient': C, 'operators': [O], 'prompts': [{
        'operator': O, 'issued_at': now.isoformat(), 'expires_at': (now+timedelta(hours=48)).isoformat(),
        'actions': {'window': window, 'skylight': skylight}}]}
    policy = t.Policy.load(t.canonical(draft), assign_ids=True)
    prompt = policy.prompts[0]
    raw = t.canonical({**draft, 'prompts': [{**draft['prompts'][0], 'id': prompt.event_id}]})+b'\n'
    t.Policy.load(raw)
    # Verify only public signatures; no key identity/signing operation here.
    m.Routes(m.read_private(routes_path), policy,
             keyer or m.Keyer(m.DEFAULT_NAK, m.DEFAULT_SHA256))
    require_gates_closed()
    state.mkdir(mode=0o700)
    with ExitStack() as stack:
        stack.enter_context(b.state_lock(state))
        spool, outbox = t.Spool(state), m.Outbox(state)
        stack.callback(spool.close)
        stack.callback(outbox.close)
        for database, tables in ((spool.db, ('receipts', 'terminal_prompts', 'corrections')),
                (outbox.db, ('delivery', 'inbox_ingested', 'inbox_refused'))):
            for table in tables:
                if database.execute('SELECT count(*) FROM '+table).fetchone()[0] != 0:
                    raise t.Refused('baseline is not empty')
        fd = os.open(policy_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
    if m.read_private(policy_path) != raw:
        raise t.Refused('proposed policy readback differs')
    return {'status': 'inactive_proposal_prepared', 'state_directory': str(state),
        'proposed_policy': str(policy_path), 'policy_sha256': sha256(raw).hexdigest(),
        'question_id': prompt.event_id, 'expires_at': prompt.expires_at.isoformat(),
        'proposed_states': dict(prompt.actions), 'baseline_rows': 0,
        'policy_review_required': True, 'publication': False, 'journal_writes': 0,
        'operator_confirmation': False, 'collector_activated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--routes', required=True, type=Path)
    parser.add_argument('--window', required=True, choices=['open', 'closed'])
    parser.add_argument('--skylight', required=True, choices=['open', 'closed'])
    args = parser.parse_args()
    try:
        result = prepare(args.state_dir, args.policy, args.routes,
                         window=args.window, skylight=args.skylight)
    except Exception as error:
        print(json.dumps({'status': 'withheld', 'error_type': type(error).__name__,
                          'state_directory': str(args.state_dir), 'collector_activated': False}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
