"""Provisioning preflight must refuse collisions without issuing SQL writes."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('advisory_provision', Path(__file__).resolve().parents[2] / 'scripts/provision-advisory-roles.py')
provision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provision)


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(provision, 'CONFIG', tmp_path / 'private.env')
    monkeypatch.setattr(provision.sys, 'argv', ['provision'])
    calls = []
    def read_only(sql):
        assert sql.startswith('SELECT ')
        calls.append(sql)
        if 'pg_roles' in sql: return ''
        if 'schema_migrations' in sql: return '1\n2\n3\n4'
        if 'public.items' in sql: return '613'
        pytest.fail('unexpected SQL')
    monkeypatch.setattr(provision, 'sql', read_only)
    return calls


def test_dry_run_is_read_only(setup):
    provision.main()
    assert len(setup) == 3
    assert not provision.CONFIG.exists()


def test_existing_config_refuses_before_database(setup):
    provision.CONFIG.write_text('fixture')
    with pytest.raises(RuntimeError, match='configuration already exists'): provision.main()
    assert setup == []


def test_dangling_config_symlink_refuses_before_database(setup, tmp_path):
    provision.CONFIG.symlink_to(tmp_path / 'absent')
    with pytest.raises(RuntimeError, match='configuration already exists'): provision.main()
    assert setup == []


@pytest.mark.parametrize('marker,value,reason', [
    ('pg_roles','advisory_writer','collision'),
    ('schema_migrations','1\n2','ledger mismatch'),
    ('public.items','613\n614','mapping drift'),
    ('public.items','999','mapping drift'),
])
def test_preflight_drift_refuses_without_writes(setup, monkeypatch, marker, value, reason):
    previous = provision.sql
    monkeypatch.setattr(provision, 'sql', lambda sql: value if marker in sql else previous(sql))
    with pytest.raises(RuntimeError, match=reason): provision.main()
    assert not provision.CONFIG.exists()
