"""Review regressions for storage semantics and complete replay source closure."""
from datetime import timedelta
from pathlib import Path
from hashlib import sha256
import pytest
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from test_household_energy_persistence import fixture,pipeline_fixture
from test_household_power_flows import declaration


@pytest.mark.parametrize('damage',['missing','sign','scale','unit'])
def test_storage_labels_require_the_original_positive_charging_metric(tmp_path,monkeypatch,damage):
    from household.power_flows import project_power_flows
    snap,metric,now=fixture(tmp_path,monkeypatch,watts=500);at=instant(snap.to_dict()['as_of'])
    if damage=='missing':metric=None
    else:
        body=loads(metric['raw']);row=body['sources'][0]
        row[{'sign':'sign','scale':'scale','unit':'canonical_unit'}[damage]]={'sign':'positive_discharging','scale':2.,'unit':'kW'}[damage]
        metric['raw']=canonical(body).decode();metric['sha256']=sha256(metric['raw'].encode()).hexdigest()
    out=project_power_flows(snapshot=snap,topology_source=declaration(at),metric_source=metric,now=now)
    assert out['household_load_w']==1000 and out['pv_controller_output_w']==1900
    assert all(out[k] is None for k in ('battery_net_dc_w','battery_charge_w','battery_discharge_w','storage_basis'))
    assert out['status']=='partial' and out['reasons']['battery_net_dc_w'] is not None


@pytest.mark.parametrize('damage',['hash','future'])
def test_supplied_metric_corruption_is_refused_not_reinterpreted(tmp_path,monkeypatch,damage):
    from household.power_flows import project_power_flows
    snap,metric,now=fixture(tmp_path,monkeypatch);at=instant(snap.to_dict()['as_of'])
    if damage=='hash':metric['sha256']='e'*64
    else:metric['available_at']=(at+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):project_power_flows(snapshot=snap,topology_source=declaration(at),metric_source=metric,now=now)


def test_changed_plan_verifier_source_is_detected_by_flow_replay(tmp_path,monkeypatch):
    import household_power_flows as flows,household_outcomes as outcomes
    _,plan,_,_=pipeline_fixture(tmp_path,monkeypatch);at=instant(plan['inputs']['snapshot']['as_of'])
    runtime=flows.flow_runtime_manifest();flow=flows.seal_flow_receipt(plan_receipt=plan,topology_source=declaration(at),now=instant(plan['inputs']['now']),runtime_manifest=runtime)
    read=outcomes._read
    def changed(path,*a,**kw):
        raw=read(path,*a,**kw)
        return raw+b'\n# changed verifier\n' if Path(path).name=='household_outcomes.py' else raw
    monkeypatch.setattr(outcomes,'_read',changed)
    with pytest.raises(ValueError):flows.replay_flow_receipt(flow,plan_receipt=plan,runtime_manifest=flows.flow_runtime_manifest())


def test_resealed_runtime_cannot_omit_the_executing_plan_verifier(tmp_path,monkeypatch):
    import household_power_flows as flows
    _,plan,_,_=pipeline_fixture(tmp_path,monkeypatch);at=instant(plan['inputs']['snapshot']['as_of']);runtime=flows.flow_runtime_manifest()
    flow=flows.seal_flow_receipt(plan_receipt=plan,topology_source=declaration(at),now=instant(plan['inputs']['now']),runtime_manifest=runtime)
    runtime.pop('openhab/scripts/household_outcomes.py',None);flow['runtime_manifest']=runtime
    flow['receipt_sha256']=identity({k:v for k,v in flow.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):flows.replay_flow_receipt(flow,plan_receipt=plan,runtime_manifest=runtime)


def test_deeply_nested_optional_topology_preserves_other_household_sources(tmp_path,monkeypatch):
    from test_household_cycle_sources import collector_fixture
    raw='{"unexpected":'+'['*1200+'0'+']'*1200+'}'
    # Python 3.12's C decoder accepts this bounded nesting while older
    # decoders can overflow. Inject that decoder failure at its real boundary
    # and exercise the complete collector, including its other source domains.
    from household import power_flows
    decode=power_flows.loads
    def overflow(text):
        if text==raw:raise RecursionError('optional topology decoder overflow')
        return decode(text)
    monkeypatch.setattr(power_flows,'loads',overflow)
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch,load_topology_raw=raw)
    result=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    assert result['load_topology_source'] is None
    assert result['power_receipt']['snapshot']['domains']['energy']['inverter_output_w']['value']==1000
    assert result['energy_configuration'] is not None
