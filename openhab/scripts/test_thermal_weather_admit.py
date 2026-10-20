from copy import deepcopy
from datetime import timedelta
import pytest
from test_weather_site_calibration import rows,T
from weather_learning.site_calibration import fit_residual
from weather_learning.contracts import identity


def test_cold_validation_reproduces_original_model_without_renewing_clock():
    from thermal_weather_admit import reproduce
    pairs=rows();original=fit_residual(pairs,kind='outdoor_temperature_c',cutoff=T+timedelta(days=8),trained_at=T+timedelta(days=20),correction_limit=6.)
    before=deepcopy(original)
    assert reproduce(original,pairs)==original['model_sha256']
    assert original==before
    changed=deepcopy(original);changed['intercept']+=.1;changed['model_sha256']=identity({k:v for k,v in changed.items() if k!='model_sha256'})
    with pytest.raises(ValueError,match='reproduce'):reproduce(changed,pairs)
