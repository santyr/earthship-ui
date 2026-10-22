"""Pure rain-counter transitions, shared by receipt capture and display products.

A baseline is an observed counter level, not an amount of rain. Recovery creates
an unknown discontinuity; it never assigns a gap's accumulation to the next hour.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from math import isfinite

MAXIMUM_STEP_IN=.5
MINIMUM_RESET_DROP_IN=.1


def _finite(value):return type(value) in (int,float) and isfinite(value)


@dataclass(frozen=True)
class CounterTransition:
    status:str
    reason:str|None
    delta_in:float|None
    new_phase:bool=False


class CounterTracker:
    def __init__(self,*,validity_seconds,maximum_counter_in):
        if type(validity_seconds) is not int or not 1<=validity_seconds<=300 or not _finite(maximum_counter_in) or not 0<maximum_counter_in<=1000000:raise ValueError('bounded rain counter continuity policy required')
        self.validity_seconds=validity_seconds;self.maximum_counter_in=maximum_counter_in
        self.baseline=None;self.valid_at=None;self.valid_tick=None;self.last_at=None;self.last_tick=None;self.candidate=None

    def break_sequence(self):
        """An invalid owned receipt cannot confirm a preceding suspect level."""
        self.candidate=None

    def _baseline(self,value,at,tick):
        self.baseline=float(value);self.valid_at=at;self.valid_tick=float(tick);self.candidate=None

    def observe(self,value,*,at,tick):
        if (not _finite(value) or not 0<=value<=self.maximum_counter_in or not isinstance(at,datetime) or at.utcoffset() is None or not _finite(tick)):raise ValueError('finite bounded counter and aware receipt clocks required')
        at=at.astimezone(timezone.utc)
        rollback=self.last_at is not None and (at<self.last_at or tick<self.last_tick)
        self.last_at,self.last_tick=at,float(tick)
        if self.baseline is None or rollback:
            self._baseline(value,at,tick)
            return CounterTransition('baseline','clock_reset' if rollback else 'first_counter',None,rollback)
        wall=(at-self.valid_at).total_seconds();elapsed=max(wall,tick-self.valid_tick);gap=elapsed>self.validity_seconds;delta=value-self.baseline
        if 0<=delta<=MAXIMUM_STEP_IN:
            self._baseline(value,at,tick)
            return CounterTransition('baseline' if gap else 'accepted','unobserved_gap' if gap else None,None if gap else float(delta),gap)
        reason='counter_drop' if delta<0 else 'counter_jump'
        eligible=gap or delta<=-MINIMUM_RESET_DROP_IN+1e-9
        previous=self.candidate
        if previous is not None and eligible:
            before,when,then,cause=previous;age=(at-when).total_seconds();tick_age=tick-then
            if cause==reason and 0<age<=self.validity_seconds and 0<tick_age<=self.validity_seconds and 0<=value-before<=MAXIMUM_STEP_IN:
                self._baseline(value,at,tick)
                return CounterTransition('recovered','confirmed_counter_reset' if delta<0 else 'confirmed_post_gap_counter',None,True)
        # A short-interval spike cannot become a first post-gap confirmation
        # merely because the next receipt crosses the freshness boundary.
        self.candidate=(float(value),at,float(tick),reason) if eligible else None
        return CounterTransition('withheld',reason,None)
