from pathlib import Path
from hashlib import sha256
import pytest


def test_producer_selection_matches_actual_numerical_source_bytes(tmp_path):
    from calibrated_score_runtime import select_source_root
    old=tmp_path/'old';new=tmp_path/'new'
    for root,value in [(old,b'old numerical source'),(new,b'new numerical source')]:
        p=root/'openhab/scripts/household_calibrated_energy.py';p.parent.mkdir(parents=True,mode=0o700);root.chmod(0o700);p.write_bytes(value);p.chmod(0o400)
    forecast={'runtime_manifest':{'openhab/scripts/household_calibrated_energy.py':sha256(b'old numerical source').hexdigest()}}
    assert select_source_root(forecast,[new,old])==old
    (old/'openhab/scripts/household_calibrated_energy.py').chmod(0o600);(old/'openhab/scripts/household_calibrated_energy.py').write_bytes(b'changed')
    with pytest.raises(ValueError,match='producer'):select_source_root(forecast,[new,old])


def test_runner_refuses_an_import_bound_to_a_different_producer(tmp_path):
    from calibrated_score_runtime import require_producer_binding
    from household_calibrated_energy import replay
    actual=Path(replay.__globals__['__file__']).resolve().parents[2]
    require_producer_binding(replay,actual)
    with pytest.raises(ValueError,match='bound'):require_producer_binding(replay,tmp_path)


def test_different_policy_in_the_same_hour_is_sampled_separately():
    import json
    from household_calibrated_score import sample_key
    old=dict(inputs={'calibration_raw':json.dumps({'final_model':{'model_sha256':'a'*64}})},output={'issued_at':'2026-10-20T00:10:15+00:00'})
    new=dict(old,output=dict(old['output'],calibration_policy_sha256='b'*64))
    assert sample_key(old)!=sample_key(new)


def test_component_producer_source_selection_requires_new_receipt_kernel(tmp_path):
 from calibrated_score_runtime import select_source_root
 root=tmp_path/'new';path=root/'openhab/scripts/component_household_receipt.py';path.parent.mkdir(parents=True);root.chmod(0o700);path.write_bytes(b'component');path.chmod(0o400)
 from household.codec import identity
 forecast=dict(schema='earthship-household-calibrated-energy-receipt/v2',runtime_manifest={'openhab/scripts/component_household_receipt.py':sha256(b'component').hexdigest()},
  inputs={'context':{'adapter_source_sha256':identity({'openhab/scripts/component_household_receipt.py':sha256(b'component').hexdigest()})}})
 assert select_source_root(forecast,[root])==root
 path.chmod(0o600);path.write_bytes(b'changed')
 with pytest.raises(ValueError):select_source_root(forecast,[root])


def test_producer_registry_can_pin_different_interpreters_without_changing_old_default(tmp_path,monkeypatch):
 from calibrated_score_runtime import producer_interpreter
 import sys
 root=tmp_path/'new';root.mkdir();old=tmp_path/'old';old.mkdir()
 ref=dict(root=str(root),python_path=sys.executable,python_sha256=sha256(Path(sys.executable).resolve().read_bytes()).hexdigest())
 assert producer_interpreter(root,roots=[str(old),ref])==sys.executable
 assert producer_interpreter(old,roots=[str(old),ref])=='/usr/bin/python3'
 changed=dict(ref,python_sha256='f'*64)
 with pytest.raises(ValueError,match='interpreter'):producer_interpreter(root,roots=[changed])

def test_component_selector_uses_complete_adapter_source_identity(tmp_path):
 from calibrated_score_runtime import select_source_root
 from weather_learning.source_bundle import capture_sources
 from household.codec import identity
 old,new=tmp_path/'old',tmp_path/'new'
 for root,extra in [(old,b'old household reader'),(new,b'new household reader')]:
  root.mkdir(mode=0o700)
  for name,raw in [('component_household_receipt.py',b'same component kernel'),('household/thermal_model.py',extra)]:
   path=root/'openhab/scripts'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw);path.chmod(0o400)
 def adapter(root):return identity({n:sha256(b).hexdigest() for n,b in capture_sources(root).items()})
 forecast=dict(schema='earthship-household-calibrated-energy-receipt/v2',
  runtime_manifest={'openhab/scripts/component_household_receipt.py':sha256(b'same component kernel').hexdigest()},
  inputs={'context':{'adapter_source_sha256':adapter(old)}})
 assert select_source_root(forecast,[new,old])==old
 forecast['inputs']['context']['adapter_source_sha256']=adapter(new)
 assert select_source_root(forecast,[old,new])==new
 path=new/'openhab/scripts/household/thermal_model.py';path.chmod(0o600);path.write_bytes(b'changed household reader')
 with pytest.raises(ValueError,match='producer'):select_source_root(forecast,[old,new])

def test_component_selector_refuses_missing_adapter_identity(tmp_path):
 from calibrated_score_runtime import select_source_root
 forecast=dict(schema='earthship-household-calibrated-energy-receipt/v2',
  runtime_manifest={'openhab/scripts/component_household_receipt.py':'a'*64})
 with pytest.raises(ValueError,match='adapter identity'):select_source_root(forecast,[tmp_path])
