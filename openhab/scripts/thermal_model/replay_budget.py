"""Scoped shared replay time; inactive callers retain their existing limits."""
from contextlib import contextmanager
from contextvars import ContextVar
import math

_remaining=ContextVar('earthship_shared_replay_remaining',default=None)


def _seconds(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
        raise ValueError('shared replay deadline elapsed or invalid')
    return float(value)


def remaining_budget(maximum):
    maximum=_seconds(maximum);remaining=_remaining.get()
    return maximum if remaining is None else min(maximum,_seconds(remaining()))


def check_shared_budget():
    remaining=_remaining.get()
    if remaining is not None:_seconds(remaining())


@contextmanager
def shared_replay_budget(remaining):
    if not callable(remaining):raise ValueError('remaining replay budget callback required')
    parent=_remaining.get()
    def bounded():
        value=_seconds(remaining())
        return value if parent is None else min(value,_seconds(parent()))
    token=_remaining.set(bounded)
    try:
        check_shared_budget();yield
    finally:_remaining.reset(token)
