"""Corrected rain windows distinguish rate/depth and unknown coverage."""
from datetime import datetime,timedelta,timezone
from importlib import import_module
from zoneinfo import ZoneInfo
import pytest

UTC=timezone.utc
START=datetime(2026,10,17,tzinfo=UTC)
def products(zone='UTC'):return import_module('weather_station_rain').RainProducts(timezone_name=zone,validity_seconds=120,maximum_counter_in=100000.)
def feed(state,start,end,*,initial=100.,rain=None):
 at=start;counter=initial
 while at<=end:
  counter+=0. if rain is None else rain(at)
  state.observe(counter,at=at,tick=at.timestamp());at+=timedelta(seconds=60)
 return counter

def snapshot(state,at):return state.snapshot(at=at,tick=at.timestamp())


def test_cold_or_stale_windows_are_not_reported_as_dry_zero():
 state=products();state.observe(100.,at=START,tick=START.timestamp());v=snapshot(state,START)
 assert v['products']['rolling_hour']['value'] is None
 assert v['products']['rate_10min']['value'] is None
 stale=snapshot(state,START+timedelta(seconds=121))
 assert stale['status']=='stale' and all(p['value'] is None for p in stale['products'].values())


def test_one_hour_amount_is_not_ten_minute_hourly_rate():
 state=products();end=START+timedelta(hours=2)
 feed(state,START,end,rain=lambda at:.1 if at==end-timedelta(minutes=40) else 0.)
 v=snapshot(state,end)['products']
 assert v['rolling_hour']['value']==pytest.approx(.1)
 assert v['rate_10min']['value']==0. and v['rate_10min']['unit']=='in/h'


def test_ten_minute_depth_is_multiplied_by_six_not_summed_into_an_hour():
 state=products();end=START+timedelta(hours=2)
 feed(state,START,end,rain=lambda at:.1 if at==end-timedelta(minutes=5) else 0.)
 p=snapshot(state,end)['products'];assert p['rate_10min']['value']==pytest.approx(.6)
 assert p['rolling_hour']['value']==pytest.approx(.1)


def test_sunday_week_and_month_boundaries_use_local_calendar_without_carrying_old_periods():
 state=products();start=datetime(2026,10,17,22,tzinfo=UTC);end=datetime(2026,10,19,0,1,tzinfo=UTC)
 feed(state,start,end,rain=lambda at:.1 if at in (datetime(2026,10,17,23,tzinfo=UTC),datetime(2026,10,18,12,tzinfo=UTC)) else 0.)
 p=snapshot(state,end)['products'];assert p['week']['start']=='2026-10-18T00:00:00+00:00'
 assert p['week']['value']==pytest.approx(.1) and p['day']['value']==0.
 assert p['month']['value'] is None and p['month']['partial_lower_bound']==pytest.approx(.2)


@pytest.mark.parametrize('day,hours',[(datetime(2026,3,8,tzinfo=ZoneInfo('America/Denver')),23),(datetime(2026,11,1,tzinfo=ZoneInfo('America/Denver')),25)])
def test_DST_day_end_has_actual_elapsed_hours(day,hours):
 start=day.astimezone(UTC);end=(day+timedelta(days=1)).astimezone(UTC)-timedelta(minutes=1);state=products('America/Denver')
 feed(state,start,end,rain=lambda at:.01 if at.minute==30 else 0.)
 p=snapshot(state,end)['products']['day'];assert p['value']==pytest.approx(hours*.01)
 assert (datetime.fromisoformat(p['end'])-datetime.fromisoformat(p['start'])).total_seconds()/3600==pytest.approx(hours-1/60)


def test_a_rain_event_is_not_erased_after_one_dry_hour():
 state=products();rain_at=START+timedelta(hours=25);end=rain_at+timedelta(hours=2)
 feed(state,START,end,rain=lambda at:.1 if at==rain_at else 0.)
 p=snapshot(state,end)['products']['event'];assert p['value']==pytest.approx(.1)
 # A subsequent fully observed quiet 24h interval qualifies its reset.
 feed(state,end+timedelta(minutes=1),rain_at+timedelta(hours=25),initial=100.1)
 p=snapshot(state,rain_at+timedelta(hours=25))['products']['event'];assert p['value']==0.


def test_period_crossing_a_source_gap_is_unknown_and_gap_rain_is_not_put_into_rate():
 state=products();last=feed(state,START,START+timedelta(hours=2));at=START+timedelta(hours=5)
 state.observe(last+.1,at=at,tick=at.timestamp());p=snapshot(state,at)['products']
 assert p['day']['value'] is p['rate_10min']['value'] is None
 assert p['day']['partial_lower_bound']==0.


def test_bad_counter_does_not_turn_a_return_into_rain_or_preserve_complete_windows():
 state=products();end=START+timedelta(hours=2);feed(state,START,end)
 state.observe(99.99,at=end+timedelta(seconds=16),tick=(end+timedelta(seconds=16)).timestamp())
 state.observe(100.,at=end+timedelta(seconds=32),tick=(end+timedelta(seconds=32)).timestamp())
 p=snapshot(state,end+timedelta(seconds=32))['products'];assert p['day']['partial_lower_bound']==0.
 assert p['rolling_hour']['value'] is None
