"""Stage A must simulate the baseline it presents, without schedule optimization."""
from copy import deepcopy
from datetime import datetime,timedelta
from types import SimpleNamespace
import json
import pytest

from thermal_model import pipeline,release
from test_thermal_pipeline import AcceptedRegistry,current_states,forecast_hours,NOW
from test_thermal_release import inputs


def selected_shade_schedule(*,behavior,dynamics,forecast):
    baseline=pipeline.baseline_schedule(behavior,forecast)
    closed=forecast[0]['at']+timedelta(minutes=5)
    opened=forecast[0]['at']+timedelta(hours=14)
    candidate={**deepcopy(baseline),'shadeCloseAt':closed,'shadeOpenAt':opened,
        'shadeTransitions':(
            dict(at=closed,state='closed',source='fixture',status='modeled'),
            dict(at=opened,state='open',source='fixture',status='modeled'))}
    candidate['ventOpenAt']=baseline['ventOpenAt']+timedelta(minutes=5)
    candidate['airflowSegments']=tuple({**segment,'startAt':candidate['ventOpenAt']} if segment['level']=='baseline' and segment['startAt']==baseline['ventOpenAt'] else segment for segment in baseline['airflowSegments'])
    return SimpleNamespace(baseline=baseline,candidate=candidate,
        modeled_difference=dict(selectionReason='bounded_candidate_improved',scoreImprovement=1.0))


@pytest.mark.parametrize("hours",[24,72])
def test_forecast_only_simulates_real_baseline_despite_material_candidate(monkeypatch,hours):
    context=dict(registry=AcceptedRegistry(),current=current_states(),forecast=forecast_hours(hours),now=NOW)
    def baseline_search(**kwargs):
        return SimpleNamespace(candidate=None,modeled_difference=dict(selectionReason='minimum_improvement_not_met',scoreImprovement=0.0))
    monkeypatch.setattr(pipeline,'search_candidate_schedule',baseline_search)
    expected=pipeline.run_shadow(**context)
    assert expected['status']=='shadow' and expected['schedule']['candidate'] is None
    monkeypatch.setattr(pipeline,'search_candidate_schedule',selected_shade_schedule)
    selected=pipeline.run_shadow(**context)
    assert selected['schedule']['candidate'] is not None,selected['reasons']
    assert max(abs(a['hallwayF']-b['hallwayF']) for a,b in zip(expected['forecast']['trajectory'],selected['forecast']['trajectory']))>.1
    def prohibited(**kwargs):pytest.fail('forecast-only path reached candidate search')
    monkeypatch.setattr(pipeline,'search_candidate_schedule',prohibited)
    result=pipeline.run_shadow(**context,optimize_schedule=False)
    assert result['forecast']==expected['forecast']
    assert result['schedule']==expected['schedule']
    assert result['confidence']['grade']=='low'


def test_stage_a_refuses_candidate_conditioned_shadow_instead_of_hiding_it(monkeypatch):
    data=inputs(monkeypatch);shadow=data['shadow']
    assert release.build_release_output(**data)['status']=='forecast_active'
    candidate=deepcopy(shadow['schedule']['baseline'])
    candidate['ventCloseAt']=(datetime.fromisoformat(candidate['ventCloseAt'])-timedelta(minutes=5)).isoformat()
    shadow['schedule']['candidate']=candidate
    shadow['schedule']['effect']['morningMassDeltaF']=1.0
    original=deepcopy(shadow)
    result=release.build_release_output(**data)
    assert result['status']=='unavailable'
    assert result['forecast']['trajectory']==[]
    assert shadow==original


def test_release_command_requests_baseline_simulation(tmp_path,monkeypatch):
    from test_thermal_release_runtime import release_case
    from test_thermal_origin_capture import capture_inputs
    thermal,args,data,now=release_case(tmp_path,monkeypatch)
    def predict(**kwargs):
        assert kwargs.get('optimize_schedule') is False
        kwargs['artifact_observer'](capture_inputs()['artifact'])
        return deepcopy(data['shadow'])
    monkeypatch.setattr(thermal,'run_shadow',predict)
    sent=[]
    assert thermal._release(args,now,put_state=lambda item,raw:sent.append(json.loads(raw)),decision_clock=lambda:now,qualification_clock=lambda:now)==0
    assert len(sent)==1 and sent[0]['status']=='forecast_active'


@pytest.mark.parametrize('selection',[None,0,1,'false'])
def test_schedule_selection_requires_explicit_boolean_before_artifact_read(selection):
    class UnreadableRegistry:
        def load_accepted(self):pytest.fail('invalid schedule selection reached artifact authority')
    result=pipeline.run_shadow(registry=UnreadableRegistry(),current={},forecast=[],now=NOW,optimize_schedule=selection)
    assert result['confidence']['grade']=='unavailable'
    assert result['forecast']['trajectory']==[]


def test_forecast_only_retains_existing_winter_baseline_without_search(monkeypatch):
    forecast=[{**row,'mode':'winter','tempF':25.0,'radiationWm2':25.0} for row in forecast_hours(24)]
    def prohibited(**kwargs):pytest.fail('forecast-only winter path reached candidate search')
    monkeypatch.setattr(pipeline,'search_candidate_schedule',prohibited)
    result=pipeline.run_shadow(registry=AcceptedRegistry(),current=current_states(),forecast=forecast,now=NOW,optimize_schedule=False)
    assert result['confidence']['grade']=='low'
    assert result['schedule']['baseline']==dict(ventOpenAt=None,ventCloseAt=None)
    assert result['schedule']['candidate'] is None
    assert all('vent_open' not in row['actions'] for row in result['forecast']['trajectory'])
