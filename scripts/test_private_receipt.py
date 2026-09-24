import json
import stat

import pytest

from private_receipt import save_private_json


def test_receipt_is_private_durable_and_exclusive(tmp_path):
    tmp_path.chmod(0o700)
    path = save_private_json(tmp_path, 'recovery-report.json', {'status': 'verified'})
    assert path == tmp_path / 'recovery-report.json'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == {'status': 'verified'}
    assert path.read_bytes().endswith(b'\n')
    with pytest.raises(FileExistsError):
        save_private_json(tmp_path, 'recovery-report.json', {'status': 'overwritten'})
    assert json.loads(path.read_text()) == {'status': 'verified'}


@pytest.mark.parametrize('name', ('../outside.json', 'nested/x.json', '.hidden.json', 'bad.txt'))
def test_receipt_refuses_unsafe_names(tmp_path, name):
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError):
        save_private_json(tmp_path, name, {})


def test_receipt_refuses_public_or_symlinked_directory(tmp_path):
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError):
        save_private_json(tmp_path, 'report.json', {})
    tmp_path.chmod(0o700)
    alias = tmp_path / 'alias'
    alias.symlink_to(tmp_path, target_is_directory=True)
    try:
        with pytest.raises(OSError):
            save_private_json(alias, 'report.json', {})
    finally:
        alias.unlink()
    assert not (tmp_path / 'report.json').exists()


def test_receipt_refuses_non_json_numbers(tmp_path):
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError):
        save_private_json(tmp_path, 'report.json', {'invalid': float('nan')})
    assert not (tmp_path / 'report.json').exists()
