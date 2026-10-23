"""Constructed weather retains the original confirmed temperature procedure."""
from copy import deepcopy
from datetime import timedelta
import pytest
from test_production_thermal_temperature import serving,context_case
from weather_learning.contracts import canonical,instant


def case(context_case):
    from weather_learning.native_scenarios import _forcings
    source,args,*_=context_case;context=source.collect_context(**args);issue=args['issue']
    actions=dict(indoor_shade_closed=.25,outdoor_shade_present=.5,vent_open=.75)
    raw=_forcings(context['rows'],issue,2,actions)
    capture=dict(issued_at=issue.isoformat(),inputs_available_at=args['clock']().isoformat(),weather_conditioning=context)
    return raw,capture,context,issue,actions


def test_central_case_reuses_confirmed_temperature_points_and_unchanged_raw_solar(context_case):
    from weather_learning.native_scenarios import _condition
    from household.production_weather_conditioning import apply_conditioning
    raw,capture,context,issue,_=case(context_case);before=canonical(context)
    expected=apply_conditioning(raw,context,issue=issue,available=instant(capture['inputs_available_at']),initial_outdoor_f=53.)
    actual=_condition(raw,context['rows'],capture,53.)
    assert actual==expected
    assert canonical(context)==before


@pytest.mark.parametrize('delta,multiplier',[(5.4,1.2),(0.,.5)])
def test_declared_perturbations_preserve_original_initial_anchor_and_actions(context_case,delta,multiplier):
    from weather_learning.native_scenarios import _condition,_forcings
    from household.production_weather_conditioning import apply_conditioning
    raw,capture,context,issue,actions=case(context_case)
    rows=deepcopy(context['rows'])
    for row in rows:row['tempF']+=delta;row['radiationWm2']*=multiplier
    constructed=_forcings(rows,issue,2,actions)
    expected=apply_conditioning(raw,context,issue=issue,available=instant(capture['inputs_available_at']),initial_outdoor_f=53.)
    actual=_condition(constructed,rows,capture,53.)
    first=instant(context['points'][0]['at'])
    for original,new in zip(expected,actual):
        weight=min(1.,(new.at-issue)/(first-issue))
        assert new.outdoor_f==pytest.approx(original.outdoor_f+delta*weight,abs=1e-10)
        assert new.radiation_wm2==pytest.approx(original.radiation_wm2*multiplier,abs=1e-10)
        assert (new.indoor_shade_closed,new.outdoor_shade_present,new.vent_open)==(.25,.5,.75)


def test_production_raw_fallback_retains_its_original_unconditioned_contract(context_case):
    from weather_learning.native_scenarios import _condition,_forcings
    source,args,state,*_=context_case;(state.root/'production-forecast.json').unlink()
    context=source.collect_context(**args);assert context['mode']=='native_raw_fallback'
    issue=args['issue'];rows=deepcopy(context['rows'])
    for row in rows:row['tempF']+=5.4;row['radiationWm2']*=1.2
    forcings=_forcings(rows,issue,2,dict(indoor_shade_closed=.25,outdoor_shade_present=.5,vent_open=.75))
    capture=dict(issued_at=issue.isoformat(),inputs_available_at=args['clock']().isoformat(),weather_conditioning=context)
    assert _condition(forcings,rows,capture,53.)==forcings
