"""Original-capture, natural-run and readback binding; no household writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sys

import pytest

SPEC = importlib.util.spec_from_file_location('natural_publication',
    Path(__file__).with_name('verify-thermal-natural-publication.py'))
v = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(v)
AT = datetime(2026, 10, 3, 3, 35, 57, tzinfo=timezone.utc)


def evidence():
    output = {'status': 'shadow', 'generatedAt': AT.isoformat(),
              'confidence': {'grade': 'low'}}
    capture = {'schema': 'earthship-thermal-shadow-forcing-capture/v2',
        'decision_at': AT.isoformat(), 'inputs_available_at': AT.isoformat(),
        'published_at': (AT + timedelta(milliseconds=200)).isoformat(),
        'sha256': {'output': v.digest(output), 'artifact': 'a' * 64},
        'output': output, 'current': {'radiation': {
            'sourceEvidence': {'snapshotSha256': 'b' * 64}}}}
    run = {'ActiveState': 'inactive', 'MainPID': '0', 'Result': 'success',
        'ExecMainCode': '1', 'ExecMainStatus': '0', 'InvocationID': 'c' * 32,
        'started_us': int((AT - timedelta(seconds=1)).timestamp() * 1_000_000),
        'finished_us': int((AT + timedelta(seconds=1)).timestamp() * 1_000_000),
        'triggered_us': int((AT - timedelta(seconds=1, milliseconds=20)).timestamp() * 1_000_000),
        'timer_active': True}
    rows = [{'time': int((AT + timedelta(milliseconds=250)).timestamp() * 1000),
             'state': json.dumps(output)}]
    return capture, run, deepcopy(output), rows


def test_original_capture_matches_natural_run_live_item_and_jdbc():
    capture, run, output, rows = evidence()
    proof = v.validate_delivery(capture, run=run, live_output=output, rows=rows,
        installed_after=AT-timedelta(minutes=10), assessed_at=AT+timedelta(seconds=10))
    assert proof['invocation_id'] == run['InvocationID']
    assert proof['output_sha256'] == capture['sha256']['output']
    assert proof['artifact_sha256'] == 'a' * 64
    assert proof['radiation_source_sha256'] == 'b' * 64
    assert not proof['learning_enabled'] and not proof['controls_enabled']


@pytest.mark.parametrize('fault', ['busy','pid','failed','signal','exit','invocation',
    'timer_off','manual','before_install','capture_before_run','capture_after_exit',
    'capture_after_assessment','live_drift','history_missing','history_early',
    'history_late','history_future','history_conflict','unavailable','bad_digest'])
def test_no_indirect_evidence_closes_natural_gate(fault):
    capture, run, output, rows = deepcopy(evidence())
    cutoff = AT-timedelta(minutes=10)
    if fault == 'busy': run['ActiveState'] = 'active'
    if fault == 'pid': run['MainPID'] = '123'
    if fault == 'failed': run['Result'] = 'exit-code'
    if fault == 'signal': run['ExecMainCode'] = '2'
    if fault == 'exit': run['ExecMainStatus'] = '1'
    if fault == 'invocation': run['InvocationID'] = 'not-an-invocation'
    if fault == 'timer_off': run['timer_active'] = False
    if fault == 'manual': run['triggered_us'] -= 120_000_000
    if fault == 'before_install': cutoff = AT+timedelta(seconds=1)
    if fault == 'capture_before_run': run['started_us'] += 3_000_000
    if fault == 'capture_after_exit': run['finished_us'] -= 2_000_000
    if fault == 'capture_after_assessment': capture['published_at'] = (AT+timedelta(days=1)).isoformat()
    if fault == 'live_drift': output['generatedAt'] = (AT+timedelta(seconds=2)).isoformat()
    if fault == 'history_missing': rows = []
    if fault == 'history_early': rows[0]['time'] -= 10000
    if fault == 'history_late': rows[0]['time'] += 60000
    if fault == 'history_future': rows[0]['time'] = 9999999999999
    if fault == 'history_conflict':
        changed = deepcopy(capture['output']); changed['status'] = 'other'
        rows.append({'time': rows[0]['time']+1, 'state': json.dumps(changed)})
    if fault == 'unavailable': capture['output']['confidence']['grade'] = 'unavailable'
    if fault == 'bad_digest': capture['sha256']['output'] = '0' * 64
    with pytest.raises(ValueError):
        v.validate_delivery(capture, run=run, live_output=output, rows=rows,
            installed_after=cutoff, assessed_at=AT+timedelta(seconds=10))


def test_installed_import_selection_precedes_recovery_helper(monkeypatch):
    monkeypatch.setattr(sys,'path',list(sys.path))
    class Stop(Exception): pass
    def load():
        assert sys.path[0]==str(v.LIVE)
        raise Stop()
    monkeypatch.setattr(v,'load_rollout',load)
    with pytest.raises(Stop): v.verify(Path('/no-live-reading'))


def rollout_fixture(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('natural_file_test_setup',
        Path(__file__).with_name('test_thermal_radiation_files.py'))
    setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
    receipt,baseline,_=setup.setup(tmp_path,monkeypatch)
    r=setup.r
    r.prepare(receipt);r.apply(receipt)
    capture,run,output,rows=evidence()
    proof=v.validate_delivery(capture,run=run,live_output=output,rows=rows,
        installed_after=AT-timedelta(minutes=10),assessed_at=AT+timedelta(seconds=10))
    return r,receipt,baseline,proof,setup


def test_private_proof_is_pinned_idempotent_and_preserved_through_rollback(tmp_path,monkeypatch):
    r,receipt,baseline,proof,setup=rollout_fixture(tmp_path,monkeypatch)
    before=r._state(receipt)
    assert v.commit_proof(r,receipt,before,proof)==proof
    after=r._state(receipt)
    assert after['status']=='installed_natural_publication_verified'
    assert (receipt/'natural-publication.json').stat().st_mode & 0o777==0o600
    raw=(receipt/'natural-publication.json').read_bytes()
    assert after['natural_publication_sha256']==__import__('hashlib').sha256(raw).hexdigest()
    assert v.commit_proof(r,receipt,after,proof)==proof
    assert r.restore(receipt)['restored_revision']==r.OLD
    setup.assert_original(baseline)
    assert r._state(receipt)['status']=='rolled_back'
    assert (receipt/'natural-publication.json').read_bytes()==raw


def test_interrupted_private_proof_commit_recovers_without_replacing_evidence(tmp_path,monkeypatch):
    r,receipt,_,proof,_=rollout_fixture(tmp_path,monkeypatch)
    before=r._state(receipt)
    save=r._save_state
    def interrupted(*args): raise RuntimeError('test-only interruption before pin')
    monkeypatch.setattr(r,'_save_state',interrupted)
    with pytest.raises(RuntimeError): v.commit_proof(r,receipt,before,proof)
    raw=(receipt/'natural-publication.json').read_bytes()
    assert r._state(receipt)['status']=='installed_waiting_natural_publication'
    monkeypatch.setattr(r,'_save_state',save)
    later={**proof,'verified_at':(AT+timedelta(seconds=20)).isoformat()}
    assert v.commit_proof(r,receipt,before,later)==proof
    assert (receipt/'natural-publication.json').read_bytes()==raw


def test_changed_or_unpinned_proof_refuses_without_runtime_mutation(tmp_path,monkeypatch):
    r,receipt,_,proof,_=rollout_fixture(tmp_path,monkeypatch)
    before=r._state(receipt)
    before['status']='installed_natural_publication_verified'
    r._save_state(receipt,before)
    with pytest.raises(ValueError): r._state(receipt)
    before['status']='installed_waiting_natural_publication'
    r._save_state(receipt,before)
    v.commit_proof(r,receipt,before,proof)
    path=receipt/'natural-publication.json';path.write_bytes(b'changed')
    with pytest.raises(ValueError): r.restore(receipt)
    assert r._revision(r.LIVE)==r.NEW
