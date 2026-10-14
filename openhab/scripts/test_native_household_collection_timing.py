"""Short-lived household measurements are acquired close to their issue clock."""
from datetime import datetime, timedelta, timezone
import pytest
from household_cycle import ObservingBackend

ISSUE = datetime(2026, 10, 14, 18, 40, 15, tzinfo=timezone.utc)


def test_native_collection_preserves_parent_and_acquires_fresh_inverter_sample():
    now = [ISSUE - timedelta(seconds=24)]
    ticks = [0.]
    original = {'forecast': 'original'}
    calls = []
    class Parent:
        def collect(self, **request):
            calls.append(('parent', request))
            return original
    def sleep(seconds):
        now[0] += timedelta(seconds=seconds)
        ticks[0] += seconds
    def collect(*, issue, remaining, guard):
        calls.append(('household', now[0]))
        assert 0 < remaining() <= 4
        # A ten-second source cadence leaves this earlier sample valid through
        # the measured twelve seconds of post-issue household processing.
        sample = ISSUE - timedelta(seconds=10)
        sleep(2)
        return {'received_at': sample.isoformat(), 'valid_until': (sample + timedelta(seconds=30)).isoformat()}
    adapter = ObservingBackend(Parent(), collector=collect, guard=lambda: None,
        clock=lambda: now[0], monotonic=lambda: ticks[0], sleep=sleep, near_issue=True)
    known = now[0]
    assert adapter.collect(issue=ISSUE, known_at=known) is original
    assert calls == [('parent', {'issue': ISSUE, 'known_at': known}), ('household', ISSUE-timedelta(seconds=7))]
    assert adapter.collection['status'] == 'collected'
    assert datetime.fromisoformat(adapter.collection['originals']['valid_until']) > ISSUE + timedelta(seconds=12)


def test_wait_guard_failure_does_not_replace_original_forecast_inputs():
    now = [ISSUE-timedelta(seconds=24)]
    original = object()
    class Parent:
        def collect(self, **request): return original
    def guard(): raise ValueError('household source changed')
    adapter = ObservingBackend(Parent(), collector=lambda **kw: pytest.fail('collector started'),
        guard=guard, clock=lambda: now[0], near_issue=True)
    assert adapter.collect(issue=ISSUE, known_at=now[0]) is original
    assert adapter.collection['reason'] == 'source_collection_failed'


def test_native_driver_selects_late_collection(tmp_path, monkeypatch):
    from test_household_native_cycle_driver import native_setup
    cycle, native, config, calls = native_setup(tmp_path, monkeypatch)
    original = native.publish_cycle
    def publish(settings, **kwargs):
        assert kwargs['backend'].near_issue is True
        return original(settings, **kwargs)
    monkeypatch.setattr(native, 'publish_cycle', publish)
    assert cycle.run_cycle(config, code_revision='e'*40)['status'] == 'published'


def test_stalled_wall_clock_cannot_hold_the_forecast_indefinitely():
    now = ISSUE-timedelta(seconds=24)
    ticks = [0.]
    original = object()
    class Parent:
        def collect(self, **request): return original
    def sleep(seconds): ticks[0] += seconds
    adapter = ObservingBackend(Parent(), collector=lambda **kw: pytest.fail('collector started'),
        guard=lambda: None, clock=lambda: now, monotonic=lambda: ticks[0], sleep=sleep, near_issue=True)
    assert adapter.collect(issue=ISSUE, known_at=now) is original
    assert adapter.collection['reason'] == 'source_collection_failed'
    assert ticks[0] <= 19
