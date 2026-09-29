"""Source-only isolation checks; never start a signer or access a real key."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / 'deploy' / 'nostr-bunker'


def test_launcher_has_valid_shell_syntax_and_requires_instance_inputs():
    launcher = DEPLOY / 'run-nak-bunker'
    subprocess.run(['sh', '-n', str(launcher)], check=True)
    result = subprocess.run(['sh', str(launcher)], capture_output=True, text=True,
                            env={}, check=False)
    assert result.returncode != 0
    assert 'missing systemd credentials directory' in result.stderr
    assert 'NOSTR_SECRET_KEY' not in result.stderr


def test_unit_is_per_identity_and_disabled_until_installed():
    unit = (DEPLOY / 'nostr-bunker@.service').read_text()
    assert 'RuntimeDirectory=nostr-bunker-%i' in unit
    assert 'EnvironmentFile=/etc/nostr-bunker/%i.env' in unit
    assert ('LoadCredentialEncrypted=nostr-key:'
            '/etc/credstore.encrypted/nostr-bunker-%i.key') in unit
    assert 'ProtectHome=yes' in unit
    assert 'DynamicUser=yes' in unit
    assert 'LimitCORE=0' in unit
    assert 'ExecStart=/usr/local/libexec/nostr-bunker/run-nak-bunker' in unit


def test_launcher_never_puts_secret_in_arguments_or_uses_project_fallback():
    launcher = (DEPLOY / 'run-nak-bunker').read_text()
    assert 'NAK_BIN=/usr/local/libexec/nostr-bunker/nak' in launcher
    assert 'sha256sum "$NAK_BIN"' in launcher
    assert 'export NOSTR_SECRET_KEY' in launcher
    assert 'exec "$NAK_BIN" --config-path "$RUNTIME_DIRECTORY" "$@"' in launcher
    assert '--authorized-keys "$client"' in launcher
    assert '--sec "$NOSTR_SECRET_KEY"' not in launcher
    assert 'lightning-goats-nostr.key' not in launcher
