from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import pytest
from test_weather_directional_pv import rows
from test_household_pv_window import START
from weather_learning.contracts import identity,canonical


def source(tmp_path):
 from weather_learning.pv_directional_calibration import fit_directional
 from weather_learning.pv_calibration_source import load_calibration
 now=START+timedelta(days=20);model=fit_directional(rows(),cutoff=START+timedelta(days=12),trained_at=now)
 core=Path(__file__).parent/'weather_learning/pv_directional_calibration.py'
 runtime={str(p.relative_to(Path(__file__).parents[2])):sha256(p.read_bytes()).hexdigest() for p in (core,core.with_name('pv_calibration.py'),core.with_name('contracts.py'),core.with_name('weights.py'))}
 report=dict(selected=True,model_sha256='a'*64,holdout_end=(START+timedelta(days=12)).isoformat(),independent_target_days=5,baseline_mae_w=10.,candidate_mae_w=8.,prospective_score=False,physical_calibration_qualified=False,automatic_actuation=False)
 report['report_sha256']=identity(report)
 value=dict(schema='earthship-historical-pv-directional-experiment/v1',created_at=now.isoformat(),final_model=model,training_model_sha256='a'*64,report=report,runtime_manifest=runtime,system_raw='{}',horizon_raw='{}',automatic_actuation=False)
 value['receipt_sha256']=identity(value);path=tmp_path/'model.json';path.write_bytes(canonical(value));path.chmod(0o600)
 return load_calibration,path,now


def test_calibration_source_is_bound_to_actual_availability_runtime_and_geometry(tmp_path):
 load,path,now=source(tmp_path)
 result=load(path,origin=now,system_raw=b'{}',horizon_raw=b'{}')
 assert result['model']['physical_calibration_qualified'] is False
 with pytest.raises(ValueError):load(path,origin=now-timedelta(seconds=1),system_raw=b'{}',horizon_raw=b'{}')
 with pytest.raises(ValueError):load(path,origin=now,system_raw=b'{"new":1}',horizon_raw=b'{}')
 with pytest.raises(ValueError):load(path,origin=now+timedelta(days=15),system_raw=b'{}',horizon_raw=b'{}')
