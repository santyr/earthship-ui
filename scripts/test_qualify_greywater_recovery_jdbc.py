"""No-hardware contracts for the protected greywater recovery rehearsal."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).with_name('qualify-greywater-recovery-jdbc.py')
spec = importlib.util.spec_from_file_location('greywater_jdbc_qualification', PATH)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_current_candidate_is_exactly_pinned():
    assert probe.sha(probe.SOURCE.read_bytes()) == probe.CANDIDATE_SHA


def test_unreviewed_candidate_refused_before_live_read_or_container_creation(monkeypatch):
    monkeypatch.setattr(probe, 'SOURCE', SimpleNamespace(read_bytes=lambda: b'changed'))
    monkeypatch.setattr(probe.runtime.oh, 'get', lambda *_: pytest.fail('unexpected production read'))
    monkeypatch.setattr(probe.runtime, 'run', lambda *_: pytest.fail('unexpected container operation'))
    with pytest.raises(RuntimeError, match='candidate drift'): probe.main()


def test_transient_observation_is_retried_not_marked_success(monkeypatch):
    calls = []
    def check():
        calls.append('observe')
        if len(calls) == 1: raise RuntimeError('temporary startup failure')
        return 'actual-proof'
    def bounded_wait(callback, **_):
        assert callback() is False
        return callback()
    monkeypatch.setattr(probe.provider, 'wait_for', bounded_wait)
    assert probe.wait_for(check) == 'actual-proof'


@pytest.mark.parametrize('table', ['item1', 'item0659', 'Item0034'])
def test_only_generated_item_table_names_can_be_fault_targets(table):
    assert probe.fault_sql(table, deny=True) == f'REVOKE INSERT ON TABLE public."{table}" FROM greywater_qualification;'
    assert probe.fault_sql(table, deny=False) == f'GRANT INSERT ON TABLE public."{table}" TO greywater_qualification;'


@pytest.mark.parametrize('table', ['items', 'item1; DROP TABLE items', 'other', 'item_2', ''])
def test_unresolved_or_unowned_fault_targets_refused(table):
    with pytest.raises(RuntimeError): probe.fault_sql(table, deny=True)


def test_refusal_proof_requires_both_off_and_no_transient_on():
    good = {name: 'OFF' for name in probe.PUMPS}
    good['SouthOutlet_AutoStatus'] = 'reason=ledger_recovery_failed,other=field'
    probe.check_refusal(good, '')
    with pytest.raises(RuntimeError): probe.check_refusal({**good, probe.PUMPS[0]: 'ON'}, '')
    with pytest.raises(RuntimeError): probe.check_refusal(good,
        f"[ItemCommandEvent] - Item '{probe.PUMPS[1]}' received command ON")
    with pytest.raises(RuntimeError): probe.check_refusal({**good,
        'SouthOutlet_AutoStatus': 'reason=invalid_soc_evidence'}, '')
