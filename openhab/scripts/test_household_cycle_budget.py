"""Post-publication replay uses the same nonrenewable original cycle budget."""
import time
import pytest
from household_cycle import CycleGuard
import weather_temperature_segmented_binding as binding


def test_publication_and_observation_share_one_absolute_stop():
    now=[0.];seen=[]
    forecast=CycleGuard(lambda:seen.append('forecast'),deadline=85,monotonic=lambda:now[0])
    observer=CycleGuard(forecast,deadline=85,monotonic=lambda:now[0])
    now[0]=20;assert forecast()==65
    now[0]=84;assert observer()==1
    now[0]=85
    with pytest.raises(ValueError,match='native publication deadline exceeded') as original:observer()
    now[0]=0
    with pytest.raises(ValueError) as again:observer()
    assert again.value is original.value and seen==['forecast','forecast','forecast']


@pytest.mark.parametrize('failure',[ValueError,KeyboardInterrupt])
def test_original_refusal_is_permanent_and_not_masked(failure):
    error=failure('original source refused');calls=[]
    def refused():calls.append(1);raise error
    guard=CycleGuard(refused,deadline=85,monotonic=lambda:0)
    for _ in range(2):
        with pytest.raises(failure) as observed:guard()
        assert observed.value is error
    assert calls==[1]


@pytest.mark.parametrize('now',[-1.,float('nan'),float('inf'),False,85.])
def test_nonregressing_finite_original_clock_and_expiry(now):
    clock=[0.];guard=CycleGuard(lambda:None,deadline=85,monotonic=lambda:clock[0]);assert guard()==85
    clock[0]=now
    with pytest.raises(ValueError,match='native publication deadline exceeded'):guard()


@pytest.mark.parametrize('deadline',[None,float('nan'),float('inf'),False])
def test_no_implicit_or_invalid_budget(deadline):
    with pytest.raises(ValueError):CycleGuard(lambda:None,deadline=deadline)


def test_original_segmented_adapter_keeps_local_expiry_and_full_checkpoints(monkeypatch):
    now=[0.];calls=[];monkeypatch.setattr(binding,'monotonic',lambda:now[0])
    guard=CycleGuard(lambda:calls.append(1),deadline=85,monotonic=lambda:now[0])
    adapter=binding._SegmentedGuard(guard)
    assert adapter.numeric and len(calls)==1
    for _ in range(63):adapter()
    assert len(calls)==1
    adapter();assert len(calls)==2
    now[0]=.006;adapter();assert len(calls)==3
    now[0]=85
    with pytest.raises(ValueError):adapter()
    assert len(calls)==3


def test_full_original_replay_equal_with_bounded_cycle_callback(tmp_path,monkeypatch):
    from test_household_segmented_replay_reuse import retained
    _,source,expected=retained(tmp_path/'retained',monkeypatch)
    unbatched=[];bounded=[]
    def original():unbatched.append(1)
    assert binding.replay_shared_temperature_source(source,guard=original)==expected
    guard=CycleGuard(lambda:bounded.append(1),deadline=time.monotonic()+85)
    assert binding.replay_shared_temperature_source(source,guard=guard)==expected
    assert 0<len(bounded)<len(unbatched)
