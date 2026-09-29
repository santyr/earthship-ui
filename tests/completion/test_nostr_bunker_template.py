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


def test_earthship_instance_selects_only_approved_sat_client():
    config = (DEPLOY / 'earthship-operator.env.example').read_text()
    settings = [line for line in config.splitlines()
                if line and not line.startswith('#')]
    assert settings == [
        ('BUNKER_AUTHORIZED_CLIENTS="'
         '5302cd2bfe2dcc76c5a9abcba74e6c5f1a07444b35c25e0cd74bac5b453fb5f6"'),
        ('BUNKER_RELAYS="wss://nos.lol wss://relay.primal.net '
         'wss://relay.damus.io"'),
        ('NAK_SHA256='
         'ba918fafd1b030bc50958a5b218c6386f4c3a57c1e469562d3947e858e0ba56e'),
    ]
    assert '4bf9fcbda64b18e885ce04d593c37264d3561a1baf3adb8c3fe01b1a8bc7edde' not in config
    assert '669ebbcccf409ee0467a33660ae88fd17e5379e646e41d7c236ff4963f3c36b6' not in config


def test_operator_helpers_are_offline_by_default_and_keep_secret_out_of_argv():
    verifier = DEPLOY / 'verify-earthship-operator-credential'
    publisher = DEPLOY / 'publish-earthship-operator-route'
    for helper in (verifier, publisher):
        subprocess.run(['sh', '-n', str(helper)], check=True)
        source = helper.read_text()
        assert 'systemd-creds decrypt --name=nostr-key "$KEY" -' in source
        assert '--sec "$secret"' not in source
        assert 'set +x' in source
        result = subprocess.run(['sh', str(helper)], capture_output=True,
                                text=True, env={}, check=False)
        assert result.returncode != 0
        assert 'run as root' in result.stderr
    source = publisher.read_text()
    assert source.count('-t "relay=$RELAY_') == 3
    assert '"$CHECKER" >/dev/null' in source
    assert 'operator route already exists' in source
    assert 'operator route published and verified on 3/3 relays' in source
