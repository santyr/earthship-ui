"""Advice publication is isolated from forecast/device paths and binds original context."""
from pathlib import Path
from datetime import timedelta
import importlib,json
import pytest
from test_household_advice_contract import snapshot,policy,state
from local_measurement_test_support import NOW
from household.codec import canonical,identity


def api():return importlib.import_module('household_advice')


def test_missing_real_policy_publishes_precise_independent_blockers(tmp_path):
    tmp_path.chmod(0o700)
    result=api().publish_advice(snapshot=snapshot(),projections={},directory=tmp_path,now=NOW,guard=lambda:None)
    report=json.loads((tmp_path/'advice.json').read_text())
    assert result['status']=='written'
    assert {r['reason'] for r in report['domains'].values()}=={'operator_policy_missing'}
    assert (tmp_path/'advice.json').stat().st_mode&0o777==0o600


def test_original_inputs_replay_and_noop_keeps_publication_stable(tmp_path):
    tmp_path.chmod(0o700);p=tmp_path/'advice-policy.json';p.write_bytes(canonical(policy()));p.chmod(0o600)
    s=state();source=dict(schema='earthship-household-operator-state/v1',declarations=s['declarations'],checks={});p=tmp_path/'advice-operator-state.json';p.write_bytes(canonical(source));p.chmod(0o600)
    solar=dict(snapshot_id=snapshot().snapshot_id,source_ref='d'*64,available_at=NOW.isoformat(),valid_until=(NOW+timedelta(seconds=100)).isoformat(),direct_gain_available=True)
    api().publish_advice(snapshot=snapshot(),projections={'solar':solar},directory=tmp_path,now=NOW,guard=lambda:None)
    old=(tmp_path/'advice.json').read_bytes();stamp=(tmp_path/'advice.json').stat().st_mtime_ns
    assert api().publish_advice(snapshot=snapshot(),projections={'solar':solar},directory=tmp_path,now=NOW,guard=lambda:None)['status']=='unchanged'
    assert (tmp_path/'advice.json').stat().st_mtime_ns==stamp
    assert api().replay_retained(tmp_path/'advice.sqlite',json.loads(old)['report_id'])==json.loads(old)


def test_bad_policy_does_not_overwrite_last_good_report(tmp_path):
    tmp_path.chmod(0o700);api().publish_advice(snapshot=snapshot(),projections={},directory=tmp_path,now=NOW,guard=lambda:None)
    before=(tmp_path/'advice.json').read_bytes();p=tmp_path/'advice-policy.json';p.write_text('{"bad":1}');p.chmod(0o600)
    with pytest.raises(ValueError):api().publish_advice(snapshot=snapshot(),projections={},directory=tmp_path,now=NOW,guard=lambda:None)
    assert (tmp_path/'advice.json').read_bytes()==before
