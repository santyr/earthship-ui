"""Review regressions: optional map failure must not invent an unshaded sky."""
from datetime import timedelta
import pytest
from household.control_contracts import instant
from household.codec import canonical
from test_household_native_weather import made,originals
from test_household_pv_model import source as system_source
from test_household_solar_horizon import source as horizon_source


def test_malformed_map_capture_withholds_PV_storage_but_keeps_flows_and_plan(tmp_path,monkeypatch,originals):
    from test_household_cycle_sources import collector_fixture
    from test_household_energy_forecast import fixture
    from local_measurement_test_support import NOW
    import household_energy_forecast as api
    collector,_,_,_,now=collector_fixture(tmp_path,monkeypatch,pv_system_raw=system_source(NOW)['raw'],solar_horizon_raw='{')
    collected=collector(issue=now+timedelta(seconds=8),remaining=lambda:6.,guard=lambda:None)
    _,args,plan=fixture(tmp_path,monkeypatch,originals);before=canonical(plan)
    # This is precisely the unusable optional source the real collector emits.
    args['horizon_source']=collected['solar_horizon_source']
    out=api.seal_energy_forecast(**args)['output']
    assert out['array_pv']['status']=='unavailable'
    assert out['array_pv']['reason']=='solar_horizon_unavailable'
    assert out['nominal_storage']['status']=='unavailable'
    assert out['current_flows']['household_load_w']==1000
    assert canonical(plan)==before


@pytest.mark.parametrize('damage',['bytes','future'])
def test_horizon_wrapper_corruption_refuses_even_without_native_geometry(tmp_path,monkeypatch,damage):
    from test_household_cycle import derived_fixture
    import household_pv_model as pv
    args,capture=derived_fixture(tmp_path,monkeypatch);issue=instant(capture['issued_at']);horizon=horizon_source(issue)
    if damage=='bytes':horizon['raw']+=' '
    else:horizon['available_at']=(issue+timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):pv.project_pv(weather=args['weather'],system_source=system_source(issue),horizon_source=horizon,now=args['now'])
