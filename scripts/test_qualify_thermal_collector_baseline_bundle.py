"""Empty-baseline recovery guards; real PostgreSQL integration is adjacent."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('baseline_bundle', ROOT/'scripts/qualify-thermal-collector-baseline-bundle.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def baseline(tmp_path):
    state = tmp_path/'state'
    state.mkdir(mode=0o700)
    spool, outbox = p.t.Spool(state), p.m.Outbox(state)
    spool.close()
    outbox.close()
    return state


def test_pair_reopens_through_real_classes_without_work(tmp_path):
    state = baseline(tmp_path)
    p.empty_state(state)
    p.restore_sqlite_pair(state, tmp_path/'restored')
    p.empty_state(tmp_path/'restored')


def test_nonempty_baseline_is_not_silently_snapshotted(tmp_path):
    state = baseline(tmp_path)
    outbox = p.m.Outbox(state)
    try:
        outbox.db.execute('INSERT INTO inbox_refused VALUES (?,?,?,?,?)', ('a'*64, 'b'*64, 1, 0, 0))
        outbox.db.commit()
    finally:
        outbox.close()
    with pytest.raises(ValueError, match='live state'):
        p.empty_state(state)


def test_sending_policy_refuses_before_config_or_database(tmp_path):
    with pytest.raises(ValueError, match='proposed'):
        p.qualify(tmp_path/'state', tmp_path/'policy.json', tmp_path/'routes.json',
                  tmp_path/'bundle', ROOT/'openhab/scripts', '0'*64)
    assert list(tmp_path.iterdir()) == []


def test_open_release_gate_refuses_before_any_state_access(tmp_path, monkeypatch):
    monkeypatch.setattr(p.m, 'POSITION_DELIVERY_RELEASE_READY', True)
    with pytest.raises(p.t.Refused, match='release gates'):
        p.qualify(tmp_path/'state', tmp_path/'policy.proposed.json', tmp_path/'routes.json',
                  tmp_path/'bundle', ROOT/'openhab/scripts', '0'*64)
    assert list(tmp_path.iterdir()) == []


def test_unknown_source_schema_refuses_before_configuration_or_database(tmp_path):
    with pytest.raises(ValueError, match='exact v1 or v2'):
        p.qualify(tmp_path/'state', tmp_path/'policy.proposed.json', tmp_path/'routes.json',
                  tmp_path/'bundle', ROOT/'openhab/scripts', '0'*64, source_schema='auto')
    assert list(tmp_path.iterdir()) == []
