"""Existing thermal models consume frozen observed shade state in a retained sidecar."""
from datetime import timedelta
from pathlib import Path
import importlib,json
from test_household_models import prepared_thermal
from test_shade_position_observations import mapping,packet
from household.advice.shade_state import normalize_event,ShadeHistory
from household.codec import canonical
from household.control_contracts import instant


def observations(at,position=100.):
    result=[]
    for i in range(1,27):
        m=mapping();m.update(shade_id=f'shade-{i}',device_id=f'fixture-motor-{i}',zone='whole-house',valid_from=(at-timedelta(days=1)).isoformat())
        p=packet(position=position,device_id=m['device_id'],source=m['source'],observed_at=at.isoformat(),received_at=at.isoformat(),available_at=at.isoformat())
        result.append(normalize_event(m,p))
    return result


def test_original_thermal_framework_runs_both_coarse_and_observed_group_paths(tmp_path,monkeypatch):
    prepared,capture=prepared_thermal(tmp_path,monkeypatch);at=instant(prepared.to_dict()['issue']);before=prepared.content
    api=importlib.import_module('household.advice.thermal_evaluation')
    value=api.compare_original_model(prepared,observations(at),training_end=at-timedelta(days=1),now=instant(capture['published_at']))
    assert value['status']=='predicted_experimental'
    assert value['coarse_prediction_f']==capture['output']['trajectory'][0]['air_f']
    assert isinstance(value['position_prediction_f'],float)
    assert value['causal_benefit_qualified'] is False and prepared.content==before


def test_partial_positions_remain_observed_but_have_no_invented_linear_thermal_effect(tmp_path,monkeypatch):
    prepared,capture=prepared_thermal(tmp_path,monkeypatch);at=instant(prepared.to_dict()['issue'])
    api=importlib.import_module('household.advice.thermal_evaluation')
    value=api.compare_original_model(prepared,observations(at,50.),training_end=at-timedelta(days=1),now=instant(capture['published_at']))
    assert value['status']=='unsupported_position_effect' and value['position_prediction_f'] is None


def test_advice_cycle_retains_actual_original_model_comparison_even_with_no_operator_policy(tmp_path,monkeypatch):
    import household_advice
    from household.snapshot import HouseholdSnapshot
    prepared,capture=prepared_thermal(tmp_path,monkeypatch);body=prepared.to_dict();at=instant(body['issue']);directory=tmp_path/'private';directory.mkdir(mode=0o700)
    history=ShadeHistory(directory/'shade-observations.sqlite')
    for row in observations(at):history.ingest(row)
    original={k:v for k,v in body['snapshot'].items() if k!='snapshot_id'};snapshot=HouseholdSnapshot(canonical(original))
    context=dict(prepared=body,training_end=(at-timedelta(days=1)).isoformat(),concurrent_changes=[],source_ref=body['original_capture_sha256'])
    result=household_advice.publish_advice(snapshot=snapshot,projections={'thermal_evaluation_context':context},directory=directory,now=instant(capture['published_at']),guard=lambda:None)
    assert result['status']=='written'
    report=json.loads((directory/'shade-thermal-evaluation.json').read_text())
    assert report['latest_model_status']=='predicted_experimental' and report['pair_count']==0
    assert report['causal_benefit_qualified'] is False


def test_bound_episode_context_survives_later_report_window(tmp_path):
    from household.advice.lifecycle import AdviceHistory
    from household.advice.thermal_evaluation import orchestrate
    from test_household_advice_contract import run,snapshot,policy,state
    from test_shade_position_observations import event
    from local_measurement_test_support import NOW
    from household.codec import loads
    store=AdviceHistory(tmp_path/'advice.sqlite');history=ShadeHistory(tmp_path/'shades.sqlite')
    original=dict(snapshot=snapshot().to_dict(),projections={},policy=policy(),action_state=state(),now=NOW.isoformat())
    store.retain(run(),inputs=original,runtime={});history.ingest(event())
    moved=NOW+timedelta(seconds=2);history.ingest(event(seq=2,position=0.,observed_at=moved.isoformat(),received_at=moved.isoformat(),available_at=moved.isoformat()))
    orchestrate(store,history,original=original,now=moved,guard=lambda:None)
    with store._connect() as db:before=bytes(db.execute('SELECT raw FROM shade_episodes').fetchone()[0])
    for i in range(1,131):
        at=NOW+timedelta(seconds=i+3);report=run(now=at);store.retain(report,inputs={**original,'now':at.isoformat()},runtime={})
    orchestrate(store,history,original={**original,'now':(NOW+timedelta(seconds=200)).isoformat()},now=NOW+timedelta(seconds=200),guard=lambda:None)
    with store._connect() as db:after=bytes(db.execute('SELECT raw FROM shade_episodes').fetchone()[0])
    assert before==after and loads(after)['context']['initial_air_f']==60.
