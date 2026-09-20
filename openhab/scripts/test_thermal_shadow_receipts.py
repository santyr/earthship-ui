from datetime import timedelta
from types import SimpleNamespace
import math
import subprocess

import pytest

from test_thermal_temperature_history import receipt, env
from test_weather_temperature_reader import AT
from thermal_temperature_runtime import (shadow_temperatures,
    configured_shadow_temperatures, validate_shadow_receipt_expiry)
from thermal_model.schema import THERMAL_ITEMS


@pytest.mark.parametrize('offset',[0,61])
def test_shadow_uses_bounded_receipt_only_history_and_actual_received_time(offset):
    now=AT+timedelta(seconds=offset); calls=[]
    def grid(stream,targets,assessed):
        calls.append((targets,assessed))
        return [(at,receipt(at)) for at in targets]
    result=shadow_temperatures(now,grid)
    assert set(result)=={'air','mass','outdoor'}
    for targets,assessed in calls:
        assert len(targets)<=289 and targets[-1]==assessed==now
        assert targets[-1]-targets[0]<=timedelta(days=1)
    for reading in result.values():
        assert reading['current']['at']==now-timedelta(seconds=30)
        assert reading['current']['validUntil']==now+timedelta(seconds=90)
        assert all(at<now for at,_ in reading['history'])


def test_missing_history_stays_invalid_but_current_receipt_can_recover():
    result=shadow_temperatures(AT,lambda stream,targets,assessed:
        [(at,receipt(at) if at==AT else None) for at in targets])
    assert all(math.isnan(value) for at,value in result['air']['history'])
    assert result['air']['current']['value']==70


def test_missing_current_never_uses_older_qualified_history():
    with pytest.raises(ValueError,match='unqualified current air'):
        shadow_temperatures(AT,lambda stream,targets,assessed:
            [(at,None if at==AT else receipt(at)) for at in targets])


def test_expiry_is_exact_and_legacy_readings_are_not_reclassified():
    current={'air':{'at':AT,'validUntil':AT+timedelta(seconds=120)}}
    validate_shadow_receipt_expiry(current,AT+timedelta(seconds=119))
    with pytest.raises(ValueError,match='expired current air'):
        validate_shadow_receipt_expiry(current,AT+timedelta(seconds=120))
    validate_shadow_receipt_expiry({'air':{'at':AT,'value':70}},AT+timedelta(days=1))


def test_pipeline_itself_rejects_expired_receipt_despite_recent_timestamp():
    from thermal_model.pipeline import _reading
    with pytest.raises(ValueError,match='expired .*receipt'):
        _reading({'at':AT-timedelta(seconds=30),'value':70,'validUntil':AT},'air',AT)


def test_shadow_activation_is_independent_and_worker_errors_are_unavailable(monkeypatch):
    import thermal_temperature_runtime as runtime
    assert configured_shadow_temperatures(AT,environ=env()) is None
    active={**env(),'THERMAL_TEMP_SHADOW_QUALIFIED_ENABLE':'1'}
    def failed(*args,**kwargs):raise subprocess.TimeoutExpired('worker',30)
    monkeypatch.setattr(runtime.subprocess,'run',failed)
    with pytest.raises(ValueError,match='^qualified shadow temperature evidence unavailable$'):
        configured_shadow_temperatures(AT,environ=active)


def test_current_states_do_not_read_numeric_temperature_or_rest_update_times(monkeypatch):
    import thermal_intel
    import thermal_temperature_runtime as runtime
    qualified=shadow_temperatures(AT,lambda stream,targets,assessed:[(at,receipt(at)) for at in targets])
    monkeypatch.setattr(runtime,'configured_shadow_temperatures',lambda now:qualified)
    protected={THERMAL_ITEMS[role] for role in qualified}
    def history(item,start,end):
        assert item not in protected
        return [(AT,100 if item==THERMAL_ITEMS['radiation'] else 70)]
    def state(item):
        assert item not in protected
        return dict(name=item,state='70',lastStateUpdate=AT.timestamp()*1000)
    current=thermal_intel._current_states(AT,series_reader=history,state_reader=state)
    assert current['air']['at']==AT-timedelta(seconds=30)
    assert current['mass']['validUntil']==AT+timedelta(seconds=90)


def test_expiry_during_shadow_computation_prevents_publication(monkeypatch,tmp_path):
    import thermal_intel
    from test_thermal_pipeline import current_states, NOW
    current=current_states(); current['air']['validUntil']=NOW+timedelta(seconds=1)
    ticks=iter([0,2])
    monkeypatch.setattr(thermal_intel.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(thermal_intel.forecast_intel,'load_site_settings',lambda:None)
    monkeypatch.setattr(thermal_intel,'_current_states',lambda now:current)
    monkeypatch.setattr(thermal_intel.forecast_intel,'fetch_forecast',lambda:{})
    monkeypatch.setattr(thermal_intel,'_forecast_rows',lambda *args:[{'mode':'warm'}])
    monkeypatch.setattr(thermal_intel,'run_shadow',lambda **kwargs:{'confidence':{'grade':'high'}})
    monkeypatch.setattr(thermal_intel,'ArtifactRegistry',lambda *args:None)
    publications=[]
    result=thermal_intel._shadow(SimpleNamespace(output=tmp_path/'shadow.json',publish=True),NOW,
                                put_state=lambda *args:publications.append(args))
    assert result==1 and publications==[]
    assert 'expired current air' in (tmp_path/'shadow.json').read_text()
