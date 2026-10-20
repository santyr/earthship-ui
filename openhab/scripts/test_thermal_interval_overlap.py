"""Ending-hour irradiation conservation at real permitted issue seconds."""
from datetime import datetime,timedelta,timezone
from copy import deepcopy
import pytest
from google_weather_fixtures import forecast
from thermal_model.installed_shade_origin import _forecast_forcing
from test_native_thermal_artifact import originals

ACTIONS=dict(indoor_shade_closed=0.,outdoor_shade_present=1.,vent_open=0.)

@pytest.mark.parametrize('seconds',[0,15])
@pytest.mark.parametrize('initial,gradient,current,next_value,crossing',[
    (-700.,800.,100.,900.,140.),
    (1500.,-700.,800.,100.,765.),
    (100.,0.,100.,100.,100.),
    (-800.,800.,0.,800.,40.),
    (800.,-400.,400.,0.,380.),
])
def test_native_trailing_hour_means_conserve_each_step_and_entire_horizon(seconds,initial,gradient,current,next_value,crossing):
    issue=datetime(2026,10,20,12,55,seconds,tzinfo=timezone.utc)
    source=forecast(issue,1,radiation_wm2=initial,radiation_step_wm2=gradient)
    original=deepcopy(source)
    values=_forecast_forcing(source,issue,issue,ACTIONS)
    assert values[0].radiation_wm2==pytest.approx(current if seconds==0 else crossing)
    assert [v.radiation_wm2 for v in values[1:]]==[next_value]*11
    # Only the first 300 or 285 seconds precede 13:00; the remainder belongs
    # to the next ending-hour source. This expectation does not call a helper.
    prior_seconds=300-seconds
    expected=current*prior_seconds+next_value*(3600-prior_seconds)
    assert sum(v.radiation_wm2*300 for v in values)==pytest.approx(expected)
    assert source==original
    assert all((v.indoor_shade_closed,v.outdoor_shade_present,v.vent_open)==(0.,1.,0.) for v in values)


def test_conditioned_crossing_conserves_raw_and_corrected_sources(tmp_path,monkeypatch,originals):
    import test_thermal_weather_conditioning as fixture
    import native_thermal_forecast as native
    import native_thermal_artifact
    from test_native_thermal_forecast import context
    from thermal_weather_source import collect_context
    from household.thermal_weather_conditioning import apply_conditioning
    from household.weather_context import prepare_native_cycle_contexts,project_weather
    from household.thermal_model import project
    issue=fixture.ISSUE.replace(hour=12,minute=55,second=15)
    candidate,inputs,kwargs=context(tmp_path,monkeypatch,originals,issue=issue)
    # A finite changing source is built at original source level. Use a
    # one-hour horizon for the sharp 100->900 crossing fixture.
    inputs['forecast']=forecast(issue,1,radiation_wm2=-700.,radiation_step_wm2=800.)
    from test_native_thermal_forecast import future
    kwargs['geometry']=future(issue,hours=1);kwargs['expected_geometry_sha256']=kwargs['geometry'].sha256
    monkeypatch.setattr(fixture,'ISSUE',issue)
    args,_=fixture.bound_fixture(tmp_path/'weather',monkeypatch,forecast=inputs['forecast'],geometry=kwargs['geometry'],sensor_epoch=candidate['fit']['sensor_epochs']['outdoor'])
    proof=collect_context(**args)
    raw=_forecast_forcing(inputs['forecast'],issue,issue,ACTIONS)
    corrected=apply_conditioning(raw,proof,issue=issue,available=issue,initial_outdoor_f=53.6)
    assert raw[0].radiation_wm2==140.
    assert corrected[0].radiation_wm2==40.
    assert sum(r.radiation_wm2*300 for r in corrected)==pytest.approx(800.*3315)
    before=deepcopy(inputs)
    capture=native.build_capture(candidate,inputs,weather_conditioning=proof,**kwargs)
    assert native.validate_capture(capture,runtime=kwargs['runtime'],expected_artifact_sha256=candidate['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])==capture
    monkeypatch.setattr(native_thermal_artifact,'current_native_runtime',lambda **kw:deepcopy(kwargs['runtime']))
    thermal,weather=prepare_native_cycle_contexts(capture,code_revision='a'*40,runtime=kwargs['runtime'],expected_artifact_sha256=candidate['artifact_sha256'],expected_capture_sha256=capture['capture_sha256'])
    assert project(thermal)['output']==capture['output']
    assert project_weather(weather)['forcings']==thermal.to_dict()['forcings']
    assert inputs==before and capture['output']['automatic_actuation'] is False
