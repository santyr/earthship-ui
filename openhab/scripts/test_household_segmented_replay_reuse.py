"""Full retained segmented replay remains byte-bound inside report-local reuse."""
from contextlib import nullcontext
from contextvars import Context
from copy import deepcopy
import cProfile
from pathlib import Path

import pytest

import household_score_report_reuse as reuse
import weather_temperature_source_segments as codec
import weather_temperature_segmented_binding as binding
from thermal_model.replay_budget import capture_source_reads
from test_native_temperature_segmented_integration import retained_inputs


def retained(root,monkeypatch):
    path=retained_inputs(root,{},monkeypatch)
    source=codec.read_shared_temperature_source(path.parent,path)
    assert len(source._files)==4
    return path,source,codec.replay_shared_temperature_source(source)


def profiled(operation):
    profiler=cProfile.Profile()
    profiler.enable()
    try:value=operation()
    finally:profiler.disable()
    count=sum(entry.callcount for entry in profiler.getstats() if entry.code is codec._decode_segment.__code__)
    return value,count


def test_full_first_decode_then_fresh_all_file_reads_without_decoding(tmp_path,monkeypatch):
    path,source,expected=retained(tmp_path/'source',monkeypatch)
    original=codec.replay_shared_temperature_source
    with reuse._temperature_reads(lambda:None),capture_source_reads() as inventory:
        reads=[];record=inventory.record
        def observed(path,raw):
            reads.append(Path(path));return record(path,raw)
        inventory.record=observed
        fresh,first=profiled(lambda:binding.read_shared_temperature_source(path.parent,path,guard=lambda:90))
        assert first==3
        # A cold retained read discards its decoded grid. The first explicit
        # replay must still run completely before it can admit a cached grid.
        value,cold=profiled(lambda:binding.replay_shared_temperature_source(fresh,guard=lambda:90))
        assert value==expected and cold==3
        reads.clear()
        value,later=profiled(lambda:binding.replay_shared_temperature_source(fresh,guard=lambda:90))
        assert value==expected and later==0
        assert set(source._files)<=set(reads)
        reread,again=profiled(lambda:binding.read_shared_temperature_source(path.parent,path,guard=lambda:90))
        assert again==0 and reread._fingerprints==source._fingerprints
        # Caller changes must never alter retained role/grid/receipt values.
        for role,grid in value.items():
            for _,receipt in grid:
                if receipt is not None:receipt['temperatureF']+=20
            grid[0]=(grid[0][0],None)
        assert binding.replay_shared_temperature_source(fresh,guard=lambda:90)==expected
        inventory.verify()
    assert codec.replay_shared_temperature_source is original


def test_original_native_loader_seals_remain_valid_during_replay_reuse(tmp_path,monkeypatch):
    import native_thermal_forecast as forecasts
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    public={name:getattr(codec,name) for name in ('fetch_shared_temperature_source',
        'write_shared_temperature_source','read_shared_temperature_source',
        'replay_shared_temperature_source','shared_temperature_source_files')}
    with reuse._temperature_reads(lambda:None):
        assert forecasts._segmented_helpers()==(binding,codec)
        assert binding.replay_shared_temperature_source(source,guard=lambda:90)==expected
        assert forecasts._segmented_helpers()==(binding,codec)
        assert all(getattr(codec,name) is function for name,function in public.items())
        assert binding.replay_shared_temperature_source(source,guard=lambda:90)==expected


@pytest.mark.parametrize('damage',['manifest','child','replacement'])
def test_changed_original_never_borrows_a_grid(tmp_path,monkeypatch,damage):
    _,source,_=retained(tmp_path/'source',monkeypatch)
    with pytest.raises(ValueError),reuse._temperature_reads(lambda:None),capture_source_reads():
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        target=source._files[0] if damage=='manifest' else source._files[-1]
        if damage=='replacement':
            replacement=target.with_name('replacement')
            replacement.write_bytes(target.read_bytes());replacement.chmod(0o600);replacement.replace(target)
        else:target.write_bytes(target.read_bytes()+b' ')
        binding.replay_shared_temperature_source(source,guard=lambda:90)


def test_callback_mutation_is_refused_before_a_hit_returns(tmp_path,monkeypatch):
    _,source,_=retained(tmp_path/'source',monkeypatch)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        changed=False
        def mutate():
            nonlocal changed
            if not changed:
                changed=True
                source._files[-1].write_bytes(source._files[-1].read_bytes()+b' ')
            return 90
        with pytest.raises(ValueError):binding.replay_shared_temperature_source(source,guard=mutate)


def test_foreign_context_and_distinct_source_do_full_original_work(tmp_path,monkeypatch):
    _,source,expected=retained(tmp_path/'one',monkeypatch)
    _,other,other_expected=retained(tmp_path/'two',monkeypatch)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        value,count=profiled(lambda:Context().run(binding.replay_shared_temperature_source,source,guard=lambda:90))
        assert value==expected and count==3
        value,count=profiled(lambda:binding.replay_shared_temperature_source(other,guard=lambda:90))
        assert value==other_expected and count==3


@pytest.mark.parametrize('limit',['bytes','entries'])
def test_existing_query_limits_disable_segmented_reuse(tmp_path,monkeypatch,limit):
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    monkeypatch.setattr(reuse,'MAX_TEMPERATURE_CACHE_BYTES' if limit=='bytes' else 'MAX_TEMPERATURE_CACHE_ENTRIES',1 if limit=='bytes' else 0)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:90))
        assert value==expected and count==3


@pytest.mark.parametrize('kind',['unretained','subclass'])
def test_unknown_handle_uses_original_replay(tmp_path,monkeypatch,kind):
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    if kind=='unretained':
        source=codec.SharedTemperatureSource(source.manifest_bytes,
            _chunks=tuple(p.read_bytes() for p in source._files[1:]))
    else:
        class OtherSource(codec.SharedTemperatureSource):pass
        source=OtherSource(source.manifest_bytes,_files=source._files,_fingerprints=source._fingerprints)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:90))
        assert value==expected and count==3


def test_changed_codec_code_uses_original_and_does_not_poison_cache(tmp_path,monkeypatch):
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        original=codec._advance.__code__
        try:
            codec._advance.__code__=original.replace()
            value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:90))
            assert value==expected and count==3
        finally:codec._advance.__code__=original
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:90))
        assert value==expected and count==0


@pytest.mark.parametrize('failure',[ValueError,KeyboardInterrupt])
def test_failed_replay_is_not_cached_and_hooks_restore(tmp_path,monkeypatch,failure):
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    original=codec.replay_shared_temperature_source
    with reuse._temperature_reads(lambda:None):
        calls=0
        def refuse():
            nonlocal calls
            calls+=1
            if calls>=50:raise failure('caller refused after partial work')
        profiler=cProfile.Profile()
        with pytest.raises(failure):
            profiler.enable()
            try:binding.replay_shared_temperature_source(source,guard=refuse)
            finally:profiler.disable()
        assert any(entry.code is codec._decode_segment.__code__ for entry in profiler.getstats())
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:90))
        assert value==expected and count==3
    assert codec.replay_shared_temperature_source is original
    with pytest.raises(failure),reuse._temperature_reads(lambda:None):raise failure('cancel report')
    assert codec.replay_shared_temperature_source is original


def test_nested_context_does_not_borrow_parent_and_restores_it(tmp_path,monkeypatch):
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        parent=codec.replay_shared_temperature_source
        with reuse._temperature_reads(lambda:None):
            value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:90))
            assert value==expected and count==3
        assert codec.replay_shared_temperature_source is parent
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:90))
        assert value==expected and count==0


@pytest.mark.parametrize('remaining',[0,-1,False,float('nan')])
def test_original_numeric_deadline_refusals_apply_to_warm_hits(tmp_path,monkeypatch,remaining):
    _,source,_=retained(tmp_path/'source',monkeypatch)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        with pytest.raises(ValueError):binding.replay_shared_temperature_source(source,guard=lambda:remaining)


def test_none_guard_and_unknown_codec_pin_preserve_original_behavior(tmp_path,monkeypatch):
    _,source,expected=retained(tmp_path/'source',monkeypatch)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:None)
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:None))
        assert value==expected and count==0
    monkeypatch.setattr(reuse,'SEGMENTED_CODEC_SHA256','0'*64)
    with reuse._temperature_reads(lambda:None):
        binding.replay_shared_temperature_source(source,guard=lambda:90)
        value,count=profiled(lambda:binding.replay_shared_temperature_source(source,guard=lambda:90))
        assert value==expected and count==3
