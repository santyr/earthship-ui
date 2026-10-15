"""A flow receipt pins its original plan, operator declaration and executing source."""
import importlib
from datetime import timedelta
from copy import deepcopy
from pathlib import Path
import pytest
from household.codec import canonical,loads,identity
from household.control_contracts import instant
from test_household_energy_persistence import pipeline_fixture
from test_household_power_flows import declaration


def api():return importlib.import_module('household_power_flows')


def test_flow_sidecar_replays_original_consumption_and_preserves_plan_bytes(tmp_path,monkeypatch,capsys):
    _,plan,_,_=pipeline_fixture(tmp_path,monkeypatch);before=canonical(plan);at=instant(plan['inputs']['snapshot']['as_of'])
    module=api();runtime=module.flow_runtime_manifest();source=declaration(at);now=instant(plan['inputs']['now'])
    flow=module.seal_flow_receipt(plan_receipt=plan,topology_source=source,now=now,runtime_manifest=runtime)
    assert flow['output']['household_load_w']==1000 and flow['output']['battery_discharge_w']==500
    assert flow['inputs']['plan_receipt_sha256']==plan['receipt_sha256'] and canonical(plan)==before
    assert module.replay_flow_receipt(flow,plan_receipt=plan,runtime_manifest=runtime)==flow
    pp=tmp_path/'plan.json';pp.write_bytes(before);pp.chmod(0o600)
    fp=tmp_path/'flows.json';fp.write_bytes(canonical(flow));fp.chmod(0o600)
    assert module.main(['--receipt',str(fp),'--plan',str(pp)])==0
    assert loads(capsys.readouterr().out)==flow


@pytest.mark.parametrize('damage',['plan','output','topology','runtime','missing_model_source'])
def test_resealed_sidecar_cannot_substitute_plan_or_model_output(tmp_path,monkeypatch,damage):
    _,plan,_,_=pipeline_fixture(tmp_path,monkeypatch);at=instant(plan['inputs']['snapshot']['as_of']);module=api();runtime=module.flow_runtime_manifest()
    flow=module.seal_flow_receipt(plan_receipt=plan,topology_source=declaration(at),now=instant(plan['inputs']['now']),runtime_manifest=runtime)
    if damage=='plan':flow['inputs']['plan_receipt_sha256']='a'*64
    elif damage=='output':flow['output']['household_load_w']=1500;flow['output']['projection_sha256']=identity({k:v for k,v in flow['output'].items() if k!='projection_sha256'})
    elif damage=='topology':flow['inputs']['topology_source']['raw']+=' '
    elif damage=='runtime':runtime['openhab/scripts/household/power_flows.py']='b'*64
    else:flow['runtime_manifest'].pop('openhab/scripts/household/power_flows.py');runtime.pop('openhab/scripts/household/power_flows.py')
    flow['receipt_sha256']=identity({k:v for k,v in flow.items() if k!='receipt_sha256'})
    with pytest.raises(ValueError):module.replay_flow_receipt(flow,plan_receipt=plan,runtime_manifest=runtime)
