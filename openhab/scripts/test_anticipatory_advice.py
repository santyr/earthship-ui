"""Forecast triggers before current comfort is exceeded; no invented actuation."""
from copy import deepcopy
from datetime import timedelta
import pytest
from household.advice.anticipatory import solar_access, choose_plan, forecast_advice
from household.codec import canonical
from household.snapshot import HouseholdSnapshot
from test_household_advice_contract import snapshot, state, api, NOW


def states(*values):return tuple((v,72.) for v in values)


def test_vertical_south_glass_has_more_winter_low_sun_access_than_summer_high_sun():
    assert solar_access(20,180)>solar_access(70,180)>0
    assert solar_access(20,0)==0
    assert solar_access(0,180)==0
    assert solar_access(-5,180)==0
    assert solar_access(20,130)==pytest.approx(solar_access(20,230))
    assert solar_access(20,90,90)>solar_access(20,90,180)


def test_predicted_overheating_recommends_closing_while_current_air_is_comfortable():
    baseline=states(73,75,78,80)
    close=dict(start_hour=0,closed=1.,states=states(73,74,75,76))
    assert choose_plan(baseline,[close],70,76)==close


def test_predicted_cold_recommends_capturing_sun_before_the_temperature_drops():
    baseline=states(73,71,68,66)
    opening=dict(start_hour=0,closed=0.,states=states(73,73,72,71))
    assert choose_plan(baseline,[opening],70,76)==opening


def test_stored_heat_and_later_overheating_defeat_short_term_warming():
    baseline=states(70,71,73,74)
    opening=dict(start_hour=0,closed=0.,states=states(72,74,78,82))
    assert choose_plan(baseline,[opening],70,76) is None


def test_schedule_can_wait_until_a_future_window_and_ties_do_not_chatter():
    baseline=states(73,78,80,82)
    now=dict(start_hour=0,states=states(73,75,76,77))
    later=dict(start_hour=2,states=states(73,75,76,77))
    assert choose_plan(baseline,[now,later],70,76)==later


def test_tiny_or_no_solar_effect_does_not_invent_shade_benefit():
    assert choose_plan(states(80,80),[dict(start_hour=0,states=states(79.99,79.99))],70,76) is None
    assert choose_plan(states(73,73),[],70,76) is None


def run(monkeypatch, *, failed=False, adverse=False, recent=False):
    snap=snapshot();action=state();action['snapshot_id']=snap.snapshot_id;action['declarations']=[]
    if adverse:action['checks']['wind']=dict(clear=False,observed_at=NOW.isoformat(),valid_until=(NOW+timedelta(seconds=25)).isoformat(),source_ref='d'*64)
    if recent:action['shade_movements']=[dict(shade_id='shade-9',epoch='installation-1',stop_observed_at=(NOW-timedelta(seconds=590)).isoformat(),event_refs=['d'*64])]
    import household.advice.anticipatory as module
    def model(*args,**kw):
        if failed:raise ValueError('original forecast unavailable')
        return dict(action='Open shades now to capture solar heat',reason='Forecast cooling later; compare stored heat.',ventilation='Keep ventilation steady; reassess the forecast',until=NOW+timedelta(seconds=50))
    monkeypatch.setattr(module,'forecast_advice',model)
    p={'thermal_evaluation_context':None,'provisional_preferences':dict(schema='earthship-provisional-advice-preferences/v1',enabled=True,comfort_min_f=70,comfort_max_f=76,timezone='America/Denver')}
    return api().evaluate_advice(snapshot=snap,projections=p,policy=None,action_state=action,now=NOW)


def test_forecast_results_preserve_human_only_contract_and_source_expiry(monkeypatch):
    report=run(monkeypatch)
    assert report['domains']['shades']['comparison'][1]['alternative']=='Open shades now to capture solar heat'
    assert report['recommendations']==[] and report['automatic_actuation'] is False
    assert report['domains']['shades']['valid_until']<=(NOW+timedelta(seconds=50)).isoformat()
    assert 'Keep ventilation' in report['domains']['ventilation']['comparison'][1]['alternative']


def test_missing_forecast_does_not_fall_back_to_reactive_rule(monkeypatch):
    report=run(monkeypatch,failed=True)
    for domain in ('shades','ventilation'):
        assert report['domains'][domain]['comparison']==[]
        assert report['domains'][domain]['reason']=='provisional_forecast_unavailable'


def test_recent_movement_and_adverse_wind_are_still_honored(monkeypatch):
    report=run(monkeypatch,adverse=True,recent=True)
    assert report['domains']['shades']['comparison'][1]['alternative']=='Keep the recent shade setting'
    assert report['domains']['ventilation']['comparison'][1]['alternative']=='Avoid ventilation for now'
    assert report['domains']['shades']['valid_until']<=(NOW+timedelta(seconds=10)).isoformat()


def test_incomplete_forecast_context_is_refused():
    with pytest.raises((ValueError,KeyError,TypeError)):
        forecast_advice({},snapshot={},now=NOW,low=70,high=76,timezone_name='America/Denver')


def test_midwinter_east_sun_is_not_south_glazing_beam_gain():
    assert solar_access(15,20)==0
    assert solar_access(15,180)>.9


def test_glazing_incline_changes_solar_incidence_without_becoming_pv_array_tilt():
    # Sun at 25.5 degrees is normal to glazing tilted 64.5 from horizontal.
    assert solar_access(25.5,165,165,64.5)==pytest.approx(1.)
    assert solar_access(64.5,165,165,25.5)==pytest.approx(1.)
    assert solar_access(25.5,165,165,25.5)<1.
    assert solar_access(70,180,180,0)==pytest.approx(__import__('math').sin(__import__('math').radians(70)))
