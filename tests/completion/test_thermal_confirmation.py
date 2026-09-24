"""Offline tests. nak signatures/decryption and PostgreSQL are explicit doubles.

SQLite persistence, JSON/hash validation, time policy, subprocess bounds and
receipt state transitions execute for real in temporary local directories.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "openhab/scripts/thermal_confirmation.py"
spec = importlib.util.spec_from_file_location("completion_thermal", PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
UTC = timezone.utc
NOW = datetime(2026, 9, 21, 15, 0, tzinfo=UTC)
OPERATOR = "a" * 64
RECIPIENT = "b" * 64
PROMPT = "c" * 64
OTHER = "d" * 64


def policy_data():
    return {"version": 1, "recipient": RECIPIENT, "operators": [OPERATOR], "prompts": [
        {"id": PROMPT, "operator": OPERATOR,
         "issued_at": (NOW - timedelta(hours=1)).isoformat(),
         "expires_at": (NOW + timedelta(hours=1)).isoformat(),
         "actions": {"vent": "closed", "indoor_shade": "closed"}}]}


PROMPT = m.Policy.load(m.canonical(policy_data()), assign_ids=True).prompts[0].event_id

def make_policy(data=None):
    return m.Policy.load(m.canonical(data or policy_data()))


def event(content="yes", *, at=NOW, operator=OPERATOR, prompt=PROMPT,
          recipient=RECIPIENT, kind=14, extra_tags=()):
    value = {"pubkey": operator, "created_at": int(at.timestamp()), "kind": kind,
             "tags": [["p", recipient], ["e", prompt], *extra_tags], "content": content}
    value["id"] = m.event_id(value)
    return value


class Decoder:
    """Authorized rumor fixture; deliberately not a cryptographic verifier."""
    def __init__(self, value):
        self.value = value

    def decode(self, raw, recipient):
        return self.value


@dataclass(frozen=True)
class Action:
    event_id: str
    idempotency_key: str
    received_at: datetime
    effective_at: datetime
    action: str
    state: str
    source: str
    confidence: float
    interval_id: str | None = None
    note: str = ""
    supersedes: str | None = None


class Journal:
    def __init__(self):
        self.records = {}
        self.payloads = {}
        self.calls = 0
        self.fail_append = False
        self.read_transform = lambda rows: rows
        self.mode_rows = ()

    def append_batch(self, actions, modes, *, payload):
        self.calls += 1
        if self.fail_append:
            raise RuntimeError("private database diagnostic")
        assert not modes
        key = actions[0].idempotency_key
        if key in self.records:
            if self.records[key] != actions or self.payloads[key] != payload:
                raise RuntimeError("idempotency conflict")
            return 0
        self.records[key] = actions
        self.payloads[key] = payload
        return len(actions)

    def events_for_receipt(self, key):
        return self.read_transform(self.records.get(key, ()))

    def modes_for_receipt(self, key):
        return self.mode_rows


@pytest.fixture
def setup(tmp_path):
    spool = m.Spool(tmp_path / "private")
    journal = Journal()
    sink = m.JournalSink(journal, Action)
    yield SimpleNamespace(spool=spool, journal=journal, sink=sink, directory=tmp_path / "private")
    spool.close()


def accept(setup, value=None, *, policy=None, now=NOW, raw=b'{"encrypted":"fixture"}'):
    return m.ingest(raw, policy or make_policy(), setup.spool, Decoder(value or event()),
                    setup.sink, now=now)


def test_completed_confirmation_has_exact_stored_receipt(setup):
    receipt = accept(setup)
    assert receipt["status"] == "stored"
    assert receipt["first_received_at"] == NOW.isoformat()
    assert len(receipt["action_event_ids"]) == 2
    records = setup.journal.records[receipt["idempotency_key"]]
    assert {a.action for a in records} == {"vent", "indoor_shade"}
    assert all(a.source == "nostr_confirmed" and a.confidence == 1.0 for a in records)
    assert all(a.effective_at == NOW and a.received_at == NOW for a in records)


@pytest.mark.parametrize("reply, disposition", [("skip", "skipped"), ("not yet", "not_yet")])
def test_nonconfirmation_has_no_action_or_mode(setup, reply, disposition):
    receipt = accept(setup, event(reply))
    assert receipt["disposition"] == disposition
    assert receipt["status"] == "no_action_recorded"
    assert receipt["action_event_ids"] == []
    assert setup.journal.calls == 0


def test_not_yet_can_be_followed_by_genuine_confirmation(setup):
    accept(setup, event("not yet"))
    receipt = accept(setup, event(at=NOW + timedelta(minutes=5)), now=NOW + timedelta(minutes=5))
    assert receipt["status"] == "stored"
    assert setup.journal.calls == 1


@pytest.mark.parametrize("terminal", ["yes", "skip"])
def test_second_distinct_terminal_reply_requires_correction(setup, terminal):
    accept(setup, event(terminal))
    with pytest.raises(m.Refused, match="terminal"):
        accept(setup, event(at=NOW + timedelta(seconds=1)), now=NOW + timedelta(seconds=1))
    assert setup.spool.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1


def test_rewrapped_same_rumor_retains_receipt_and_payload(setup):
    first = accept(setup)
    repeat = accept(setup, now=NOW + timedelta(minutes=10), raw=b'{"different":"gift wrap"}')
    assert first == repeat
    assert len(setup.journal.records) == 1
    assert setup.journal.calls == 2  # Readback is repeated, not cached success.
    assert setup.spool.get(event()["id"])["original_wrap"] == b'{"encrypted":"fixture"}'


def test_receipt_survives_process_restart_and_prompt_expiry(setup):
    first = accept(setup)
    setup.spool.close()
    setup.spool = m.Spool(setup.directory)
    assert accept(setup, now=NOW + timedelta(days=3)) == first
    # Fixture cleanup must close the replacement rather than the old object.
    setup.spool.close()
    setup.spool = m.Spool(setup.directory)


def test_commit_then_readback_failure_is_retriable_with_same_original_time(setup):
    setup.journal.read_transform = lambda rows: ()
    with pytest.raises(m.Retryable):
        accept(setup)
    row = setup.spool.get(event()["id"])
    assert row["acknowledgement"] is None
    setup.journal.read_transform = lambda rows: rows
    receipt = accept(setup, now=NOW + timedelta(minutes=5))
    assert receipt["first_received_at"] == NOW.isoformat()
    assert len(setup.journal.records) == 1


def test_outbox_failure_after_journal_commit_does_not_change_replay(setup, monkeypatch):
    original = setup.spool.acknowledge
    monkeypatch.setattr(setup.spool, "acknowledge", lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError()))
    with pytest.raises(sqlite3.OperationalError):
        accept(setup)
    assert setup.spool.get(event()["id"])["acknowledgement"] is None
    monkeypatch.setattr(setup.spool, "acknowledge", original)
    result = accept(setup, now=NOW + timedelta(minutes=10))
    assert result["first_received_at"] == NOW.isoformat()
    assert len(setup.journal.records) == 1


def test_append_failure_has_durable_pending_receipt_without_ack(setup):
    setup.journal.fail_append = True
    with pytest.raises(m.Retryable) as failure:
        accept(setup)
    assert "private" not in str(failure.value)
    assert setup.spool.get(event()["id"])["acknowledgement"] is None
    setup.journal.fail_append = False
    assert accept(setup)["status"] == "stored"


@pytest.mark.parametrize("transform", [
    lambda rows: rows[:-1],
    lambda rows: (*rows, rows[0]),
    lambda rows: (*rows[:-1], replace(rows[-1], state="open")),
    lambda rows: (*rows[:-1], replace(rows[-1], received_at=NOW + timedelta(seconds=1))),
    lambda rows: (*rows[:-1], replace(rows[-1], source="model_inferred")),
    lambda rows: (*rows[:-1], replace(rows[-1], note="changed")),
    lambda rows: (*rows[:-1], replace(rows[-1], supersedes="1" * 24)),
])
def test_exact_readback_rejects_missing_duplicate_or_changed_records(setup, transform):
    setup.journal.read_transform = transform
    with pytest.raises(m.Retryable, match="readback"):
        accept(setup)
    assert setup.spool.get(event()["id"])["acknowledgement"] is None


def test_unexpected_mode_record_fails_ack(setup):
    setup.journal.mode_rows = (object(),)
    with pytest.raises(m.Retryable, match="readback"):
        accept(setup)


def test_previously_acknowledged_replay_rechecks_actual_storage(setup):
    accept(setup)
    setup.journal.read_transform = lambda _: ()
    with pytest.raises(m.Retryable):
        accept(setup)


@pytest.mark.parametrize("value", [
    event(operator=OTHER), event(recipient=OTHER), event(prompt=OTHER),
    event(extra_tags=[["p", RECIPIENT]]), event(extra_tags=[["e", OTHER]]),
    event(at=NOW + timedelta(seconds=1)), event(at=NOW - timedelta(hours=2)),
    event("yes 23:59"), event("yes tomorrow"), event("yes; rm -rf /"),
    event("THERMAL\nvent: open"), event("yes\nvent: open"), event("YES"),
    event("yes 2026-09-21T16:00:00+00:00"), event("yes 2026-09-21T08:00:00"),
    event("yes 2026-09-18T08:00:00+00:00"),
])
def test_invalid_replies_never_reach_journal(setup, value):
    with pytest.raises(m.Refused):
        accept(setup, value)
    assert setup.journal.calls == 0
    assert setup.spool.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 0


def test_expired_first_receipt_is_not_accepted(setup):
    with pytest.raises(m.Refused):
        accept(setup, now=NOW + timedelta(hours=2))
    assert not setup.journal.records


def test_valid_explicit_local_time_and_signed_timestamp_distinct_from_receipt(setup):
    value = event("yes 08:30")
    receipt = accept(setup, value, now=NOW + timedelta(minutes=5))
    record = setup.journal.records[receipt["idempotency_key"]][0]
    assert record.effective_at == NOW - timedelta(minutes=30)
    assert record.received_at == NOW + timedelta(minutes=5)


@pytest.mark.parametrize("stamp, clock", [
    (datetime(2026, 3, 8, 10, 0, tzinfo=UTC), "02:30"),
    (datetime(2026, 11, 1, 10, 0, tzinfo=UTC), "01:30"),
])
def test_dst_clock_requires_explicit_offset(stamp, clock):
    with pytest.raises(m.Refused, match="ambiguous or nonexistent"):
        m.resolve_reply("yes " + clock, stamp)


@pytest.mark.parametrize("text", ["yes 2026-11-01T01:30:00-06:00", "yes 2026-11-01T01:30:00-07:00"])
def test_explicit_dst_offsets_are_unambiguous(text):
    disposition, at = m.resolve_reply(text, datetime(2026, 11, 1, 10, 0, tzinfo=UTC))
    assert disposition == "confirmed" and at.tzinfo is UTC


def test_changed_prompt_same_id_cannot_reinterpret_replay(setup):
    accept(setup)
    data = policy_data()
    data["prompts"][0]["actions"]["vent"] = "open"
    with pytest.raises(m.Refused, match="conflicts|identity"):
        accept(setup, policy=make_policy(data))
    assert setup.journal.calls == 1


def correction_policy(original, *, offset=0):
    data = policy_data()
    data["prompts"].append({**data["prompts"][0], "id": OTHER,
                            "issued_at": (NOW - timedelta(hours=1) + timedelta(seconds=offset)).isoformat(),
                            "actions": {"vent": "open", "indoor_shade": "closed"},
                            "correction_of": original})
    return m.Policy.load(m.canonical(data), assign_ids=True)


def test_correction_appends_links_and_never_mutates_original(setup):
    original = accept(setup)
    prior = setup.journal.records[original["idempotency_key"]]
    policy = correction_policy(original["rumor_id"])
    correction = event("yes 08:45", prompt=policy.prompts[-1].event_id, at=NOW + timedelta(minutes=1))
    result = accept(setup, correction, policy=policy, now=NOW + timedelta(minutes=1))
    assert setup.journal.records[original["idempotency_key"]] == prior
    new = setup.journal.records[result["idempotency_key"]]
    assert {e.supersedes for e in new} == {e.event_id for e in prior}
    assert all(e.event_id not in {p.event_id for p in prior} for e in new)
    assert accept(setup, correction, policy=policy, now=NOW + timedelta(minutes=2)) == result


def test_correction_requires_stored_original(setup):
    with pytest.raises(m.Refused, match="stored confirmation"):
        policy = correction_policy("e" * 64)
        accept(setup, event(prompt=policy.prompts[-1].event_id), policy=policy)


def test_correction_cannot_target_skipped_reply(setup):
    skipped = accept(setup, event("skip"))
    with pytest.raises(m.Refused, match="stored confirmation"):
        policy = correction_policy(skipped["rumor_id"])
        accept(setup, event(prompt=policy.prompts[-1].event_id), policy=policy)


def test_correction_cannot_fork_superseded_ancestor(setup):
    original = accept(setup)
    policy = correction_policy(original["rumor_id"])
    accept(setup, event(prompt=policy.prompts[-1].event_id), policy=policy)
    with pytest.raises(m.Refused, match="latest"):
        policy = correction_policy(original["rumor_id"], offset=1)
        accept(setup, event(prompt=policy.prompts[-1].event_id), policy=policy)


def test_correction_cannot_expand_action_scope(setup):
    original = accept(setup)
    data = policy_data()
    data["prompts"].append({**data["prompts"][0], "id": OTHER,
                            "actions": {"vent": "open"}, "correction_of": original["rumor_id"]})
    with pytest.raises(m.Refused, match="scope"):
        policy = m.Policy.load(m.canonical(data), assign_ids=True)
        accept(setup, event(prompt=policy.prompts[-1].event_id), policy=policy)


@pytest.mark.parametrize("payload", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{} {}', b'\xff', b'', b' ' * (m.MAX_INPUT + 1)])
def test_json_validation_is_strict(payload):
    with pytest.raises(m.Refused):
        m.strict_json(payload)


@pytest.mark.parametrize("field, value", [("kind", True), ("created_at", True),
                                         ("created_at", -1), ("tags", [[]]),
                                         ("tags", [["p", 3]]), ("content", 3),
                                         ("pubkey", "A" * 64), ("unknown", "x")])
def test_malformed_event_envelopes_rejected(field, value):
    obj = event()
    obj[field] = value
    with pytest.raises(m.Refused):
        m.validate_event(obj, kind=14, signed=False)


def test_event_hash_matches_published_nak_fixture():
    value = {"id": "a889df6a387419ff204305f4c2d296ee328c3cd4f8b62f205648a541b4554dfb",
             "pubkey": "c6047f9441ed7d6d3045406e95c07cd85c778e4b8cef3ca7abac09b95c709ee5",
             "created_at": 1698623783, "kind": 1, "tags": [],
             "content": "hello from the nostr army knife"}
    assert m.event_id(value) == value["id"]  # Hash check ONLY, not a Schnorr verification.


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(version=True),
    lambda d: d.update(version=2),
    lambda d: d.update(operators=[]),
    lambda d: d.update(operators=[OPERATOR, OPERATOR]),
    lambda d: d.update(operators=[RECIPIENT]),
    lambda d: d["prompts"].append(d["prompts"][0].copy()),
    lambda d: d["prompts"][0].update(actions={"pump": "on"}),
    lambda d: d["prompts"][0].update(actions={"vent": "execute"}),
    lambda d: d["prompts"][0].update(actions={}),
    lambda d: d["prompts"][0].update(operator=OTHER),
    lambda d: d["prompts"][0].update(expires_at=NOW.replace(tzinfo=None).isoformat()),
    lambda d: d["prompts"][0].update(expires_at=(NOW + timedelta(days=3)).isoformat()),
    lambda d: d["prompts"][0].update(expires_at=(NOW - timedelta(hours=2)).isoformat()),
    lambda d: d["prompts"][0].update(shell="anything"),
])
def test_policy_is_closed_and_bounded(mutation):
    data = policy_data()
    mutation(data)
    with pytest.raises(m.Refused):
        make_policy(data)


def test_spool_permissions(tmp_path):
    directory = tmp_path / "private"
    spool = m.Spool(directory)
    assert directory.stat().st_mode & 0o777 == 0o700
    assert (directory / "confirmations.sqlite3").stat().st_mode & 0o777 == 0o600
    spool.close()


def test_spool_refuses_world_readable_directory(tmp_path):
    directory = tmp_path / "insecure"
    directory.mkdir(mode=0o755)
    with pytest.raises(m.Refused, match="private"):
        m.Spool(directory)


def test_spool_refuses_database_symlink(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    (directory / "confirmations.sqlite3").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(m.Refused):
        m.Spool(directory)


def test_spool_rejects_unknown_schema(tmp_path):
    directory = tmp_path / "private"
    spool = m.Spool(directory)
    spool.db.execute("PRAGMA user_version=99")
    spool.close()
    with pytest.raises(m.Refused, match="unsupported"):
        m.Spool(directory)


def signed_wrap():
    wrap = {"pubkey": "e" * 64, "kind": 1059, "created_at": int((NOW - timedelta(days=1)).timestamp()),
            "tags": [["p", RECIPIENT]], "content": "encrypted-fixture", "sig": "0" * 128}
    wrap["id"] = m.event_id(wrap)
    return m.canonical(wrap)


def signed_seal(*, author=OPERATOR, tags=(), content="encrypted-rumor-fixture"):
    seal = {"pubkey": author, "kind": 13, "created_at": int(NOW.timestamp()),
            "tags": list(tags), "content": content, "sig": "0" * 128}
    seal["id"] = m.event_id(seal)
    return m.canonical(seal)


@pytest.fixture
def binary(tmp_path):
    path = tmp_path / "nak-fixture"
    path.write_bytes(b"not a real cryptographic implementation")
    path.chmod(0o700)
    return path, sha256(path.read_bytes()).hexdigest()


def test_nak_adapter_verifies_both_signed_layers_and_scrubs_db_secret(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "test-only-bunker-configuration")
    monkeypatch.setenv("THERMAL_DATABASE_URL", "private-dsn-fixture")
    calls = []
    def run(argv, payload, environment, **kwargs):
        calls.append((argv, payload, environment.copy()))
        if argv[-1] == "verify":
            return b""
        return signed_seal() if len(calls) == 2 else m.canonical(event())
    decoder = m.NakDecoder(*binary, runner=run)
    assert decoder.decode(signed_wrap(), RECIPIENT)["pubkey"] == OPERATOR
    assert calls[0][0] == [str(binary[0]), "verify"]
    assert calls[1][0][:4] == [str(binary[0]), "decrypt", "--sender-pubkey", "e" * 64]
    assert calls[1][0][4] == "encrypted-fixture"
    assert calls[2][0] == [str(binary[0]), "verify"]
    assert calls[3][0][:4] == [str(binary[0]), "decrypt", "--sender-pubkey", OPERATOR]
    assert calls[3][0][4] == "encrypted-rumor-fixture"
    assert calls[1][1] == calls[3][1] == b""
    assert "NOSTR_SECRET_KEY" not in calls[0][2]
    assert calls[1][2]["NOSTR_SECRET_KEY"] == "test-only-bunker-configuration"
    assert "NOSTR_SECRET_KEY" not in calls[2][2]
    assert all("THERMAL_DATABASE_URL" not in env for _, _, env in calls)
    assert all("test-only-bunker-configuration" not in arg for argv, _, _ in calls for arg in argv)


def test_nak_seal_signature_failure_never_decrypts_rumor(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    calls = []
    def run(argv, *_args, **_kwargs):
        calls.append(argv)
        if len(calls) == 2:
            return signed_seal()
        if len(calls) == 3:
            raise m.Refused("Nostr cryptographic verification failed")
        return b""
    with pytest.raises(m.Refused, match="verification"):
        m.NakDecoder(*binary, runner=run).decode(signed_wrap(), RECIPIENT)
    assert len(calls) == 3


def test_nak_rejects_raw_rumor_author_mismatch(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    calls = []
    def run(argv, *_args, **_kwargs):
        calls.append(argv)
        if len(calls) == 2:
            return signed_seal()
        if len(calls) == 4:
            return m.canonical(event(operator=OTHER))
        return b""
    with pytest.raises(m.Refused, match="author"):
        m.NakDecoder(*binary, runner=run).decode(signed_wrap(), RECIPIENT)
    assert len(calls) == 4


def test_nak_rejects_nonempty_seal_tags_before_seal_verify(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    calls = []
    def run(argv, *_args, **_kwargs):
        calls.append(argv)
        return signed_seal(tags=[["p", RECIPIENT]]) if len(calls) == 2 else b""
    with pytest.raises(m.Refused, match="seal tags"):
        m.NakDecoder(*binary, runner=run).decode(signed_wrap(), RECIPIENT)
    assert len(calls) == 2


def test_signed_rumor_is_not_accepted(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    signed = {**event(), "sig": "0" * 128}
    calls = []
    def run(argv, *_args, **_kwargs):
        calls.append(argv)
        if len(calls) == 2:
            return signed_seal()
        if len(calls) == 4:
            return m.canonical(signed)
        return b""
    with pytest.raises(m.Refused, match="unsigned"):
        m.NakDecoder(*binary, runner=run).decode(signed_wrap(), RECIPIENT)


def test_nak_verification_failure_never_unwraps(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    calls = []
    def run(argv, *_args, **_kwargs):
        calls.append(argv)
        raise m.Refused("Nostr cryptographic verification failed")
    with pytest.raises(m.Refused):
        m.NakDecoder(*binary, runner=run).decode(signed_wrap(), RECIPIENT)
    assert len(calls) == 1 and calls[0][-1] == "verify"


def test_nak_missing_secret_never_falls_back_to_machine_key(binary, monkeypatch):
    monkeypatch.delenv("NOSTR_SECRET_KEY", raising=False)
    with pytest.raises(m.Refused, match="identity"):
        m.NakDecoder(*binary).decode(signed_wrap(), RECIPIENT)


def test_nak_hash_mismatch_never_runs(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    with pytest.raises(m.Refused, match="hash"):
        m.NakDecoder(binary[0], "f" * 64).decode(signed_wrap(), RECIPIENT)


def test_nak_wrong_recipient_never_runs(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    with pytest.raises(m.Refused, match="addressed"):
        m.NakDecoder(*binary).decode(signed_wrap(), OTHER)


def test_real_subprocess_bounds_echo():
    result = m.run_bounded([sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
                           b"test" * 20000, {}, limit=80000)
    assert result == b"test" * 20000


def test_real_subprocess_timeout_kills_child():
    with pytest.raises(m.Retryable):
        m.run_bounded([sys.executable, "-c", "import time; time.sleep(5)"], b"{}", {}, timeout=0.1)


def test_real_subprocess_output_overflow_kills_child():
    with pytest.raises(m.Retryable, match="bound"):
        m.run_bounded([sys.executable, "-c", "print('x'*10000)"], b"{}", {}, limit=100)


def test_real_subprocess_nonzero_is_not_success():
    with pytest.raises(m.Refused):
        m.run_bounded([sys.executable, "-c", "raise SystemExit(1)"], b"{}", {})


def test_cli_help_is_offline_and_requires_no_secret():
    import subprocess
    result = subprocess.run([sys.executable, str(PATH), "--help"], capture_output=True, timeout=5)
    assert result.returncode == 0
    assert b"--nak-sha256" in result.stdout


def test_prompt_identity_is_bound_to_exact_displayed_question():
    policy = make_policy()
    question = m.prompt_event(policy.prompts[0], RECIPIENT)
    assert question["id"] == PROMPT
    assert question["kind"] == 14
    assert question["tags"] == [["p", OPERATOR]]
    assert question["content"].startswith("THERMAL CONFIRMATION v1")
    assert "Vents: closed" in question["content"]
    assert "Indoor shades: closed" in question["content"]
    assert "sig" not in question  # Unsigned; no accidental public publication.
    data = policy_data()
    data["prompts"][0]["actions"]["vent"] = "open"
    with pytest.raises(m.Refused, match="question"):
        make_policy(data)
    replacement = m.Policy.load(m.canonical(data), assign_ids=True)
    assert replacement.prompts[0].event_id != PROMPT


def test_prepared_policy_roundtrips_strictly():
    data = policy_data()
    del data["prompts"][0]["id"]
    prepared = m.Policy.load(m.canonical(data), assign_ids=True)
    assert m.Policy.load(m.canonical(m.policy_object(prepared))) == prepared
    assert prepared.prompts[0].event_id == PROMPT


def test_cli_policy_preparation_and_rendering_are_offline(tmp_path):
    import subprocess
    path = tmp_path / "policy.json"
    data = policy_data()
    del data["prompts"][0]["id"]
    path.write_bytes(m.canonical(data))
    prepared = subprocess.run([sys.executable, str(PATH), "--policy", str(path), "--prepare-policy"],
                              capture_output=True, timeout=5, env={"PATH": os.environ["PATH"]})
    assert prepared.returncode == 0
    path.write_bytes(prepared.stdout)
    rendered = subprocess.run([sys.executable, str(PATH), "--policy", str(path), "--render-prompts"],
                              capture_output=True, timeout=5, env={"PATH": os.environ["PATH"]})
    assert rendered.returncode == 0
    assert json.loads(rendered.stdout)["id"] == PROMPT
    assert not (tmp_path / "confirmations.sqlite3").exists()


def test_cli_requires_explicit_apply_mode(tmp_path):
    import subprocess
    path = tmp_path / "policy.json"
    path.write_bytes(m.canonical(policy_data()))
    result = subprocess.run([sys.executable, str(PATH), "--policy", str(path)],
                            capture_output=True, timeout=5)
    assert result.returncode == 2
    assert result.stdout == b""
    assert b"--apply" in result.stderr


@pytest.mark.parametrize("change", ["source", "effective_at", "action", "state", "supersedes"])
def test_corrupt_pending_spool_cannot_rewrite_authenticated_report(setup, change):
    setup.journal.fail_append = True
    with pytest.raises(m.Retryable):
        accept(setup)
    row = setup.spool.get(event()["id"])
    records = json.loads(row["records_json"])
    records[0][change] = "corrupted-value"
    with setup.spool.db:
        setup.spool.db.execute("UPDATE receipts SET records_json=? WHERE rumor_id=?",
                               (m.canonical(records).decode(), event()["id"]))
    setup.journal.fail_append = False
    with pytest.raises(m.Refused, match="authenticated"):
        accept(setup)
    assert setup.journal.calls == 1
    assert setup.journal.records == {}


def test_replay_after_clock_rollback_is_not_retimestamped(setup):
    accept(setup)
    with pytest.raises(m.Refused, match="timing"):
        accept(setup, now=NOW - timedelta(seconds=1))
    assert setup.journal.calls == 1


def test_revoked_operator_cannot_replay_previously_accepted_reply(setup):
    accept(setup)
    data = policy_data()
    data["operators"] = [OTHER]
    data["prompts"][0]["operator"] = OTHER
    policy = m.Policy.load(m.canonical(data), assign_ids=True)
    with pytest.raises(m.Refused, match="authorized"):
        accept(setup, policy=policy)
    assert setup.journal.calls == 1


def test_failed_decryption_is_not_accepted_as_an_unsigned_rumor(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    def run(argv, *_args, **_kwargs):
        if argv[-1] == "verify": return b""
        raise m.Refused("Nostr cryptographic verification failed")
    with pytest.raises(m.Refused):
        m.NakDecoder(*binary, runner=run).decode(signed_wrap(), RECIPIENT)


def test_modified_outer_content_rejected_before_crypto_subprocess(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    payload = json.loads(signed_wrap())
    payload["content"] = "tampered"
    with pytest.raises(m.Refused, match="hash"):
        m.NakDecoder(*binary).decode(m.canonical(payload), RECIPIENT)


def test_nak_multi_document_decryption_output_is_rejected(binary, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", "fixture")
    def run(argv, *_args, **_kwargs):
        return (b"" if argv[-1] == "verify"
                else signed_seal() + b"\n" + signed_seal())
    with pytest.raises(m.Refused, match="document"):
        m.NakDecoder(*binary, runner=run).decode(signed_wrap(), RECIPIENT)


@pytest.mark.parametrize("terminal", ["yes", "skip"])
def test_terminal_prompt_cannot_be_reopened_by_not_yet(setup, terminal):
    accept(setup, event(terminal))
    with pytest.raises(m.Refused, match="terminal"):
        accept(setup, event("not yet", at=NOW + timedelta(seconds=1)), now=NOW + timedelta(seconds=1))
    assert setup.spool.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0] == 1
