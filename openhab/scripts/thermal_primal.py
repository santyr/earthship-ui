#!/usr/bin/env python3
"""Explicit, bounded Primal thermal command. No automatic transport fallback.

Read-only configuration and local signer challenges are separate from the
release-gated sender/poller. Secrets are supplied only through private service
credentials/environment, never command arguments. No actuator commands.
"""
import argparse
from contextlib import ExitStack
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import secrets
import sqlite3
import sys

import thermal_confirmation as t
import thermal_messaging as m
import thermal_nip04 as n
import thermal_state_backup as b


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # Even mistaken secret-bearing arguments must not reach diagnostics.
        self.exit(2, 'thermal Primal arguments refused; see --help\n')


def utc_now():
    return datetime.now(timezone.utc)


def read_private(path):
    m.require(path is not None and path.is_absolute() and path.resolve() == path,
              'explicit non-symlink configuration path required')
    b._private_directory(path.parent)
    return m.read_private(path)


def configuration(args):
    m.require(all(value is not None for value in (
        args.policy, args.routes, args.nak, args.nak_sha256, args.nak_version)),
        'explicit policy, routes and qualified signer identity required')
    # An explicitly idle v2 collector must not require a fabricated question.
    # This opts in only here; legacy/general policy loading remains unchanged.
    policy = t.Policy.load(read_private(args.policy), allow_empty=True)
    m.require(policy.version == 2, 'Primal command requires position vocabulary v2')
    keyer = m.Keyer(args.nak, args.nak_sha256)
    m.require(isinstance(args.nak_version, str) and 0 < len(args.nak_version) <= 128,
              'explicit signer version required')
    version = keyer.call(['--version']).decode('utf-8').strip()
    m.require(version == args.nak_version, 'signer version mismatch')
    routes = m.Routes(read_private(args.routes), policy, keyer)
    return policy, routes, keyer


def check_primal_identity(keyer, collector):
    """Local self-roundtrip, not an operator response or a published event."""
    codec = n.Nip04Codec(keyer)
    challenge = 'Earthship Primal keyer self-check ' + secrets.token_hex(16)
    event = codec.encode(challenge, author=collector, recipient=collector,
                         created_at=int(utc_now().timestamp()))
    decoded = codec.decode(t.canonical(event), recipient=collector,
                           authors=frozenset({collector}))
    m.require(decoded.plaintext == challenge and decoded.event_id == event['id'],
              'Primal keyer self-roundtrip mismatch')
    # Preserve the independent existing NIP-17 signer contract as well.
    keyer.check_identity(collector)
    return {'version': 1, 'status': 'passed', 'transport': 'nip04',
            'scope': 'local-primal-and-nip17-keyer-self-roundtrips',
            'signer_identity_verified': True, 'stdin_encoding_verified': True,
            'nak_sha256': keyer.digest, 'journal_writes': 0,
            'message_published': False, 'operator_read_verified': False}


def main(argv=None):
    parser = Parser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ('check-config', 'check-keyer', 'send-prompts', 'process-reply',
                 'poll-replies', 'flush', 'follow-recommendations'):
        modes.add_argument('--' + name, action='store_true')
    parser.add_argument('--policy', type=Path)
    parser.add_argument('--routes', type=Path)
    parser.add_argument('--state-dir', type=Path)
    parser.add_argument('--event-file', type=Path)
    parser.add_argument('--followup-config', type=Path,
                        help='private immutable activation/bank and daily-limit policy')
    parser.add_argument('--nak', type=Path)
    parser.add_argument('--nak-sha256')
    parser.add_argument('--nak-version')
    parser.add_argument('--relay-auth', action='store_true',
                        help='explicit NIP-42 identity disclosure on approved relays')
    args = parser.parse_args(argv)
    try:
        if not (args.check_config or args.check_keyer):
            n.require_release()  # Before config reads, signing, locks or state.
        followup = None
        if args.follow_recommendations or args.followup_config is not None:
            import thermal_followup as followup
            if args.follow_recommendations:
                followup.require_release()  # Still before private config, signing or state.
            m.require(args.follow_recommendations or args.check_config or args.check_keyer,
                      'follow-up settings require explicitly selected recurring mode')
            settings = followup.load_configuration(read_private(args.followup_config), now=utc_now())
            followup.reader_dsn()  # Validate separate credential before opening state.
        policy, routes, keyer = configuration(args)
        if followup is not None:
            followup._authority(policy)
        if args.check_config:
            print(t.canonical({'version': 1, 'status': 'passed', 'transport': 'nip04',
                'scope': 'private-policy-and-signed-routes-only',
                'signed_routes_verified': True, 'signer_identity_verified': False,
                'journal_writes': 0, 'message_published': False,
                'release_enabled': n.PRIMAL_RELEASE_READY}).decode())
            return 0
        identity = check_primal_identity(keyer, policy.recipient)
        if args.check_keyer:
            print(t.canonical(identity).decode())
            return 0
        m.require(args.state_dir is not None and args.state_dir.is_absolute()
                  and args.state_dir.resolve() == args.state_dir,
                  'explicit non-symlink state directory required')
        raw = read_private(args.event_file) if args.process_reply else None
        sink = t.JournalSink()
        sink.require_v2_storage()  # Before creating any SQLite or lock file.
        with ExitStack() as stack:
            stack.enter_context(b.state_lock(args.state_dir))
            ledger = n.PrimalLedger(args.state_dir)
            stack.callback(ledger.close)
            outbox = n.PrimalOutbox(args.state_dir)
            stack.callback(outbox.close)
            followup_counts = {}
            automatic = ()
            if args.follow_recommendations:
                followup.initialize(ledger.db)
                followup.pin_configuration(ledger.db, settings, policy=policy)
                policy = followup.combined_policy(ledger.db, policy=policy)
                try:
                    observed_at = utc_now()
                    rows = followup.read_publications(settings, now=observed_at)
                    candidate = followup.select_followup(rows, now=observed_at,
                        activated_at=t.aware(settings['activated_at']), bank_epoch=settings['bank_epoch'])
                    reserved = followup.reserve_followup(ledger.db, candidate, policy=policy, now=utc_now())
                    followup_counts['followup_status'] = 'reserved_or_retained' if reserved else 'idle'
                except t.Retryable:
                    # Evidence outages withhold new questions, not authenticated
                    # replies and ACK recovery for already retained questions.
                    followup_counts.update(followup_status='reader_unavailable', followup_retryable=1)
                except t.Refused:
                    followup_counts.update(followup_status='evidence_withheld', followup_withheld=1)
                automatic = followup.retained_prompts(ledger.db, policy=policy)
                policy = followup.combined_policy(ledger.db, policy=policy)
            delivery = n.PrimalDelivery(policy, routes, ledger, outbox,
                n.Nip04Codec(keyer), n.PrimalRelay(keyer, policy.recipient,
                    policy.operators, auth=args.relay_auth), sink)
            if args.send_prompts:
                delivery.queue_prompts(utc_now())
            if args.follow_recommendations:
                # Never auto-send an unqueued separately reviewed/manual prompt.
                # Recover original reserved ciphers, including a crash between
                # reservation and the existing ledger/outbox commits.
                sender = n.PrimalDelivery(replace(policy, prompts=automatic), routes, ledger, outbox,
                    delivery.codec, delivery.relay, sink)
                sender.queue_prompts(utc_now())
            if raw is not None:
                delivery.receive(raw, utc_now())
            # Do not freeze publication authority or first receipt time at
            # command start. Each event/route must use its actual current time.
            polled = delivery.poll_replies() if args.poll_replies or args.follow_recommendations else {}
            recovered = delivery.recover_acks()
            result = delivery.flush()
            for counts in (recovered, polled):
                for name, value in counts.items():
                    result[name] = result.get(name, 0) + value
            if args.poll_replies or args.follow_recommendations:
                result['inbox_refusals'] = outbox.refusal_status(utc_now().timestamp())
            result.update(followup_counts)
            result.update(version=1, transport='nip04', operator_read_verified=False)
            print(t.canonical(result).decode())
            return (3 if result['retryable'] or result['deferred'] or result.get('relay_failures')
                    or result.get('followup_retryable')
                    else 2 if result['withheld'] or result.get('followup_withheld') else 0)
    except t.Refused:
        print('thermal Primal refused; release, identity or configuration not qualified', file=sys.stderr)
        return 2
    except (t.Retryable, OSError, sqlite3.Error, ImportError, ValueError, KeyError):
        print('thermal Primal incomplete; retained state requires retry or repair', file=sys.stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(main())
