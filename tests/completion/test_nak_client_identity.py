"""Subprocess identity isolation tests; no real bunker, keys, or network."""
from hashlib import sha256
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "client_identity_thermal", ROOT / "openhab/scripts/thermal_confirmation.py"
)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
RECIPIENT = "b" * 64
CLIENT = "disposable-client-key-sentinel"
SIGNER = "disposable-signer-configuration-sentinel"


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    monkeypatch.setenv("NOSTR_SECRET_KEY", SIGNER)
    monkeypatch.delenv("NOSTR_CLIENT_KEY", raising=False)
    path = tmp_path / "nak"
    data = b"unit test double; never executed"
    path.write_bytes(data)
    path.chmod(0o700)
    wrap = {"pubkey": "e" * 64, "created_at": 1789990000, "kind": 1059,
            "tags": [["p", RECIPIENT]], "content": "encrypted-fixture", "sig": "0" * 128}
    wrap["id"] = m.event_id(wrap)
    rumor = {"pubkey": "a" * 64, "created_at": 1789990001, "kind": 14,
             "tags": [["p", RECIPIENT]], "content": "yes"}
    rumor["id"] = m.event_id(rumor)
    calls = []

    def run(argv, payload, environment, **kwargs):
        # Retain the object too: later mutation must not add secrets to verify.
        calls.append((argv, payload, environment))
        return b"" if argv[-1] == "verify" else m.canonical(rumor)

    decoder = m.NakDecoder(path, sha256(data).hexdigest(), runner=run)
    return decoder, m.canonical(wrap), calls


def test_configured_client_identity_reaches_only_unwrap(adapter, monkeypatch):
    decoder, wrap, calls = adapter
    monkeypatch.setenv("NOSTR_CLIENT_KEY", CLIENT)
    assert decoder.decode(wrap, RECIPIENT)["pubkey"] == "a" * 64
    assert [argv[1:] for argv, _, _ in calls] == [["verify"], ["gift", "unwrap"]]
    assert calls[0][1] == calls[1][1]
    assert calls[0][2] is not calls[1][2]
    assert {"NOSTR_SECRET_KEY", "NOSTR_CLIENT_KEY"}.isdisjoint(calls[0][2])
    assert calls[1][2]["NOSTR_SECRET_KEY"] == SIGNER
    assert calls[1][2]["NOSTR_CLIENT_KEY"] == CLIENT
    assert all(CLIENT not in arg and SIGNER not in arg
               for argv, _, _ in calls for arg in argv)


@pytest.mark.parametrize("value", [None, ""])
def test_absent_client_key_does_not_invent_or_export_a_key(adapter, monkeypatch, value):
    decoder, wrap, calls = adapter
    if value is not None:
        monkeypatch.setenv("NOSTR_CLIENT_KEY", value)
    decoder.decode(wrap, RECIPIENT)
    assert all("NOSTR_CLIENT_KEY" not in env for _, _, env in calls)


@pytest.mark.parametrize("name", ["THERMAL_DATABASE_URL", "OPENHAB_TOKEN",
                                  "OPENHAB_API_KEY", "GITHUB_TOKEN", "LD_PRELOAD"])
def test_unrelated_credentials_and_loader_environment_stay_out(adapter, monkeypatch, name):
    decoder, wrap, calls = adapter
    monkeypatch.setenv("NOSTR_CLIENT_KEY", CLIENT)
    monkeypatch.setenv(name, "must-not-reach-nak")
    decoder.decode(wrap, RECIPIENT)
    assert all(name not in env for _, _, env in calls)


def test_client_key_is_not_a_substitute_for_signer_configuration(adapter, monkeypatch):
    decoder, wrap, calls = adapter
    monkeypatch.delenv("NOSTR_SECRET_KEY")
    monkeypatch.setenv("NOSTR_CLIENT_KEY", CLIENT)
    with pytest.raises(m.Refused, match="identity configuration"):
        decoder.decode(wrap, RECIPIENT)
    assert calls == []


def test_failed_outer_verification_never_exposes_keys_to_unwrap(adapter, monkeypatch):
    decoder, wrap, calls = adapter
    monkeypatch.setenv("NOSTR_CLIENT_KEY", CLIENT)

    def refuse(argv, payload, environment, **kwargs):
        calls.append((argv, payload, environment))
        raise m.Refused("Nostr cryptographic verification failed")

    decoder.runner = refuse
    with pytest.raises(m.Refused, match="cryptographic verification"):
        decoder.decode(wrap, RECIPIENT)
    assert len(calls) == 1
    assert calls[0][0][1:] == ["verify"]
    assert {"NOSTR_SECRET_KEY", "NOSTR_CLIENT_KEY"}.isdisjoint(calls[0][2])
