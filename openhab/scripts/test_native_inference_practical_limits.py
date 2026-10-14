"""Brief unrelated host paging must not prohibit a capped inference worker."""
import pytest
from test_native_inference_pressure import rig


def test_observed_five_mib_swapout_and_two_ms_stall_are_tolerated(rig):
    guard,sample,*_=rig
    sample(10.1,out=1280,some=2000,full=2000)
    guard.check()


def test_swapout_is_bounded_over_full_window_and_refusal_latches(rig):
    guard,sample,*_=rig
    sample(10.1,out=2048);guard.check()
    sample(10.2,out=4096);guard.check()
    sample(10.3,out=4097)
    with pytest.raises(ValueError,match='swap-out.*trailing one-second'):guard.check()
    sample(12,out=4097)
    with pytest.raises(ValueError,match='previously refused'):guard.check()


def test_swapout_counter_regression_still_refuses(rig):
    guard,sample,*_=rig
    sample(10.1,out=1);guard.check();sample(10.2,out=0)
    with pytest.raises(ValueError,match='regressed'):guard.check()


def test_swapout_window_expires_only_at_observed_sample(rig):
    guard,sample,*_=rig
    sample(10.5,out=4096);guard.check();sample(11.5,out=4096);guard.check()
    sample(11.6,out=8192);guard.check()
