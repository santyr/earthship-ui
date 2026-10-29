"""Publication-local pure decoding never replaces original data or its guards."""
from contextvars import Context, copy_context
from copy import deepcopy
import cProfile
from datetime import timedelta
import json
from pathlib import Path
from threading import Thread

import pytest
import household_production_point_reuse as reuse
import production_thermal_source as producer
from household.control_contracts import instant
from weather_learning.tests.test_production_thermal_temperature import context_case, serving


def prepared(context_case):
    source, args, *_ = context_case
    value = source.collect_context(**args)
    assert value['mode'] == 'confirmed_production_temperature'
    kwargs = dict(forecast=dict(rows=value['rows']), issue=instant(value['issue']),
                  available=instant(value['prepared_at']), epoch=value['source_sensor_epoch'],
                  site=value['site'], timezone=value['timezone'], guard=lambda: None)
    return source, value, kwargs


def profiled(operation, code):
    profile = cProfile.Profile()
    result = profile.runcall(operation)
    return result, sum(row.callcount for row in profile.getstats() if row.code is code)


def test_first_full_decoder_then_all_three_fresh_original_reads_and_detached_points(context_case, monkeypatch):
    source, value, args = prepared(context_case)
    original = producer._points
    seen = []
    read = reuse._read
    def observed(path, maximum):
        seen.append(Path(path))
        return read(path, maximum)
    monkeypatch.setattr(reuse, '_read', observed)
    with reuse.job_production_points(lambda: None) as state:
        first, cold = profiled(lambda: producer._points(value['selection'], value['production_receipt'], **args), original.__code__)
        assert first == value['points'] and cold == 1
        seen.clear()
        first[0]['temp_f'] += 100
        again, warm = profiled(lambda: producer._points(value['selection'], value['production_receipt'], **args), original.__code__)
        assert again == value['points'] and warm == 0
        assert set(seen) == {Path(ref['path']) for ref in value['originals']}
        assert len(seen) == 3
        source.verify_bindings(value, guard=lambda: None)
        assert state.misses == 1 and state.hits == 2
        assert 0 < state.bytes <= reuse.MAX_BYTES
    assert producer._points is original and not state.entries and state.bytes == 0


@pytest.mark.parametrize('damage', ['missing', 'bytes', 'same_length_bytes'])
def test_changed_original_is_never_hidden_by_a_warm_decoding(context_case, damage):
    _, value, args = prepared(context_case)
    path = Path(value['originals'][1]['path'])
    with reuse.job_production_points(lambda: None) as state:
        producer._points(value['selection'], value['production_receipt'], **args)
        if damage == 'missing':
            path.unlink()
        elif damage == 'bytes':
            path.write_bytes(path.read_bytes() + b'not-json')
        else:
            raw = path.read_bytes()
            path.write_bytes(raw.replace(b'false', b'true ', 1))
        with pytest.raises((OSError, ValueError, KeyError)):
            producer._points(value['selection'], value['production_receipt'], **args)
        assert not state.entries and state.hits == 0


def test_unchanged_semantics_with_new_original_bytes_require_a_complete_decode(context_case):
    _, value, args = prepared(context_case)
    original = producer._points
    with reuse.job_production_points(lambda: None) as state:
        producer._points(value['selection'], value['production_receipt'], **args)
        path = Path(value['originals'][1]['path'])
        path.write_bytes(path.read_bytes() + b'\n')
        actual, count = profiled(lambda: producer._points(value['selection'], value['production_receipt'], **args), original.__code__)
        assert actual == value['points'] and count == 1 and state.hits == 0


@pytest.mark.parametrize('parameter', ['forecast', 'available', 'site', 'timezone', 'epoch'])
def test_complete_request_arguments_are_part_of_reuse_identity(context_case, parameter):
    _, value, args = prepared(context_case)
    original = producer._points
    with reuse.job_production_points(lambda: None) as state:
        producer._points(value['selection'], value['production_receipt'], **args)
        changed = deepcopy(args)
        if parameter == 'forecast':
            changed['forecast']['extra_original_parameter'] = 'distinct'
        elif parameter == 'available':
            changed['available'] -= timedelta(microseconds=1)
        elif parameter == 'site':
            changed['site']['latitude'] += 1
        else:
            changed[parameter] = 'different'
        try:
            _, count = profiled(lambda: producer._points(value['selection'], value['production_receipt'], **changed), original.__code__)
            assert count == 1
        except (ValueError, KeyError):
            pass
        assert state.hits == 0


def test_guard_refusal_is_sticky_and_restoration_still_runs(context_case):
    _, value, args = prepared(context_case)
    original = producer._points
    refuse = [False]
    error = TimeoutError('original publication deadline')
    def guard():
        if refuse[0]:
            raise error
    with pytest.raises(TimeoutError, match='original publication deadline'):
        with reuse.job_production_points(guard) as state:
            producer._points(value['selection'], value['production_receipt'], **args)
            refuse[0] = True
            with pytest.raises(TimeoutError) as first:
                producer._points(value['selection'], value['production_receipt'], **args)
            refuse[0] = False
            with pytest.raises(TimeoutError) as second:
                producer._points(value['selection'], value['production_receipt'], **args)
            assert first.value is second.value is error
            assert not state.entries
    assert producer._points is original


@pytest.mark.parametrize('damage', ['missing', 'expired', 'wrong_phase'])
def test_original_named_raw_fallbacks_do_not_become_job_failures(context_case, damage):
    source, args, state, *_ = context_case
    if damage == 'missing':
        (state.root/'production-forecast.json').unlink()
    elif damage == 'expired':
        args['issue'] += timedelta(hours=2)
        args['clock'] = lambda: args['issue'] - timedelta(seconds=2)
        for row in args['forecast']['rows']:
            row['at'] = (instant(row['at']) + timedelta(hours=2)).isoformat()
    else:
        args['sensor_epoch'] = 'different-original-phase'
    with reuse.job_production_points(lambda: None):
        value = source.collect_context(**args)
        assert value['mode'] == 'native_raw_fallback'
        assert value['reason'].startswith('production_temperature_')


def test_cache_capacity_falls_back_to_the_original_full_decoder(context_case, monkeypatch):
    _, value, args = prepared(context_case)
    original = producer._points
    monkeypatch.setattr(reuse, 'MAX_BYTES', 32)
    with reuse.job_production_points(lambda: None) as state:
        for _ in range(2):
            actual, count = profiled(lambda: producer._points(value['selection'], value['production_receipt'], **args), original.__code__)
            assert actual == value['points'] and count == 1
        assert not state.entries and state.bytes == 0


def test_oversized_request_key_is_not_admitted(context_case):
    _, value, args = prepared(context_case)
    args['forecast']['extra_original_parameter'] = 'x' * reuse.MAX_KEY_BYTES
    original = producer._points
    with reuse.job_production_points(lambda: None) as state:
        for _ in range(2):
            _, count = profiled(lambda: producer._points(value['selection'], value['production_receipt'], **args), original.__code__)
            assert count == 1
        assert not state.entries


def test_fresh_context_and_other_thread_run_the_full_original_decoder(context_case):
    _, value, args = prepared(context_case)
    original = producer._points
    with reuse.job_production_points(lambda: None) as state:
        producer._points(value['selection'], value['production_receipt'], **args)
        _, count = profiled(lambda: Context().run(producer._points, value['selection'], value['production_receipt'], **args), original.__code__)
        assert count == 1 and state.hits == 0
        context = copy_context()
        values = []
        thread = Thread(target=lambda: values.append(context.run(producer._points, value['selection'], value['production_receipt'], **args)))
        thread.start(); thread.join(timeout=10)
        assert not thread.is_alive() and values == [value['points']] and state.hits == 0


def test_copied_context_and_reader_cannot_reuse_an_ended_job(context_case):
    _, value, args = prepared(context_case)
    original = producer._points
    with reuse.job_production_points(lambda: None) as state:
        producer._points(value['selection'], value['production_receipt'], **args)
        saved = producer._points
        context = copy_context()
    actual, count = profiled(lambda: context.run(saved, value['selection'], value['production_receipt'], **args), original.__code__)
    assert actual == value['points'] and count == 1 and not state.active and not state.entries


def test_nested_reader_scope_is_refused_without_replacing_the_owner(context_case):
    original = producer._points
    with reuse.job_production_points(lambda: None):
        installed = producer._points
        with pytest.raises(ValueError, match='one original publication guard'):
            with reuse.job_production_points(lambda: None):
                pass
        assert producer._points is installed
    assert producer._points is original


@pytest.mark.parametrize('when', ['entry', 'exit'])
def test_cycle_requires_the_exact_helper_source_and_restores_on_refusal(monkeypatch, when):
    import household_cycle as cycle
    import household_forecast_score as score
    original = producer._points
    read = score._policy_source_bytes
    calls = []
    def observed(path):
        raw = read(path)
        if Path(path).name == 'household_production_point_reuse.py':
            calls.append(path)
            if when == 'entry' or len(calls) > 1:
                return raw + b'\n'
        return raw
    monkeypatch.setattr(score, '_policy_source_bytes', observed)
    with pytest.raises(ValueError, match='publication production point helper'):
        with cycle.publication_production_reads(lambda: None):
            assert producer._points is not original
    assert producer._points is original
