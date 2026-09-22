#!/usr/bin/env python3
"""Fail-closed, attended NIP-17 thermal confirmation ingress.

Only processes an explicitly supplied gift wrap; no relay subscriptions, replies,
actuator commands, schema migration, model promotion, or timer installation.
Crypto is delegated to an explicitly configured, SHA-256-pinned nak executable.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import selectors
import signal
import sqlite3
import stat
import subprocess
import sys
import time
from typing import Callable
from zoneinfo import ZoneInfo

UTC = timezone.utc
DENVER = ZoneInfo("America/Denver")
MAX_INPUT = 65536
MAX_RUMOR = 16384
MAX_AGE = timedelta(hours=48)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
STATES = {"vent": {"open", "closed"}, "indoor_shade": {"open", "closed"},
          "outdoor_shade": {"installed", "removed"}, "kiva": {"on", "off"}}


class Refused(ValueError):
    """Safe, fixed diagnostic; never include decrypted input or credentials."""


class Retryable(RuntimeError):
    """No success acknowledgement: replay the original input after repair."""


def canonical(value: object) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                          sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise Refused("invalid JSON value") from exc


def strict_json(payload: bytes, limit: int = MAX_INPUT):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= limit:
        raise Refused("input size outside bound")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Refused("duplicate JSON field")
            result[key] = value
        return result

    def constant(_):
        raise Refused("non-finite JSON constant")

    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Refused("invalid JSON document") from exc


def identifier(value: object) -> str:
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise Refused("invalid event identity")
    return value


def aware(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(UTC)
    except (ValueError, TypeError, OverflowError) as exc:
        raise Refused("timestamp must be timezone-aware") from exc


def iso(value: datetime) -> str:
    return aware(value).isoformat()


def event_id(event: dict) -> str:
    serial = [0, event["pubkey"], event["created_at"], event["kind"],
              event["tags"], event["content"]]
    # NIP-01 hashes this array in order, not an event dictionary.
    return sha256(canonical(serial)).hexdigest()


def validate_event(event, *, kind: int, signed: bool):
    required = {"id", "pubkey", "created_at", "kind", "tags", "content"}
    allowed = required | {"sig"}
    if (not isinstance(event, dict) or not required <= event.keys()
            or not event.keys() <= allowed):
        raise Refused("invalid event fields")
    identifier(event["id"])
    identifier(event["pubkey"])
    if type(event["kind"]) is not int or event["kind"] != kind:
        raise Refused("wrong event kind")
    if type(event["created_at"]) is not int or not 0 <= event["created_at"] <= 253402300799:
        raise Refused("invalid event timestamp")
    if not isinstance(event["content"], str):
        raise Refused("invalid event content")
    tags = event["tags"]
    if (not isinstance(tags, list) or len(tags) > 32
            or any(not isinstance(tag, list) or not 1 <= len(tag) <= 5
                   or any(not isinstance(s, str) or len(s) > 512 for s in tag)
                   for tag in tags)):
        raise Refused("invalid event tags")
    if signed and (not isinstance(event.get("sig"), str)
                   or re.fullmatch(r"[0-9a-f]{128}", event["sig"]) is None):
        raise Refused("invalid signature representation")
    if event_id(event) != event["id"]:
        raise Refused("event hash mismatch")
    return event


def tag_value(event: dict, name: str) -> str:
    tags = [tag for tag in event["tags"] if tag[0] == name]
    if len(tags) != 1 or len(tags[0]) < 2:
        raise Refused("missing or ambiguous message scope")
    return identifier(tags[0][1])


@dataclass(frozen=True)
class Prompt:
    event_id: str
    operator: str
    issued_at: datetime
    expires_at: datetime
    actions: tuple[tuple[str, str], ...]
    correction_of: str | None = None

    def snapshot(self):
        return {"id": self.event_id, "operator": self.operator,
                "issued_at": iso(self.issued_at), "expires_at": iso(self.expires_at),
                "actions": dict(self.actions), "correction_of": self.correction_of}


@dataclass(frozen=True)
class Policy:
    recipient: str
    operators: frozenset[str]
    prompts: tuple[Prompt, ...]

    @classmethod
    def load(cls, raw: bytes, *, assign_ids: bool = False):
        obj = strict_json(raw)
        if not isinstance(obj, dict) or set(obj) != {"version", "recipient", "operators", "prompts"}:
            raise Refused("invalid policy fields")
        if type(obj["version"]) is not int or obj["version"] != 1:
            raise Refused("unsupported policy version")
        recipient = identifier(obj["recipient"])
        authors = obj["operators"]
        if (not isinstance(authors, list) or not 1 <= len(authors) <= 16
                or any(not isinstance(x, str) for x in authors)):
            raise Refused("invalid operator allowlist")
        operators = frozenset(identifier(x) for x in authors)
        if len(operators) != len(authors) or recipient in operators:
            raise Refused("invalid operator allowlist")
        if not isinstance(obj["prompts"], list) or not 1 <= len(obj["prompts"]) <= 100:
            raise Refused("invalid prompt inventory")
        prompts = []
        for value in obj["prompts"]:
            fields = {"operator", "issued_at", "expires_at", "actions"}
            if not assign_ids:
                fields.add("id")
            if (not isinstance(value, dict) or not fields <= value.keys()
                    or not value.keys() <= fields | {"id", "correction_of"}):
                raise Refused("invalid prompt fields")
            operator = identifier(value["operator"])
            if operator not in operators:
                raise Refused("prompt operator not allowlisted")
            issued, expires = aware(value["issued_at"]), aware(value["expires_at"])
            if not timedelta(0) < expires - issued <= MAX_AGE:
                raise Refused("prompt lifetime outside bound")
            actions = value["actions"]
            if (not isinstance(actions, dict) or not actions
                    or any(key not in STATES or not isinstance(state, str) or state not in STATES[key]
                           for key, state in actions.items())):
                raise Refused("invalid prompt action vocabulary")
            correction = value.get("correction_of")
            if correction is not None:
                identifier(correction)
            prompt = Prompt("0" * 64 if assign_ids else identifier(value["id"]), operator,
                            issued, expires, tuple(sorted(actions.items())), correction)
            computed = prompt_event(prompt, recipient)["id"]
            if not assign_ids and prompt.event_id != computed:
                raise Refused("prompt identity does not bind the configured question and actions")
            prompts.append(replace(prompt, event_id=computed))
        if len({p.event_id for p in prompts}) != len(prompts):
            raise Refused("duplicate prompt identity")
        return cls(recipient, operators, tuple(prompts))


def prompt_event(prompt: Prompt, recipient: str) -> dict:
    """Canonical, UNSIGNED NIP-17 question; never a public kind-1 note.

    Publish this exact rumor through the separately reviewed encrypted sender.
    Binding its hash prevents mapping an operator's `yes` to another question.
    """
    names = {"vent": "Vents", "indoor_shade": "Indoor shades",
             "outdoor_shade": "Outdoor shades", "kiva": "Kiva"}
    lines = ["THERMAL CONFIRMATION v1", "Have you completed ALL these actions?"]
    if prompt.correction_of:
        lines.append("Correction of confirmation: " + prompt.correction_of)
    lines.extend(names[action] + ": " + state for action, state in prompt.actions)
    lines.extend(["Question issued: " + iso(prompt.issued_at),
                  "Reply accepted through: " + iso(prompt.expires_at),
                  "Reply yes only after completion, not for plans.",
                  "Otherwise reply not yet or skip.",
                  "For an earlier completed action: yes HH:MM (America/Denver today)",
                  "or yes YYYY-MM-DDTHH:MM:SS+/-HH:MM with an explicit UTC offset."])
    value = {"pubkey": recipient, "created_at": int(prompt.issued_at.timestamp()),
             "kind": 14, "tags": [["p", prompt.operator]], "content": "\n".join(lines)}
    value["id"] = event_id(value)
    return value


def policy_object(policy: Policy) -> dict:
    return {"version": 1, "recipient": policy.recipient, "operators": sorted(policy.operators),
            "prompts": [p.snapshot() for p in policy.prompts]}


def action_records(rumor, prompt, received_at, prior=None):
    signed_at = datetime.fromtimestamp(rumor["created_at"], UTC)
    disposition, effective = resolve_reply(rumor["content"], signed_at)
    previous = {} if prior is None else {r["action"]: r for r in json.loads(prior["records_json"])}
    if prior is not None and set(previous) != dict(prompt.actions).keys():
        raise Refused("correction action scope differs from original confirmation")
    records = []
    if disposition == "confirmed":
        key = "nostr:" + rumor["id"]
        for action, state in prompt.actions:
            at = iso(effective)
            eid = sha256(f"{key}:{action}:{state}:{at}".encode()).hexdigest()[:24]
            records.append({"event_id": eid, "idempotency_key": key,
                            "received_at": iso(received_at), "effective_at": at,
                            "action": action, "state": state, "source": "nostr_confirmed",
                            "confidence": 1.0, "interval_id": None,
                            "note": "Nostr prompt " + prompt.event_id,
                            "supersedes": previous[action]["event_id"] if prior else None})
    return disposition, records


def run_bounded(argv: list[str], payload: bytes, env: dict[str, str], *,
                timeout: float = 30, limit: int = MAX_INPUT) -> bytes:
    """Bound process time and stdout before allocating an unbounded response."""
    child = None
    try:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, env=env, start_new_session=True)
        assert child.stdin is not None and child.stdout is not None
        os.set_blocking(child.stdin.fileno(), False)
        os.set_blocking(child.stdout.fileno(), False)
        output = bytearray()
        offset = 0
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as select:
            select.register(child.stdin, selectors.EVENT_WRITE)
            select.register(child.stdout, selectors.EVENT_READ)
            while select.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise Retryable("Nostr verifier timed out")
                for key, _ in select.select(min(remaining, 0.2)):
                    if key.fileobj is child.stdin:
                        try:
                            offset += os.write(child.stdin.fileno(), payload[offset:offset + 4096])
                        except BrokenPipeError:
                            offset = len(payload)
                        if offset == len(payload):
                            select.unregister(child.stdin)
                            child.stdin.close()
                    else:
                        block = os.read(child.stdout.fileno(), min(4096, limit + 1 - len(output)))
                        if not block:
                            select.unregister(child.stdout)
                            child.stdout.close()
                        else:
                            output.extend(block)
                            if len(output) > limit:
                                raise Retryable("Nostr verifier output exceeds bound")
            remaining = deadline - time.monotonic()
            if remaining <= 0 or child.wait(timeout=remaining) != 0:
                raise Refused("Nostr cryptographic verification failed")
        return bytes(output)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Retryable("Nostr verifier unavailable") from exc
    finally:
        if child is not None:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()
            for stream in (child.stdin, child.stdout):
                if stream is not None and not stream.closed:
                    stream.close()


class NakDecoder:
    """Trust boundary: nak verifies the outer signature AND authenticated seal.

    The supported `gift unwrap` contract sets rumor.pubkey from seal.pubkey and
    recomputes rumor.id. Qualify the approved binary against the runbook before
    production. No generic caller-supplied executable arguments are accepted.
    """
    def __init__(self, executable: Path, expected_sha256: str,
                 *, runner: Callable = run_bounded):
        self.executable = executable
        self.digest = identifier(expected_sha256)
        self.runner = runner

    def decode(self, raw: bytes, recipient: str):
        if not self.executable.is_absolute() or self.executable.is_symlink():
            raise Refused("nak must be an explicit non-symlink absolute path")
        try:
            info = self.executable.stat()
            if (not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022
                    or not info.st_mode & 0o111 or info.st_size > 128 * 1024 * 1024
                    or info.st_uid not in {0, os.getuid()}):
                raise Refused("nak executable ownership or mode is unsafe")
            if sha256(self.executable.read_bytes()).hexdigest() != self.digest:
                raise Refused("nak executable hash mismatch")
        except OSError as exc:
            raise Retryable("pinned nak executable unavailable") from exc
        secret = os.environ.get("NOSTR_SECRET_KEY")
        if not secret:
            raise Refused("explicit Nostr identity configuration is required")
        wrap = validate_event(strict_json(raw), kind=1059, signed=True)
        if tag_value(wrap, "p") != recipient:
            raise Refused("gift wrap is not addressed to collector")
        payload = canonical(wrap) + b"\n"
        environment = {k: v for k, v in os.environ.items()
                       if k in {"PATH", "HOME", "LANG", "LC_ALL", "XDG_CONFIG_HOME"}}
        # Database credentials are never exposed to the crypto subprocess.
        self.runner([str(self.executable), "verify"], payload, environment)
        environment["NOSTR_SECRET_KEY"] = secret
        clear = self.runner([str(self.executable), "gift", "unwrap"], payload,
                            environment, limit=MAX_RUMOR)
        return validate_event(strict_json(clear, MAX_RUMOR), kind=14, signed=False)


def resolve_reply(content: str, signed_at: datetime):
    """Only actual, completed transitions; no NLP or general command syntax."""
    if content == "not yet":
        return "not_yet", None
    if content == "skip":
        return "skipped", None
    if content == "yes":
        return "confirmed", signed_at
    if not content.startswith("yes ") or len(content) > 80:
        raise Refused("reply is outside the confirmation vocabulary")
    value = content[4:]
    if re.fullmatch(r"\d{2}:\d{2}", value):
        hour, minute = map(int, value.split(":"))
        try:
            local = signed_at.astimezone(DENVER).replace(hour=hour, minute=minute,
                                                       second=0, microsecond=0, tzinfo=None)
        except ValueError as exc:
            raise Refused("invalid local confirmation time") from exc
        candidates = {}
        for fold in (0, 1):
            candidate = local.replace(tzinfo=DENVER, fold=fold)
            if candidate.astimezone(UTC).astimezone(DENVER).replace(tzinfo=None) == local:
                candidates[candidate.utcoffset()] = candidate.astimezone(UTC)
        if len(candidates) != 1:
            raise Refused("local confirmation time is ambiguous or nonexistent")
        effective = next(iter(candidates.values()))
    else:
        effective = aware(value)
    if effective > signed_at or signed_at - effective > MAX_AGE:
        raise Refused("confirmation is future-dated or outside reporting window")
    return "confirmed", effective


class Spool:
    """Private, durable first-receipt ledger. No pruning or network authority."""
    def __init__(self, directory: Path):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise Refused("spool directory must be private and owned by current user")
        path = directory / "confirmations.sqlite3"
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        except FileExistsError:
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise Refused("spool database must be a private regular file")
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise Refused("unsupported spool schema")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS receipts (
            rumor_id TEXT PRIMARY KEY, digest TEXT NOT NULL, prompt_json TEXT NOT NULL,
            recipient TEXT NOT NULL, operator TEXT NOT NULL, first_received_at TEXT NOT NULL,
            signed_at TEXT NOT NULL, disposition TEXT NOT NULL, rumor_json TEXT NOT NULL,
            original_wrap BLOB NOT NULL, records_json TEXT NOT NULL, acknowledgement TEXT);
          CREATE TABLE IF NOT EXISTS terminal_prompts (
            prompt_id TEXT PRIMARY KEY, rumor_id TEXT NOT NULL UNIQUE REFERENCES receipts(rumor_id));
          CREATE TABLE IF NOT EXISTS corrections (
            original_id TEXT PRIMARY KEY REFERENCES receipts(rumor_id),
            correction_id TEXT NOT NULL UNIQUE REFERENCES receipts(rumor_id));
          PRAGMA user_version=1;
        """)
        self.db.commit()

    def close(self):
        self.db.close()

    def get(self, rumor_id: str):
        row = self.db.execute("SELECT * FROM receipts WHERE rumor_id=?", (rumor_id,)).fetchone()
        return dict(row) if row is not None else None

    def receive(self, rumor: dict, wrap: bytes, prompt: Prompt, recipient: str, now: datetime):
        body = canonical({k: v for k, v in rumor.items() if k != "sig"})
        digest = sha256(body).hexdigest()
        prompt_json = canonical(prompt.snapshot()).decode()
        key = rumor["id"]
        self.db.execute("BEGIN IMMEDIATE")
        try:
            old = self.get(key)
            if old is not None:
                if (old["digest"] != digest or old["prompt_json"] != prompt_json
                        or old["recipient"] != recipient or old["operator"] != prompt.operator):
                    raise Refused("receipt or prompt conflicts with original acceptance")
                original_time = aware(old["first_received_at"])
                signed_at = datetime.fromtimestamp(rumor["created_at"], UTC)
                if (original_time > now or original_time < signed_at
                        or original_time - signed_at > MAX_AGE
                        or not prompt.issued_at <= signed_at <= prompt.expires_at
                        or original_time > prompt.expires_at):
                    raise Refused("original receipt timing is inconsistent")
                prior = self.get(prompt.correction_of) if prompt.correction_of else None
                if prompt.correction_of and prior is None:
                    raise Refused("original correction target is missing")
                disposition, records = action_records(rumor, prompt, original_time, prior)
                if (old["rumor_json"] != body.decode() or old["signed_at"] != iso(signed_at)
                        or old["disposition"] != disposition
                        or old["records_json"] != canonical(records).decode()):
                    raise Refused("stored receipt does not match authenticated confirmation")
                self.db.commit()
                return old
            signed_at = datetime.fromtimestamp(rumor["created_at"], UTC)
            if (signed_at > now or now - signed_at > MAX_AGE
                    or not prompt.issued_at <= signed_at <= prompt.expires_at
                    or now > prompt.expires_at):
                raise Refused("reply is future-dated, expired, or outside prompt window")
            if self.db.execute("SELECT 1 FROM terminal_prompts WHERE prompt_id=?",
                               (prompt.event_id,)).fetchone():
                raise Refused("prompt already has a terminal reply; use an explicit correction prompt")
            disposition, effective = resolve_reply(rumor["content"], signed_at)
            prior = None
            if prompt.correction_of is not None:
                prior = self.get(prompt.correction_of)
                if (prior is None or prior["acknowledgement"] is None
                        or prior["disposition"] != "confirmed"
                        or prior["operator"] != prompt.operator or prior["recipient"] != recipient):
                    raise Refused("correction requires a stored confirmation by the same operator")
                if self.db.execute("SELECT 1 FROM corrections WHERE original_id=?",
                                   (prompt.correction_of,)).fetchone():
                    raise Refused("correct the latest confirmation, not a superseded ancestor")
            disposition, records = action_records(rumor, prompt, now, prior)
            self.db.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)",
                            (key, digest, prompt_json, recipient, prompt.operator, iso(now),
                             iso(signed_at), disposition, body.decode(), wrap,
                             canonical(records).decode()))
            if disposition in {"confirmed", "skipped"}:
                self.db.execute("INSERT INTO terminal_prompts VALUES (?,?)", (prompt.event_id, key))
            if prior is not None and disposition == "confirmed":
                self.db.execute("INSERT INTO corrections VALUES (?,?)", (prompt.correction_of, key))
            self.db.commit()  # Must precede ANY external journal side effect.
            return self.get(key)
        except sqlite3.IntegrityError as exc:
            self.db.rollback()
            raise Refused("prompt already has a terminal reply; use an explicit correction prompt") from exc
        except BaseException:
            self.db.rollback()
            raise

    def acknowledge(self, row: dict, receipt: dict):
        encoded = canonical(receipt).decode()
        with self.db:
            current = self.get(row["rumor_id"])
            if current is None or current["digest"] != row["digest"]:
                raise Retryable("receipt ledger changed before acknowledgement")
            if current["acknowledgement"] not in (None, encoded):
                raise Retryable("stored acknowledgement conflicts with exact receipt")
            self.db.execute("UPDATE receipts SET acknowledgement=? WHERE rumor_id=?",
                            (encoded, row["rumor_id"]))
        return receipt


class JournalSink:
    """Existing append-only PostgreSQL API, with full immutable record readback."""
    def __init__(self, journal=None, action_factory=None):
        self.journal = journal
        self.action_factory = action_factory

    def store(self, records: list[dict], payload: bytes):
        if not records:
            raise Refused("empty confirmation must not reach the action journal")
        try:
            if self.journal is None:
                dsn = os.environ.get("THERMAL_DATABASE_URL")
                if not dsn:
                    raise Retryable("restricted thermal journal connection is not configured")
                from thermal_model.journal import ActionJournal
                from thermal_model.schema import ActionEvent
                self.journal = ActionJournal(dsn)
                self.action_factory = ActionEvent
            if self.action_factory is None:
                raise Retryable("action record factory unavailable")
            expected = tuple(self.action_factory(**{**r, "received_at": aware(r["received_at"]),
                                                   "effective_at": aware(r["effective_at"])})
                             for r in records)
            self.journal.append_batch(expected, (), payload=payload)
            stored = tuple(self.journal.events_for_receipt(records[0]["idempotency_key"]))
            modes = tuple(self.journal.modes_for_receipt(records[0]["idempotency_key"]))
            expected_by_id = {r.event_id: r for r in expected}
            stored_by_id = {r.event_id: r for r in stored}
            if (modes or len(stored_by_id) != len(stored)
                    or len(expected_by_id) != len(expected) or stored_by_id != expected_by_id):
                raise Retryable("thermal journal exact readback failed")
        except Retryable:
            raise
        except Exception as exc:
            # Never send database diagnostics or message contents to an operator.
            raise Retryable("thermal journal unavailable or receipt conflicted") from exc


def ingest(raw: bytes, policy: Policy, spool: Spool, decoder, sink, *, now=None):
    now = aware(now or datetime.now(UTC))
    # Receipt timestamp is fixed BEFORE network/keyer operations, never on retry.
    rumor = validate_event(decoder.decode(raw, policy.recipient), kind=14, signed=False)
    if rumor["pubkey"] not in policy.operators:
        raise Refused("sender is not an authorized thermal operator")
    if tag_value(rumor, "p") != policy.recipient:
        raise Refused("message is not addressed to this collector")
    prompt_id = tag_value(rumor, "e")
    prompt = next((p for p in policy.prompts if p.event_id == prompt_id), None)
    if prompt is None or prompt.operator != rumor["pubkey"]:
        raise Refused("reply is not bound to this operator's thermal prompt")
    row = spool.receive(rumor, raw, prompt, policy.recipient, now)
    records = json.loads(row["records_json"])
    if row["disposition"] == "confirmed":
        # Even a previously acknowledged replay re-verifies PostgreSQL storage.
        sink.store(records, row["rumor_json"].encode())
    receipt = {"version": 1, "status": "stored" if records else "no_action_recorded",
               "disposition": row["disposition"], "rumor_id": row["rumor_id"],
               "idempotency_key": "nostr:" + row["rumor_id"],
               "first_received_at": row["first_received_at"],
               "action_event_ids": [r["event_id"] for r in records]}
    return spool.acknowledge(row, receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-policy", action="store_true", help="emit policy with canonical prompt IDs; no network or journal")
    modes.add_argument("--render-prompts", action="store_true", help="emit unsigned kind-14 questions for a reviewed encrypted sender")
    modes.add_argument("--apply", action="store_true", help="process one genuine encrypted reply into the journal")
    parser.add_argument("--spool-dir", type=Path)
    parser.add_argument("--nak", type=Path)
    parser.add_argument("--nak-sha256")
    parser.add_argument("--event-file", type=Path, help="otherwise one gift wrap is read from stdin")
    args = parser.parse_args(argv)
    spool = None
    try:
        with args.policy.open("rb") as handle:
            policy = Policy.load(handle.read(MAX_INPUT + 1), assign_ids=args.prepare_policy)
        if args.prepare_policy:
            print(canonical(policy_object(policy)).decode())
            return 0
        if args.render_prompts:
            for prompt in policy.prompts:
                print(canonical(prompt_event(prompt, policy.recipient)).decode())
            return 0
        if args.spool_dir is None or args.nak is None or args.nak_sha256 is None:
            parser.error("--apply requires --spool-dir, --nak and --nak-sha256")
        if args.event_file:
            with args.event_file.open("rb") as handle:
                raw = handle.read(MAX_INPUT + 1)
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        strict_json(raw)  # Reject oversize input before creating local state.
        spool = Spool(args.spool_dir)
        receipt = ingest(raw, policy, spool, NakDecoder(args.nak, args.nak_sha256), JournalSink())
        print(canonical(receipt).decode())
        return 0
    except Refused as exc:
        print("confirmation refused: " + str(exc), file=sys.stderr)
        return 2
    except (Retryable, OSError, sqlite3.Error, ImportError):
        print("confirmation not acknowledged; repair the dependency and replay the original event", file=sys.stderr)
        return 3
    finally:
        if spool is not None:
            spool.close()


if __name__ == "__main__":
    raise SystemExit(main())
