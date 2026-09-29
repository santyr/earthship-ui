"""Offline checks for the legacy DM script; never use household keys or relays."""

import json
import os
import subprocess
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / "openhab/scripts/nostr_notify.sh"
TEST_KEY = "0" * 63 + "1"
TEST_PUB = "79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"


def test_dm_sender_key_stays_out_of_argv_and_publish_environment(tmp_path):
    config = tmp_path / "notifier.env"
    config.write_text(
        f"NOSTR_SECRET_KEY_HEX={TEST_KEY}\n"
        f"NOTIFY_PUBKEY_HEX={TEST_PUB}\n"
        "RELAYS=wss://relay.invalid\n"
    )
    config.chmod(0o600)
    log = tmp_path / "nak-calls.jsonl"
    fake_nak = tmp_path / "nak"
    fake_nak.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['CALL_LOG'], 'a') as log:\n"
        "    log.write(json.dumps({'args': args, 'has_key': 'NOSTR_SECRET_KEY' in os.environ}) + '\\n')\n"
        "if 'encrypt' in args:\n"
        "    assert os.environ['NOSTR_SECRET_KEY'] == os.environ['TEST_KEY']\n"
        "    print('disposable-ciphertext')\n"
        "elif 'event' in args and not any(a.startswith('wss://') for a in args):\n"
        "    assert os.environ['NOSTR_SECRET_KEY'] == os.environ['TEST_KEY']\n"
        "    body = json.load(sys.stdin)\n"
        "    assert body['content'] == 'disposable-ciphertext'\n"
        "    print(json.dumps(body))\n"
        "elif 'event' in args:\n"
        "    assert 'NOSTR_SECRET_KEY' not in os.environ\n"
        "    print('success', file=sys.stderr)\n"
        "else:\n"
        "    sys.exit(2)\n"
    )
    fake_nak.chmod(0o700)
    script = tmp_path / "nostr_notify.sh"
    script.write_text(
        SOURCE.read_text()
        .replace("/etc/openhab/misc/nostr_notify.env", str(config))
        .replace("NAK=/etc/openhab/scripts/nak", f"NAK={fake_nak}")
    )
    env = os.environ.copy()
    env.update(CALL_LOG=str(log), TEST_KEY=TEST_KEY)
    result = subprocess.run(
        ["bash", str(script), "disposable message"],
        env=env, text=True, capture_output=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "DM sent" in result.stdout
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 3
    assert [call["has_key"] for call in calls] == [True, True, False]
    assert all("--sec" not in call["args"] for call in calls)
    assert TEST_KEY not in result.stdout + result.stderr
