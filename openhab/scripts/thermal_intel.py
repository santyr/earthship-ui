#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from thermal_model.actions import parse_thermal_message
from thermal_model.journal import ActionJournal


def _aware_iso(value):
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include timezone information")
    return parsed


def _build_parser():
    parser = argparse.ArgumentParser(description="Local thermal intelligence tooling")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)
    journal = subparsers.add_parser("journal", help="append one local THERMAL message")
    journal.add_argument("--message-file", required=True, type=Path)
    journal.add_argument("--idempotency-key", required=True)
    journal.add_argument("--received-at", type=_aware_iso)
    return parser


def _journal(args, parser):
    dsn = os.environ.get("THERMAL_DATABASE_URL")
    if not dsn:
        parser.error("THERMAL_DATABASE_URL is required")
    try:
        payload = args.message_file.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        parser.error(f"unable to read UTF-8 message file: {exc}")
    received_at = args.received_at or datetime.now(timezone.utc)
    parsed = parse_thermal_message(text, received_at, args.idempotency_key)
    journal = ActionJournal(dsn)
    inserted = journal.append_batch(parsed.actions, parsed.modes, payload=payload)
    stored_actions = journal.events_for_receipt(args.idempotency_key)
    stored_modes = journal.modes_for_receipt(args.idempotency_key)
    receipt = {
        "action_event_ids": [event.event_id for event in stored_actions],
        "idempotency_key": args.idempotency_key,
        "inserted": inserted,
        "mode_event_ids": [event.event_id for event in stored_modes],
    }
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.subcommand == "journal":
        _journal(args, parser)
        return 0
    parser.error("unsupported subcommand")


if __name__ == "__main__":
    raise SystemExit(main())
