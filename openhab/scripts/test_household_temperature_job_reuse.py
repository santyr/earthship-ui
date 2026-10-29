"""Temperature reuse may span one original scoring job, never separate jobs."""
from contextvars import Context
from pathlib import Path

import pytest

import household_score_report_reuse as reuse
import weather_temperature_source_segments as codec
import weather_temperature_segmented_binding as binding
from test_household_segmented_replay_reuse import retained,profiled


def test_job_acquisition_and_report_share_exact_result_then_discard_it(tmp_path,monkeypatch):
    path,source,expected=retained(tmp_path/'source',monkeypatch)
    original=binding._source_operation
    calls=[]
    def guard():calls.append(1);return 119
    with reuse.job_temperature_reads(guard):
        handle,count=profiled(lambda:binding.read_shared_temperature_source(path.parent,path,guard=lambda:50))
        assert handle==source and count==3
        with reuse._temperature_reads(guard,reuse_job=True):
            value,count=profiled(lambda:binding.replay_shared_temperature_source(handle,guard=lambda:90))
            assert value==expected and count==0
        value,count=profiled(lambda:binding.replay_shared_temperature_source(handle,guard=lambda:90))
        assert value==expected and count==0
    assert calls and binding._source_operation is original
    with reuse.job_temperature_reads(guard):
        value,count=profiled(lambda:binding.replay_shared_temperature_source(handle,guard=lambda:90))
        assert value==expected and count==3


def test_nested_and_foreign_contexts_cannot_borrow_job_hits(tmp_path,monkeypatch):
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    with reuse.job_temperature_reads(lambda:119):
        binding.replay_shared_temperature_source(source,guard=lambda:50)
        with reuse._temperature_reads(lambda:119):
            value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:50))
            assert value==expected and count==3
        with reuse.job_temperature_reads(lambda:119):
            value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:50))
            assert value==expected and count==3
        value,count=profiled(lambda:Context().run(binding.replay_shared_temperature_source,source,guard=lambda:50))
        assert value==expected and count==3
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:50))
        assert value==expected and count==0


@pytest.mark.parametrize('failure',[ValueError,KeyboardInterrupt])
def test_job_refusal_restores_hooks_and_preserves_original_error(tmp_path,monkeypatch,failure):
    _,source,_=retained(tmp_path/'source',monkeypatch)
    original=binding._source_operation
    with pytest.raises(failure,match='original operation refused'),reuse.job_temperature_reads(lambda:119):
        binding.replay_shared_temperature_source(source,guard=lambda:50)
        with reuse._temperature_reads(lambda:119,reuse_job=True):
            raise failure('original operation refused')
    assert binding._source_operation is original
    assert reuse._job_temperature_frame.get() is None


def test_original_job_deadline_does_not_renew_for_report(tmp_path,monkeypatch):
    _,source,_=retained(tmp_path/'source',monkeypatch)
    elapsed=[0]
    def remaining():
        if elapsed[0]>=119:raise ValueError('original job deadline')
        return 119-elapsed[0]
    with pytest.raises(ValueError,match='original job deadline'),reuse.job_temperature_reads(remaining):
        binding.replay_shared_temperature_source(source,guard=lambda:50)
        elapsed[0]=118
        with reuse._temperature_reads(remaining,reuse_job=True):
            elapsed[0]=119
            binding.replay_shared_temperature_source(source,guard=lambda:50)


def test_acquisition_deadline_remains_independent_of_job_deadline(tmp_path,monkeypatch):
    _,source,_=retained(tmp_path/'source',monkeypatch)
    with reuse.job_temperature_reads(lambda:119):
        binding.replay_shared_temperature_source(source,guard=lambda:50)
        with pytest.raises(ValueError):binding.replay_shared_temperature_source(source,guard=lambda:0)


def test_borrowed_report_keeps_its_own_guard_at_each_reuse(tmp_path,monkeypatch):
    _,source,_=retained(tmp_path/'source',monkeypatch)
    refuse=[False]
    def report_guard():
        if refuse[0]:raise ValueError('original report guard refused')
        return 80
    with reuse.job_temperature_reads(lambda:119):
        binding.replay_shared_temperature_source(source,guard=lambda:50)
        with reuse._temperature_reads(report_guard,reuse_job=True):
            refuse[0]=True
            with pytest.raises(ValueError,match='original report guard refused'):
                binding.replay_shared_temperature_source(source,guard=lambda:50)
            refuse[0]=False
    assert reuse._temperature_borrow_guard.get() is None


@pytest.mark.parametrize('limit',['bytes','entries'])
def test_job_reuse_keeps_existing_temperature_capacity(tmp_path,monkeypatch,limit):
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    monkeypatch.setattr(reuse,'MAX_TEMPERATURE_CACHE_BYTES' if limit=='bytes' else 'MAX_TEMPERATURE_CACHE_ENTRIES',1 if limit=='bytes' else 0)
    with reuse.job_temperature_reads(lambda:119):
        binding.replay_shared_temperature_source(source,guard=lambda:50)
        with reuse._temperature_reads(lambda:119,reuse_job=True):
            value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:50))
            assert value==expected and count==3


def test_same_job_still_reads_and_refuses_mutated_originals(tmp_path,monkeypatch):
    _,source,_=retained(tmp_path/'source',monkeypatch)
    with reuse.job_temperature_reads(lambda:119):
        binding.replay_shared_temperature_source(source,guard=lambda:50)
        source._files[-1].write_bytes(source._files[-1].read_bytes()+b' ')
        with reuse._temperature_reads(lambda:119,reuse_job=True),pytest.raises(ValueError):
            binding.replay_shared_temperature_source(source,guard=lambda:50)


def test_production_policy_uses_job_scope_only_with_explicit_original_guard(tmp_path,monkeypatch):
    import household_forecast_score as coordinator
    path,source,expected=retained(tmp_path/'source',monkeypatch)
    monkeypatch.setattr(coordinator,'production_resource_preflight',lambda:None)
    with coordinator.production_score_policy(temperature_guard=lambda:119):
        helper=coordinator._production_report_reuse
        binding.read_shared_temperature_source(path.parent,path,guard=lambda:50)
        assert helper._job_temperature_frame.get() is helper._temperature_frame.get()
        with helper._temperature_reads(lambda:119,reuse_job=True):
            value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:50))
            assert value==expected and count==0
    with coordinator.production_score_policy():
        assert coordinator._production_report_reuse._job_temperature_frame.get() is None
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:50))
        assert value==expected and count==3


@pytest.mark.parametrize('guard',[None,False,42])
def test_job_scope_requires_the_original_guard(guard):
    with pytest.raises(ValueError,match='original job guard'):
        with reuse.job_temperature_reads(guard):pytest.fail('invalid job guard admitted')
