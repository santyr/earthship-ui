"""Exact code-only packaging, inactive gates and independent copy recovery."""
from hashlib import sha256
import importlib.util
from pathlib import Path
import shutil

import pytest

SPEC = importlib.util.spec_from_file_location('bundle', Path(__file__).with_name('build-pre-dusk-notification-bundle.py'))
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


def destination(tmp_path):
    path = tmp_path / 'bundle'
    path.mkdir(mode=0o700)
    return path


def test_build_is_exact_private_and_inactive_and_independent_copy_restores(tmp_path):
    path = destination(tmp_path)
    receipt = bundle.build(path)
    assert receipt['files'] == 12
    assert receipt['production_installed'] is False
    assert receipt['credentials_included'] is False
    assert set(p.name for p in path.iterdir()) == set(bundle.FILES) | {'manifest.json'}
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in path.iterdir())
    restored = tmp_path / 'restored'
    shutil.copytree(path, restored)
    assert bundle.verify(restored, receipt['manifest_sha256']) == receipt
    assert all(sha256((path / name).read_bytes()).digest() == sha256((restored / name).read_bytes()).digest()
               for name in (*bundle.FILES, 'manifest.json'))


@pytest.mark.parametrize('case', ['changed', 'missing', 'extra', 'symlink', 'public'])
def test_changed_or_unsafe_bundle_refuses(tmp_path, case):
    path = destination(tmp_path)
    receipt = bundle.build(path)
    target = path / bundle.FILES[0]
    if case == 'changed':
        target.write_bytes(target.read_bytes() + b'\n# altered\n')
    elif case == 'missing':
        target.unlink()
    elif case == 'extra':
        (path / 'unexpected').write_bytes(b'no')
    elif case == 'symlink':
        target.unlink(); target.symlink_to(bundle.ROOT / 'openhab/scripts' / bundle.FILES[0])
    else:
        target.chmod(0o644)
    with pytest.raises(ValueError):
        bundle.verify(path, receipt['manifest_sha256'])


def test_existing_output_is_never_overwritten(tmp_path):
    path = destination(tmp_path)
    owned = path / 'existing'
    owned.write_bytes(b'preserve')
    with pytest.raises(ValueError):
        bundle.build(path)
    assert owned.read_bytes() == b'preserve'


@pytest.mark.parametrize('name,gate', [('pre_dusk_notification.py', 'RELEASE_READY'),
    ('thermal_messaging.py', 'POLL_RELEASE_READY'),
    ('thermal_messaging.py', 'POSITION_DELIVERY_RELEASE_READY')])
def test_active_gate_prevents_all_output_writes(tmp_path, name, gate):
    source = tmp_path / 'source'
    shutil.copytree(bundle.ROOT / 'openhab/scripts', source,
                    ignore=lambda directory, names: [n for n in names if n not in bundle.FILES])
    target = source / name
    raw = target.read_text().replace(gate + ' = False', gate + ' = True')
    target.write_text(raw)
    path = destination(tmp_path)
    with pytest.raises(ValueError, match='inactive'):
        bundle.build(path, source)
    assert list(path.iterdir()) == []
