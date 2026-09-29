"""Offline checks for the attended greywater SoC-evidence release preflight."""

import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).with_name('deploy-greywater-soc-evidence.py')
spec = importlib.util.spec_from_file_location('greywater_soc_release', PATH)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def item(state):
    return {'state': state}


def test_exact_transition_hashes_are_pinned():
    assert release.guard.OLD_SHA == '312cf24ceba5c63e30c4ecd0104bbf3bcf646f1e203b8c6c9c964e58dd7b84df'
    assert release.guard.NEW_SHA == release.guard.digest(release.guard.SOURCE.read_text())


def test_valid_receipt_reaches_existing_rollback_adapter(monkeypatch):
    states = {
        '/items/BMS_Comms_Status': item('OK'),
        '/items/BMS_SOC_Evidence_JSON': item('{"soc":74}'),
        '/items/BMS_SOC': item('74'),
    }
    calls = []
    monkeypatch.setattr(release.guard.oh, 'get', states.__getitem__)
    monkeypatch.setattr(release.guard.oh, 'atomic_soc_freshness', lambda *_: None)
    monkeypatch.setattr(release.guard, 'main', lambda: calls.append('guarded'))
    release.main()
    assert calls == ['guarded']


@pytest.mark.parametrize(('comms', 'problem', 'held'), [
    ('STALE age=1s', None, '74'),
    ('OK', 'unavailable', '74'),
    ('OK', None, '73'),
])
def test_bad_evidence_never_reaches_adapter(monkeypatch, comms, problem, held):
    states = {
        '/items/BMS_Comms_Status': item(comms),
        '/items/BMS_SOC_Evidence_JSON': item('{"soc":74}'),
        '/items/BMS_SOC': item(held),
    }
    calls = []
    monkeypatch.setattr(release.guard.oh, 'get', states.__getitem__)
    monkeypatch.setattr(release.guard.oh, 'atomic_soc_freshness', lambda *_: problem)
    monkeypatch.setattr(release.guard, 'main', lambda: calls.append('guarded'))
    with pytest.raises(RuntimeError):
        release.main()
    assert calls == []
