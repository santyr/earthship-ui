"""NIP-19 CLI input tests; no household key, signer, relay or database access."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'openhab/scripts'))
import thermal_confirmation as t

spec = importlib.util.spec_from_file_location(
    'collector_input_messaging', ROOT / 'openhab/scripts/thermal_messaging.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# Independent published NIP-19 vectors, not household identities.
VECTORS = (
    ('npub180cvv07tjdrrgpa0j7j7tmnyl2yr6yr7l8j4s3evf6u64th6gkwsyjh6w6',
     '3bf0c63fcb93463407af97a5e5ee64fa883d107ef9e558472c4eb9aaaefa459d'),
    ('npub10elfcs4fr0l0r8af98jlmgdh9c8tcxjvz9qkw038js35mp4dma8qzvjptg',
     '7e7e9c42a91bfef19fa929e5fda1b72e0ebc1a4c1141673e2794234d86addf4e'),
)
NPUB, HEX = VECTORS[0]
ALPHABET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
ERROR = 'collector must be a 64-character hex public key or a valid npub'


def encoded_words(hrp, words, constant=1):
    """BIP-173 reference-style encoder for deliberately malformed fixtures."""
    generators = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    values = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    chk = 1
    for v in values + words + [0] * 6:
        top = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ v
        for i in range(5):
            chk ^= generators[i] if ((top >> i) & 1) else 0
    chk ^= constant
    return hrp + '1' + ''.join(ALPHABET[w] for w in words +
                               [(chk >> 5 * (5 - i)) & 31 for i in range(6)])


@pytest.mark.parametrize('npub,hex_key', VECTORS)
@pytest.mark.parametrize('form', ['npub', 'upper_npub', 'hex', 'upper_hex'])
def test_published_vectors_normalize(npub, hex_key, form):
    value = {'npub': npub, 'upper_npub': npub.upper(),
             'hex': hex_key, 'upper_hex': hex_key.upper()}[form]
    assert m.collector_public_key(value) == hex_key


def test_mixed_case_hex_is_not_subject_to_bech32_case_rule():
    assert m.collector_public_key(HEX[:32].upper() + HEX[32:]) == HEX


@pytest.mark.parametrize('index', range(len(NPUB)))
def test_single_character_corruption_is_not_corrected(index):
    replacement = 'q' if NPUB[index] != 'q' else 'p'
    value = NPUB[:index] + replacement + NPUB[index + 1:]
    with pytest.raises(t.Refused, match=ERROR):
        m.collector_public_key(value)


@pytest.mark.parametrize('value', [None, 123, True, b'not-a-key', '', 'a' * 63,
    'a' * 65, 'g' * 64, '0x' + HEX, '02' + HEX, ' ' + NPUB, NPUB + '\n',
    'nostr:' + NPUB, 'https://example.org/' + NPUB, 'nPub' + NPUB[4:],
    'npub1' + NPUB[5:].upper(), 'npub1' + '0' * 58, '\u212a' * 63])
def test_invalid_inputs_are_refused_without_echo(value):
    with pytest.raises(t.Refused) as error:
        m.collector_public_key(value)
    assert str(error.value) == ERROR


@pytest.mark.parametrize('hrp', ['nsec', 'note', 'nprofile', 'nevent', 'bc'])
def test_other_bech32_entity_types_are_not_public_keys(hrp):
    words = [ALPHABET.index(char) for char in NPUB[5:-6]]
    with pytest.raises(t.Refused, match=ERROR):
        m.collector_public_key(encoded_words(hrp, words))


def test_rejects_bech32m_even_with_valid_bech32m_checksum():
    words = [ALPHABET.index(char) for char in NPUB[5:-6]]
    with pytest.raises(t.Refused, match=ERROR):
        m.collector_public_key(encoded_words('npub', words, 0x2bc830a3))


@pytest.mark.parametrize('padding', [1, 2, 4, 8, 15])
def test_nonzero_padding_is_rejected_even_with_valid_checksum(padding):
    words = [ALPHABET.index(char) for char in NPUB[5:-6]]
    words[-1] |= padding
    with pytest.raises(t.Refused, match=ERROR):
        m.collector_public_key(encoded_words('npub', words))


@pytest.mark.parametrize('length', [0, 49, 50, 51, 53, 54, 55, 100])
def test_payload_length_must_be_32_bytes(length):
    with pytest.raises(t.Refused, match=ERROR):
        m.collector_public_key(encoded_words('npub', [0] * length))


@pytest.mark.parametrize('value', [NPUB, NPUB.upper(), HEX, HEX.upper()])
def test_cli_passes_only_canonical_hex_to_keyer(monkeypatch, capsys, value):
    calls = []
    def checked(collector):
        calls.append(collector)
        assert collector == HEX
        return {'status': 'passed', 'message_published': False}
    monkeypatch.setattr(m, 'Keyer', lambda *a: SimpleNamespace(check_identity=checked))
    assert m.main(['--check-keyer', '--collector', value]) == 0
    assert calls == [HEX]
    assert json.loads(capsys.readouterr().out)['status'] == 'passed'


def test_invalid_cli_input_never_reaches_signer_or_leaks_input(monkeypatch, capsys):
    def no_signer(*args):
        pytest.fail('invalid collector input reached the signer')
    monkeypatch.setattr(m, 'Keyer', lambda *a: SimpleNamespace(check_identity=no_signer))
    private = encoded_words('nsec', [0] * 52)  # Public dummy fixture, never a real key.
    assert m.main(['--check-keyer', '--collector', private]) == 2
    output = capsys.readouterr()
    assert private not in output.out + output.err
    assert output.out == '' and ERROR in output.err


def test_policy_recipient_path_still_works(monkeypatch, capsys):
    def checked(collector):
        assert collector == HEX
        return {'status': 'passed'}
    monkeypatch.setattr(m, 'Keyer', lambda *a: SimpleNamespace(check_identity=checked))
    monkeypatch.setattr(m, 'read_private', lambda path: b'private-policy-fixture')
    monkeypatch.setattr(t.Policy, 'load', lambda raw: SimpleNamespace(recipient=HEX))
    assert m.main(['--check-keyer', '--policy', '/unused-policy']) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'passed'


def test_normalization_does_not_weaken_actual_signer_identity_check(monkeypatch, capsys):
    # Exercise the real check_identity/sign comparison with a wrong signed author.
    keyer = m.Keyer(m.DEFAULT_NAK, m.DEFAULT_SHA256)
    def call(args, payload=b'', **kwargs):
        event = t.strict_json(payload)
        event['pubkey'] = VECTORS[1][1]
        event['id'] = t.event_id(event)
        event['sig'] = '0' * 128
        return t.canonical(event)
    monkeypatch.setattr(keyer, 'call', call)
    monkeypatch.setattr(keyer, 'verify', lambda event, kind: event)
    monkeypatch.setattr(m, 'Keyer', lambda *a: keyer)
    assert m.main(['--check-keyer', '--collector', NPUB]) == 2
    assert 'keyer identity mismatch' in capsys.readouterr().err


def test_core_event_identity_validation_still_rejects_npub():
    with pytest.raises(t.Refused, match='invalid event identity'):
        t.identifier(NPUB)


def test_help_advertises_both_input_forms(capsys):
    with pytest.raises(SystemExit) as done:
        m.main(['--help'])
    assert done.value.code == 0
    assert '64-character hex or npub' in ' '.join(capsys.readouterr().out.split())
