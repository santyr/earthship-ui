"""Frozen collector code staging; no credentials, network, journal or services."""
import importlib.util
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('primal_runtime', ROOT/'scripts/thermal-primal-runtime.py')


def load_runtime():
    assert SPEC.origin and Path(SPEC.origin).is_file(), 'isolated runtime stager is missing'
    module = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(module)
    return module


def test_frozen_code_runs_default_off_without_shared_openhab_or_solarpv(tmp_path):
    runtime = load_runtime()
    target = tmp_path/'release'
    result = runtime.stage(ROOT/'openhab/scripts', target)
    assert result['status'] == 'inactive_code_staged'
    assert result['release_enabled'] is False and result['files'] == 9
    command = subprocess.run([sys.executable, '-S', str(target/'code/thermal_primal.py'),
                              '--poll-replies', '--state-dir', str(tmp_path/'state')],
                             capture_output=True, text=True, timeout=10,
                             env={'PATH': os.defpath, 'PYTHONPATH': str(target/'code'),
                                  'PYTHONDONTWRITEBYTECODE': '1'})
    assert command.returncode == 2 and 'refused' in command.stderr
    assert not (tmp_path/'state').exists()
    assert runtime.verify(target, result['manifest_sha256'])['files'] == 9


def test_existing_release_is_never_overwritten(tmp_path):
    runtime = load_runtime()
    target = tmp_path/'release'; target.mkdir(mode=0o700)
    marker = target/'keep'; marker.write_bytes(b'existing deployment')
    with pytest.raises(ValueError, match='existing'):
        runtime.stage(ROOT/'openhab/scripts', target)
    assert marker.read_bytes() == b'existing deployment' and list(target.iterdir()) == [marker]


@pytest.mark.parametrize('change', ['gate', 'symlink', 'syntax'])
def test_invalid_source_refuses_before_destination_creation(tmp_path, change):
    runtime = load_runtime()
    source = tmp_path/'source'
    for name in runtime.FILES:
        path = source/name; path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/'openhab/scripts'/name, path)
    target = tmp_path/'release'
    changed = source/'thermal_nip04.py'
    if change == 'gate':
        changed.write_text(changed.read_text().replace('PRIMAL_RELEASE_READY = False',
                                                      'PRIMAL_RELEASE_READY = True'))
    elif change == 'syntax':
        changed.write_text('this is not valid Python !')
    else:
        changed.unlink(); changed.symlink_to(ROOT/'openhab/scripts/thermal_nip04.py')
    with pytest.raises(ValueError):
        runtime.stage(source, target)
    assert not target.exists()


@pytest.mark.parametrize('change', ['bytes', 'extra', 'manifest', 'permission'])
def test_frozen_runtime_tampering_refuses_independently_pinned_manifest(tmp_path, change):
    runtime = load_runtime()
    target = tmp_path/'release'
    result = runtime.stage(ROOT/'openhab/scripts', target)
    if change == 'bytes':
        with (target/'code/thermal_nip04.py').open('ab') as output:
            output.write(b'\n# changed source\n')
    elif change == 'extra':
        (target/'code/sitecustomize.py').write_text('raise RuntimeError("unreviewed")')
    elif change == 'permission':
        (target/'code/thermal_primal.py').chmod(0o666)
    else:
        with (target/'code-manifest.json').open('ab') as output:
            output.write(b' ')
    with pytest.raises(ValueError):
        runtime.verify(target, result['manifest_sha256'])


def test_private_environment_preserves_values_without_shell_expansion(tmp_path):
    runtime = load_runtime()
    values = {'NOSTR_SECRET_KEY': '1'*64,
              'THERMAL_DATABASE_URL': 'postgresql://synthetic:p$ss\\"word@127.0.0.1/openhab',
              'THERMAL_DATABASE_RUNTIME_ROLE': 'fixture_writer',
              'THERMAL_DATABASE_EXPECTED_OWNER': 'fixture_owner',
              'EARTHSHIP_PRIMAL_NAK': '/absolute/signer',
              'EARTHSHIP_PRIMAL_NAK_SHA256': 'a'*64,
              'EARTHSHIP_PRIMAL_NAK_VERSION': 'nak version synthetic candidate'}
    path = tmp_path/'runtime.env'
    runtime.write_environment(path, values)
    assert path.stat().st_mode & 0o777 == 0o600
    decoded = {key: shlex.split(value)[0]
               for key, value in (line.split('=', 1) for line in path.read_text().splitlines())}
    assert decoded == values
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        runtime.write_environment(path, values)
    assert path.read_bytes() == original


@pytest.mark.parametrize('change', ['extra', 'missing', 'newline'])
def test_environment_scope_or_control_character_refuses_before_write(tmp_path, change):
    runtime = load_runtime()
    values = {name: 'synthetic' for name in runtime.ENVIRONMENT_KEYS}
    if change == 'extra':
        values['UNREVIEWED_OPERATOR_SECRET'] = 'synthetic-secret'
    elif change == 'missing':
        del values['NOSTR_SECRET_KEY']
    else:
        values['NOSTR_SECRET_KEY'] = 'synthetic\nINJECTED=value'
    path = tmp_path/'runtime.env'
    with pytest.raises(ValueError):
        runtime.write_environment(path, values)
    assert not path.exists()
