"""Counter repairs retain discontinuities without fabricating missing rainfall."""
from datetime import datetime,timedelta,timezone
from importlib import import_module
import pytest

START=datetime(2026,10,22,tzinfo=timezone.utc)
def tracker():return import_module('weather_station_counter').CounterTracker(validity_seconds=120,maximum_counter_in=100000.)
def observe(state,value,seconds):return state.observe(value,at=START+timedelta(seconds=seconds),tick=float(seconds))


def test_normal_tips_are_differences_after_an_explicit_unknown_baseline():
 state=tracker();first=observe(state,100.,0);next=observe(state,100.01,16)
 assert first.status=='baseline' and first.delta_in is None
 assert next.status=='accepted' and next.delta_in==pytest.approx(.01) and next.new_phase is False


def test_small_drop_never_lowers_a_valid_baseline_or_creates_return_rain():
 state=tracker();observe(state,100.,0);bad=observe(state,99.99,16);back=observe(state,100.,32)
 assert bad.status=='withheld' and bad.reason=='counter_drop'
 assert back.status=='accepted' and back.delta_in==0
 assert state.baseline==100.


def test_large_gap_requires_two_consistent_natural_readings_and_an_unknown_phase():
 state=tracker();observe(state,100.,0);first=observe(state,101.,21600);second=observe(state,101.,21616);next=observe(state,101.01,21632)
 assert first.status=='withheld' and first.delta_in is None
 assert second.status=='recovered' and second.new_phase is True and second.delta_in is None
 assert next.status=='accepted' and next.delta_in==pytest.approx(.01)


def test_short_interval_spike_return_does_not_rebase_to_bad_value():
 state=tracker();observe(state,100.,0);bad=observe(state,500.,16);back=observe(state,100.,32)
 assert bad.status=='withheld' and back.delta_in==0 and state.baseline==100.


def test_pre_gap_spike_cannot_confirm_a_post_gap_baseline():
 state=tracker();observe(state,100.,0)
 assert observe(state,101.,112).status=='withheld'
 assert observe(state,101.,128).status=='withheld'
 assert state.baseline==100.
 assert observe(state,101.,144).status=='recovered'


def test_consistent_hardware_reset_starts_a_new_phase_without_assigning_negative_rain():
 state=tracker();observe(state,100.,0);observe(state,0.,16);recovered=observe(state,0.01,32)
 assert recovered.status=='recovered' and recovered.delta_in is None and recovered.new_phase is True
 assert observe(state,.02,48).delta_in==pytest.approx(.01)


def test_unknown_gap_with_small_counter_change_does_not_assign_gap_rain_to_now():
 state=tracker();observe(state,100.,0);next=observe(state,100.1,300)
 assert next.status=='baseline' and next.reason=='unobserved_gap' and next.new_phase is True and next.delta_in is None
 assert observe(state,100.11,316).delta_in==pytest.approx(.01)


def test_inconsistent_or_stale_confirmation_cannot_recover_a_jump():
 state=tracker();observe(state,100.,0);observe(state,101.,300)
 assert observe(state,103.,316).status=='withheld'
 assert observe(state,103.,500).status=='withheld'
 assert observe(state,103.,516).status=='recovered'


def test_invalid_receipt_breaks_consecutive_confirmation():
 state=tracker();observe(state,100.,0);observe(state,101.,300);state.break_sequence()
 assert observe(state,101.,316).status=='withheld'
 assert observe(state,101.,332).status=='recovered'


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1,True,100001])
def test_invalid_values_do_not_mutate_counter_state(bad):
 state=tracker();observe(state,100.,0)
 with pytest.raises(ValueError):observe(state,bad,16)
 assert state.baseline==100.


def test_clock_rollback_discards_pending_confirmation_and_declares_a_new_baseline():
 state=tracker();observe(state,100.,0);observe(state,101.,300);result=observe(state,101.,200)
 assert result.status=='baseline' and result.new_phase is True and result.reason=='clock_reset'


def collector():
 from weather_rain_receiver import RainCollector
 from weather_rain_evidence import RainPolicy
 current=[0.]
 state=RainCollector(RainPolicy(sensor_id=206),clock=lambda:START+timedelta(seconds=current[0]),monotonic=lambda:current[0],process_id=lambda:1)
 def receive(value,seconds):
  current[0]=seconds;state.observe(dict(model='Fineoffset-WH65B',id=206,totalrainin=value));return state.snapshot()
 return state,receive


def test_strict_collector_recovers_a_real_gap_with_new_epoch_and_no_gap_increment():
 state,receive=collector();first=receive(100.,0);bad=receive(101.,21600);recovered=receive(101.,21616);next=receive(101.01,21632)
 assert bad['record']['status']=='invalid'
 assert recovered['record']['status']=='valid' and recovered['record']['totalRainIn']==101.
 assert recovered['streamEpoch']!=first['streamEpoch'] and recovered['record']['streamEpoch']==recovered['streamEpoch']
 assert recovered['packetCount']==1 and recovered['counterJumps']==recovered['invalidPackets']==0
 assert next['record']['totalRainIn']==101.01 and next['streamEpoch']==recovered['streamEpoch']


def test_strict_collector_does_not_admit_a_single_small_counter_drop():
 state,receive=collector();first=receive(100.,0);bad=receive(99.99,16);back=receive(100.,32)
 assert bad['record']['status']=='invalid' and bad['record']['reason']=='counter_drop'
 assert bad['counterDrops']==1 and bad['invalidPackets']==1
 assert back['record']['status']=='valid' and back['record']['totalRainIn']==100.
 assert first['streamEpoch']==back['streamEpoch']
