from datetime import timedelta
import pytest
from test_household_pv_window import START
from test_weather_directional_pv import rows
from weather_learning.pv_directional_calibration import fit_directional


@pytest.mark.parametrize('lead,elevation,horizon,expected',[(1,25.,20.,False),(1,25.01,20.,True),(48,30.,20.,True),(336,30.,20.,True),(336.01,30.,20.,False),(2,-1.,0.,False)])
def test_policy_uses_supported_leads_and_retains_raw_near_horizon(lead,elevation,horizon,expected):
    from weather_learning.pv_calibration_policy import project_power
    origin=START+timedelta(days=20);model=fit_directional(rows(),cutoff=START+timedelta(days=8),trained_at=origin)
    watts,applied=project_power(model,1000.,azimuth_degrees=110.,elevation_degrees=elevation,horizon_elevation_degrees=horizon,origin=origin,target=origin+timedelta(hours=lead))
    assert applied is expected
    assert (watts<1000.) is expected
    if not expected:assert watts==1000.


def test_policy_rejects_future_model_and_invalid_geometry():
    from weather_learning.pv_calibration_policy import project_power
    origin=START+timedelta(days=20);model=fit_directional(rows(),cutoff=START+timedelta(days=8),trained_at=origin+timedelta(seconds=1))
    kw=dict(azimuth_degrees=110.,elevation_degrees=30.,horizon_elevation_degrees=20.,origin=origin,target=origin+timedelta(hours=1))
    with pytest.raises(ValueError,match='origin'):project_power(model,1000.,**kw)
    kw['origin']+=timedelta(seconds=1);kw['elevation_degrees']=float('nan')
    with pytest.raises(ValueError,match='geometry'):project_power(model,1000.,**kw)
