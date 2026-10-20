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
