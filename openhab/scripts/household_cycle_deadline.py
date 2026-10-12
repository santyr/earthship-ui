"""Main-thread observation cutoff, composed with fixed transport deadlines.

The cutoff is separate from Exception so reader error wrappers cannot swallow
it. Existing HTTP readers temporarily own the alarm with their own timeout
clamped to the same remaining budget; the total timer resumes without renewal.
"""
from contextlib import contextmanager
import math,signal,threading,time


class ObservationDeadline(BaseException):
    pass


@contextmanager
def observation_deadline(seconds):
    if (type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=6 or
        threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL)!=(0.,0.)):
        raise ValueError('exclusive bounded observation alarm required')
    previous=signal.getsignal(signal.SIGALRM)
    def expired(*args):raise ObservationDeadline()
    expired.household_observation_deadline=True
    signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,seconds)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0.)
        signal.signal(signal.SIGALRM,previous)


@contextmanager
def borrow_observation_timer():
    """Allow a bounded legacy HTTP reader to own its exclusive alarm briefly."""
    previous=signal.getsignal(signal.SIGALRM)
    if not getattr(previous,'household_observation_deadline',False):
        yield;return
    duration,interval=signal.getitimer(signal.ITIMER_REAL)
    if duration<=0 or interval!=0:raise ObservationDeadline()
    started=time.monotonic();signal.setitimer(signal.ITIMER_REAL,0.)
    try:yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0.)
        signal.signal(signal.SIGALRM,previous)
        left=duration-(time.monotonic()-started)
        if left<=0:raise ObservationDeadline()
        signal.setitimer(signal.ITIMER_REAL,left)
