"""Deterministic bounded guards over real small lossless segmented sources."""
from datetime import timedelta
import json

import pytest

import weather_temperature_segmented_binding as binding
import weather_temperature_source_segments as codec
from test_weather_temperature_source_segments import (
    AT, envelope, request, oracle, documents, rewrite_segments)


class Clock:
    def __init__(self): self.now = 10.0
    def __call__(self): return self.now


def adapter(check, monkeypatch, clock=None):
    # A missing adapter must fail as the intended absent feature, not ImportError.
    assert hasattr(binding, '_SegmentedGuard'), 'missing bounded numeric segmented guard'
    clock = clock or Clock()
    monkeypatch.setattr(binding, 'monotonic', clock)
    return binding._SegmentedGuard(check), clock


def test_numeric_guard_checks_on_64th_inner_callback_and_exit(monkeypatch):
    calls = []
    guard, _ = adapter(lambda: calls.append(True) or 20, monkeypatch)
    for _ in range(63): guard()
    assert len(calls) == 1
    guard()
    assert len(calls) == 2
    guard.finish()
    assert len(calls) == 3


def test_elapsed_checkpoint_checks_before_64_calls(monkeypatch):
    calls = []
    guard, clock = adapter(lambda: calls.append(True) or 20, monkeypatch)
    clock.now += .006
    guard()
    assert len(calls) == 2


def test_every_inner_callback_refuses_frozen_expiry_without_full_callback(monkeypatch):
    calls = []
    guard, clock = adapter(lambda: calls.append(True) or .001, monkeypatch)
    clock.now += .002
    with pytest.raises(ValueError): guard()
    assert len(calls) == 1
    clock.now = 10
    with pytest.raises(ValueError): guard()
    assert len(calls) == 1


def test_larger_later_budget_never_renews_deadline(monkeypatch):
    remaining = iter([.02, 200])
    guard, clock = adapter(lambda: next(remaining), monkeypatch)
    clock.now += .006
    guard()
    clock.now += .015
    with pytest.raises(ValueError): guard()


def test_smaller_later_budget_tightens_deadline(monkeypatch):
    remaining = iter([20, .001])
    guard, clock = adapter(lambda: next(remaining), monkeypatch)
    clock.now += .006
    guard()
    clock.now += .002
    with pytest.raises(ValueError): guard()


def test_callback_execution_time_is_charged_from_before_call(monkeypatch):
    clock = Clock()
    def check():
        clock.now += .02
        return .01
    with pytest.raises(ValueError): adapter(check, monkeypatch, clock)


def test_failure_at_next_checkpoint_permanently_latches(monkeypatch):
    calls = []
    def check():
        calls.append(True)
        if len(calls) == 2: raise RuntimeError('original guard cancelled')
        return 20
    guard, _ = adapter(check, monkeypatch)
    for _ in range(63): guard()
    for action in (guard, guard, guard.finish, guard.local):
        with pytest.raises(RuntimeError, match='original guard cancelled'): action()
    assert len(calls) == 2


@pytest.mark.parametrize('remaining', [True, '1', 0, -1, float('nan'), float('inf')])
def test_invalid_initial_numeric_budget_refuses(monkeypatch, remaining):
    with pytest.raises(ValueError): adapter(lambda: remaining, monkeypatch)


@pytest.mark.parametrize('remaining', [None, True, '1', 0, -1, float('nan'), float('inf')])
def test_numeric_mode_never_drops_its_deadline(monkeypatch, remaining):
    values = iter([20, remaining, 20])
    guard, clock = adapter(lambda: next(values), monkeypatch)
    clock.now += .006
    with pytest.raises(ValueError): guard()
    with pytest.raises(ValueError): guard.finish()


def test_clock_regression_refuses_and_latches(monkeypatch):
    guard, clock = adapter(lambda: 20, monkeypatch)
    clock.now -= 1
    with pytest.raises(ValueError): guard()
    clock.now += 2
    with pytest.raises(ValueError): guard.local()


@pytest.fixture
def retained(tmp_path):
    rows = [(AT + timedelta(minutes=n), envelope(AT + timedelta(minutes=n))) for n in (0, 5, 10)]
    args = request(rows, targets=[AT + timedelta(minutes=n) for n in (0, 3, 5, 10)])
    source = codec.build_shared_temperature_source(**args)
    root = tmp_path/'input';root.mkdir(mode=0o700)
    path = codec.write_shared_temperature_source(root, source)
    manifest, parts = documents(root, path)
    part = parts[0]
    path = rewrite_segments(root, manifest,
        [dict(part, native_rows=[row]) for row in part['native_rows']])
    return args, path, codec.read_shared_temperature_source(root, path)


def invoke(api, operation, path, source, output, guard):
    if operation == 'read': return api.read_shared_temperature_source(path.parent, path, guard=guard)
    if operation == 'replay': return api.replay_shared_temperature_source(source, guard=guard)
    return api.write_shared_temperature_source(output, source, guard=guard)


@pytest.mark.parametrize('operation', ['read', 'replay', 'write'])
def test_initial_none_preserves_original_unbatched_terminal_behavior(tmp_path, retained, monkeypatch, operation):
    _, path, source = retained
    output = tmp_path/'output';output.mkdir(mode=0o700)
    original_output = tmp_path/'original-output';original_output.mkdir(mode=0o700)
    calls = []
    invoke(codec, operation, path, source, original_output, lambda: calls.append(True))
    original = len(calls);calls.clear()
    assert hasattr(binding, 'write_shared_temperature_source'), 'missing guarded segmented operations'
    monkeypatch.setattr(binding, 'monotonic', Clock())
    invoke(binding, operation, path, source, output, lambda: calls.append(True))
    assert len(calls) == original


def test_real_codec_complete_replay_matches_legacy_oracle_and_inventory(tmp_path, retained, monkeypatch):
    args, path, source = retained
    assert hasattr(binding, 'write_shared_temperature_source'), 'missing guarded segmented operations'
    monkeypatch.setattr(binding, 'monotonic', Clock())
    guarded = binding.read_shared_temperature_source(path.parent, path, guard=lambda: 20)
    actual = binding.replay_shared_temperature_source(guarded, guard=lambda: 20)
    assert actual == oracle(args)
    assert all(actual[role][1][1] is None for role in ('air', 'mass', 'outdoor'))
    expected = (path,) + tuple(path.parent/child['name'] for child in json.loads(path.read_bytes())['segments'])
    assert codec.shared_temperature_source_files(guarded) == expected
    assert len(expected) == 4
    output = tmp_path/'output';output.mkdir(mode=0o700)
    saved = binding.write_shared_temperature_source(output, source, guard=lambda: 20)
    assert saved.read_bytes() == path.read_bytes()
    assert binding.replay_shared_temperature_source(
        binding.read_shared_temperature_source(output, saved, guard=lambda: 20), guard=lambda: 20) == actual


@pytest.mark.parametrize('operation', ['read', 'replay', 'write'])
@pytest.mark.parametrize('damage', ['input_replace', 'child_bytes', 'manifest_bytes'])
def test_successful_exit_callback_cannot_mutate_retained_custody(tmp_path, retained, monkeypatch, operation, damage):
    _, path, source = retained
    output = tmp_path/'output';output.mkdir(mode=0o700)
    assert hasattr(binding, 'write_shared_temperature_source'), 'missing guarded segmented operations'
    monkeypatch.setattr(binding, 'monotonic', Clock())
    completed = [];mutated = []
    name = {'read':'read_shared_temperature_source', 'replay':'replay_shared_temperature_source',
            'write':'write_shared_temperature_source'}[operation]
    original = getattr(codec, name)
    def observe_return(*args, **kwargs):
        result = original(*args, **kwargs)
        completed.append(True)
        return result
    # This witness delegates every byte/row/replay to the original codec and
    # observes its return boundary; it never substitutes a numerical result.
    monkeypatch.setattr(codec, name, observe_return)
    def check():
        if completed and not mutated:
            mutated.append(True)
            root = output if operation == 'write' and damage != 'input_replace' else path.parent
            target = root/path.name if damage == 'manifest_bytes' else root/json.loads(path.read_bytes())['segments'][0]['name']
            raw = target.read_bytes()
            if damage == 'input_replace': target.unlink()
            target.write_bytes(raw if damage == 'input_replace' else raw + b' ')
            target.chmod(0o600)
        return 20
    with pytest.raises((ValueError, OSError)):
        invoke(binding, operation, path, source, output, check)
    assert completed and mutated, 'mutation must occur only after the real codec returned'


@pytest.mark.parametrize('operation', ['read', 'replay', 'write'])
def test_terminal_local_checks_never_call_external_guard(tmp_path, retained, monkeypatch, operation):
    args, path, source = retained
    output = tmp_path/'output';output.mkdir(mode=0o700)
    assert hasattr(binding, 'write_shared_temperature_source'), 'missing guarded segmented operations'
    clock = Clock();monkeypatch.setattr(binding, 'monotonic', clock)
    completed = [];post_return_checks = []
    name = {'read':'read_shared_temperature_source', 'replay':'replay_shared_temperature_source',
            'write':'write_shared_temperature_source'}[operation]
    original = getattr(codec, name)
    def observe_return(*args, **kwargs):
        result = original(*args, **kwargs)
        completed.append(True)
        return result
    monkeypatch.setattr(codec, name, observe_return)
    def check():
        if completed:
            post_return_checks.append(True)
            clock.now += .006  # A scheduled/full check would now be time-due.
        return 20
    result = invoke(binding, operation, path, source, output, check)
    assert post_return_checks == [True]
    if operation == 'replay': assert result == oracle(args)
    elif operation == 'read': assert len(codec.shared_temperature_source_files(result)) == 4
    else: assert result.read_bytes() == path.read_bytes()
