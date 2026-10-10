"""Native original inputs retain real endpoints across interior sensor gaps."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import json
import pytest
from thermal_model.schema import THERMAL_ITEMS,ActionEvent,ModeEvent
from thermal_model.temperature_history import QualifiedTemperatureHistoryV2,STREAMS,POLICY
from weather_temperature_evidence import TemperaturePolicy,MODELS
from weather_temperature_receiver import TemperatureCollector
from weather_temperature_reader import select_temperature_grid_v2
from test_thermal_sensor_epoch_history import EPOCHS
from thermal_model.training_inputs import capture_training_inputs_v2

START=datetime(2026,9,24,18,tzinfo=timezone.utc)
END=START+timedelta(minutes=70)


def snapshot(*,missing=None,future_indoor=False,future_action=None,initial_outdoor="installed",radiation_gap=False,transient_action=None,steps=14,late_indoor=False,rich_actions=False,mode_delay_hours=0):
    end=START+timedelta(minutes=5*steps)
    policies={stream:TemperaturePolicy(model,sensor,**POLICY) for stream,model,sensor in STREAMS.values()}
    phases={STREAMS[role][0]:phase for role,phase in EPOCHS.items()}
    clock={'at':START,'tick':1000,'pid':1}
    source=TemperatureCollector(policies,sensor_epochs=phases,clock=lambda:clock['at'],monotonic=lambda:clock['tick'],process_id=lambda:clock['pid'])
    raw=[]
    for index in range(steps):
        clock.update(at=START+timedelta(minutes=5*index),tick=1000+300*index,pid=1 if index<8 else 2)
        for role,(stream,model,sensor) in STREAMS.items():
            if missing==role and index==6:continue
            value={'air':70+index*.01,'mass':69+index*.005,'outdoor':55}[role]
            source.observe({'model':model,'id':str(sensor),MODELS[model][1]:str(value)})
        raw.append((clock['at'],json.dumps(source.snapshot())))
    def grid(stream,targets,assessed):
        role=next(role for role,identity in STREAMS.items() if identity[0]==stream)
        return select_temperature_grid_v2([row for row in raw if row[0]<=targets[-1]],targets=targets,assessed_at=assessed,history_start=targets[0]-timedelta(seconds=120),stream=stream,policy=policies[stream],sensor_epoch=EPOCHS[role])
    def legacy(item,start,end):
        assert item==THERMAL_ITEMS['radiation'] or item not in {THERMAL_ITEMS[role] for role in STREAMS}
        return [(START+timedelta(minutes=5*i),None if missing=='radiation' and i==6 else 200) for i in range(steps) if not (radiation_gap and i==6)] if item==THERMAL_ITEMS['radiation'] else []
    events=[ActionEvent('outdoor','receipt',START,START,'outdoor_shade',initial_outdoor,'manual_dm',1),ActionEvent('indoor','receipt',START,START,'indoor_shade','open','manual_dm',1),ActionEvent('vent','receipt',START,START,'vent','closed','manual_dm',1)]
    if future_indoor:events.append(ActionEvent('later','receipt',START+timedelta(minutes=20),START+timedelta(minutes=20),'indoor_shade','closed','manual_dm',1))
    if future_action is not None:
        action,state=future_action
        events.append(ActionEvent('domain','receipt',START+timedelta(minutes=30),START+timedelta(minutes=30),action,state,'manual_dm',1))
    if transient_action is not None:
        action,bad,good=transient_action
        for minute,state in ((12,bad),(14,good)):
            events.append(ActionEvent(f'transient-{minute}','receipt',START+timedelta(minutes=minute),START+timedelta(minutes=minute),action,state,'model_inferred',.5))
    if late_indoor:
        events.append(ActionEvent('retroactive','receipt',START+timedelta(minutes=20),START,'indoor_shade','closed','manual_dm',1))
    if rich_actions:
        for hour,action,state in ((12,'indoor_shade','closed'),(12,'vent','open'),(36,'vent','closed'),(60,'indoor_shade','open')):
            at=START+timedelta(hours=hour)
            if at<end:events.append(ActionEvent(f'rich-{hour}-{action}','receipt',at,at,action,state,'manual_dm',1))
    mode_at=START+timedelta(hours=mode_delay_hours)
    modes=[ModeEvent('mode','receipt',mode_at,mode_at,'warm','manual_dm',1)]
    reader=QualifiedTemperatureHistoryV2(legacy,grid,cutover=START,assessed_at=end,sensor_epochs=EPOCHS,retain_raw=True)
    journal=SimpleNamespace(effective_events=lambda *_:events,effective_modes=lambda *_:modes)
    return capture_training_inputs_v2(start=START,end=end,series_reader=reader,journal=journal,clock=lambda:end,revision_reader=lambda:'a'*64)


def build(record):
    from thermal_model.installed_shade_inputs import build_development_inputs
    return build_development_inputs(record,expected_snapshot_sha256=record['snapshot_sha256'],sensor_epochs=EPOCHS,assessed_at=END)


def select(data):
    from thermal_model.installed_shade_inputs import select_development_endpoints
    return select_development_endpoints(data,horizon_hours=1,start=START,end=END)


def test_missing_interior_air_is_not_fabricated_but_original_forcing_still_supports_endpoint():
    record=snapshot(missing='air');before=deepcopy(record);data=build(record);points=select(data)
    assert len(points)==1 and len(points[0].forcings)==12
    assert START+timedelta(minutes=30) not in {row.at for row in data.samples}
    assert points[0].origin.at==START and points[0].target.at==START+timedelta(hours=1)
    assert points[0].source_snapshot_sha256==record['snapshot_sha256']
    assert data.sensor_epochs==tuple(sorted(EPOCHS.items())) and record==before
    assert data.release_authorized is False and data.as_issued_forecast is False


@pytest.mark.parametrize('missing',['outdoor','radiation'])
def test_original_forcing_barrier_prevents_endpoint(missing):
    assert select(build(snapshot(missing=missing)))==()


def test_origin_actions_are_frozen_in_predictions_even_when_later_journal_changes():
    data=build(snapshot(future_indoor=True));point=select(data)[0]
    assert point.origin.indoor_shade_closed==0
    assert all(row.indoor_shade_closed==0 and row.vent_open==0 and row.outdoor_shade_present==1 for row in point.forcings)
    assert any(row.indoor_shade_closed==1 for row in data.samples if row.at>START)


@pytest.mark.parametrize('damage',['snapshot','phase','future','legacy'])
def test_pinned_source_or_native_phase_mismatch_is_refused(damage):
    from thermal_model.installed_shade_inputs import build_development_inputs
    record=snapshot();pin=record['snapshot_sha256'];phases=dict(EPOCHS);assessed=END
    if damage=='snapshot':pin='b'*64
    elif damage=='phase':phases['air']=EPOCHS['mass']
    elif damage=='future':assessed=START
    else:record['schema']='earthship-thermal-training-inputs/v1'
    with pytest.raises(ValueError):build_development_inputs(record,expected_snapshot_sha256=pin,sensor_epochs=phases,assessed_at=assessed)


def test_native_session_resets_preserve_hardware_phase_and_source_links():
    record=snapshot();data=build(record)
    assert len({row.stream_epoch for row in data.weather})==2
    assert {row.sensor_epoch for row in data.weather}=={EPOCHS['outdoor']}
    assert all(len(row.outdoor_snapshot_sha256)==64 for row in data.weather)


def test_input_is_immutable_and_selection_interval_is_bounded():
    from thermal_model.installed_shade_inputs import select_development_endpoints
    data=build(snapshot())
    with pytest.raises((AttributeError,TypeError)):data.samples=()
    with pytest.raises(ValueError):select_development_endpoints(data,horizon_hours=True,start=START,end=END)
    with pytest.raises(ValueError):select_development_endpoints(data,horizon_hours=1,start=START-timedelta(minutes=5),end=END)


def test_missing_mass_remains_absent_without_breaking_original_weather_prefix():
    data=build(snapshot(missing='mass'))
    assert START+timedelta(minutes=30) not in {row.at for row in data.samples}
    assert len(select(data))==1


@pytest.mark.parametrize('action,state',[('outdoor_shade','removed'),('outdoor_shade','unknown'),('kiva','on'),('kiva','exceptional_heat_unknown')])
def test_future_domain_or_heat_change_excludes_entire_endpoint(action,state):
    assert select(build(snapshot(future_action=(action,state))))==()


def test_removed_shade_origin_cannot_enter_installed_domain():
    assert select(build(snapshot(initial_outdoor='removed')))==()


def test_interpolated_daylight_radiation_is_not_original_qualified_forcing():
    data=build(snapshot(radiation_gap=True))
    assert START+timedelta(minutes=30) not in {row.at for row in data.weather}
    assert select(data)==()


@pytest.mark.parametrize('action,bad,good',[('outdoor_shade','removed','installed'),('kiva','on','off')])
def test_transient_off_grid_domain_or_heat_event_cannot_disappear(action,bad,good):
    data=build(snapshot(transient_action=(action,bad,good)))
    # Every five-minute target appears safe; original sub-step events still
    # invalidate the entire conditional forecast window.
    assert all(row.outdoor_shade_present==1 and row.passive_fit_allowed for row in data.weather)
    assert select(data)==()



def test_retroactive_action_received_after_origin_cannot_supply_known_origin_state():
    data=build(snapshot(late_indoor=True))
    assert data.samples[0].indoor_shade_closed==1
    # Retrospective labeling is retained for diagnostics, never mistaken for
    # information actually available at the forecast origin.
    assert select(data)==()
