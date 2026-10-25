"""Report-local pure replay reuse preserves strict barriers and caller isolation."""
from copy import deepcopy
from contextvars import Context
from dataclasses import replace
from datetime import timedelta
import pytest
import household_score_report_reuse as reuse
import weather_temperature_reader as reader
import weather_temperature_sources as sources
from test_weather_temperature_reader import AT, raw, POLICY
from test_weather_temperature_sources import case


def test_snapshot_reuse_is_local_copied_and_keyed_by_every_input(monkeypatch):
    calls=[];parse=reader._object
    def counted(pairs):calls.append(1);return parse(pairs)
    monkeypatch.setattr(reader,'_object',counted)
    packet=raw();original=reader._snapshot
    with reuse._temperature_reads(lambda:None):
        value=reader._snapshot(packet,AT,'indoor',POLICY)
        n=len(calls);value[1]['temperatureF']=0
        assert reader._snapshot(packet,AT,'indoor',POLICY)[1]['temperatureF']==70
        assert len(calls)==n
        reader._snapshot(packet,AT+timedelta(seconds=1),'indoor',POLICY)
        reader._snapshot(packet,AT,'other',POLICY)
        reader._snapshot(packet,AT,'indoor',replace(POLICY,minimum_f=1))
        reader._snapshot(packet.replace('70','71'),AT,'indoor',POLICY)
        assert len(calls)>n
        n=len(calls)
        Context().run(reader._snapshot,packet,AT,'indoor',POLICY)
        assert len(calls)>n
    assert reader._snapshot is original
    n=len(calls)
    with reuse._temperature_reads(lambda:None):reader._snapshot(packet,AT,'indoor',POLICY)
    assert len(calls)>n


@pytest.mark.parametrize('damage',['null','conflict','epoch','future','expired','boundary','stored','stream','policy','authority','assessment','target'])
def test_complete_packet_reuse_matches_original_barriers(tmp_path,monkeypatch,damage):
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch))
    changed=deepcopy(packet)
    if damage=='null':changed['native_rows'][0][1]=None
    elif damage=='conflict':changed['native_rows'].insert(1,[changed['native_rows'][0][0],changed['native_rows'][0][1].replace('70','71')])
    elif damage=='epoch':changed['sensor_epoch']='invalid'
    elif damage=='future':changed['native_rows'][0][1]=changed['native_rows'][0][1].replace('12:00:00','12:00:01')
    elif damage=='expired':changed['targets'][0]=(AT+timedelta(seconds=300)).isoformat();changed['history_start']=AT.isoformat()
    elif damage=='boundary':changed['targets'][0]=(AT+timedelta(seconds=90)).isoformat();changed['history_start']=(AT-timedelta(seconds=210)).isoformat()
    elif damage=='stored':changed['native_rows'][0][0]=(AT+timedelta(seconds=1)).isoformat()
    elif damage=='stream':changed['stream']='outdoor'
    elif damage=='policy':changed['policy']['maximum_f']=69
    elif damage=='authority':changed['release_authority']=True
    elif damage=='assessment':changed['assessed_at']=AT.isoformat()
    else:changed['targets'][0]=(AT+timedelta(seconds=61)).isoformat();changed['history_start']=(AT-timedelta(seconds=239)).isoformat()
    original=sources.replay_temperature_source
    try:expected=original(changed);error=None
    except Exception as exc:error=type(exc)
    with reuse._temperature_reads(lambda:None):
        first=sources.replay_temperature_source(packet);first[0][1]['temperatureF']=0
        assert sources.replay_temperature_source(packet)[0][1]['temperatureF']==70
        if error:
            with pytest.raises(error):sources.replay_temperature_source(changed)
        else:assert sources.replay_temperature_source(changed)==expected
    assert sources.replay_temperature_source is original


def test_nested_deadline_and_cancellation_restore_hooks(monkeypatch):
    original=reader._snapshot;query=sources.replay_temperature_source
    for failure in (TimeoutError,KeyboardInterrupt):
        with pytest.raises(failure):
            with reuse._temperature_reads(lambda:None):
                outer=reader._snapshot
                with reuse._temperature_reads(lambda:None):
                    assert reader._snapshot(raw(),AT,'indoor',POLICY)[1]['temperatureF']==70
                assert reader._snapshot is outer
                raise failure()
        assert reader._snapshot is original and sources.replay_temperature_source is query
    with pytest.raises(TimeoutError):
        with reuse._temperature_reads(lambda:(_ for _ in ()).throw(TimeoutError())):
            reader._snapshot(raw(),AT,'indoor',POLICY)
    assert reader._snapshot is original


def test_bounded_eviction_and_unknown_sources_do_not_reuse(monkeypatch):
    calls=[];parse=reader._object
    def counted(pairs):calls.append(1);return parse(pairs)
    monkeypatch.setattr(reader,'_object',counted)
    monkeypatch.setattr(reuse,'MAX_TEMPERATURE_CACHE_ENTRIES',1)
    with reuse._temperature_reads(lambda:None):
        reader._snapshot(raw(),AT,'indoor',POLICY)
        reader._snapshot(raw(value='71'),AT,'indoor',POLICY)
        n=len(calls);reader._snapshot(raw(),AT,'indoor',POLICY)
        assert len(calls)>n
    monkeypatch.setattr(reuse,'TEMPERATURE_SOURCE_SHA256',{})
    with reuse._temperature_reads(lambda:None):assert reader._snapshot.__code__.co_filename==str(__import__('pathlib').Path(reader.__file__))


def test_original_imported_query_alias_reuses_whole_packet_and_restores(tmp_path,monkeypatch):
    import thermal_model.installed_shade_raw_score_sources as raw_sources
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch))
    calls=[];select=sources.select_temperature_grid_v2
    def counted(*a,**kw):calls.append(1);return select(*a,**kw)
    monkeypatch.setattr(sources,'select_temperature_grid_v2',counted)
    original=raw_sources.replay_temperature_source
    with reuse._temperature_reads(lambda:None):
        assert raw_sources.replay_temperature_source(packet)[0][1]['temperatureF']==70
        raw_sources.replay_temperature_source(deepcopy(packet))
        assert len(calls)==1,'a fitted caller imported before the report repeated pure raw replay'
    assert raw_sources.replay_temperature_source is original


def test_overlapping_report_snapshot_working_set_is_not_reparsed(monkeypatch):
    calls=[];parse=reader._object
    def counted(pairs):calls.append(1);return parse(pairs)
    monkeypatch.setattr(reader,'_object',counted)
    rows=[(raw(offset=i),AT+timedelta(seconds=i)) for i in range(5000)]
    with reuse._temperature_reads(lambda:None):
        for packet,at in rows:reader._snapshot(packet,at,'indoor',POLICY)
        parsed=len(calls)
        for packet,at in rows:reader._snapshot(packet,at,'indoor',POLICY)
        assert len(calls)==parsed,'overlapping retained windows lost their complete normalized working set'


@pytest.mark.parametrize('damage',['replace','symlink','permission','bytes'])
def test_final_pure_helper_readback_refuses_source_mutation(tmp_path,monkeypatch,damage):
    # Redirect metadata to independent exact source copies; originals stay
    # untouched. The actual stable-byte/ownership/inode readers still execute.
    import weather_temperature_evidence as evidence
    import thermal_model.installed_shade_raw_score_sources as raw_sources
    from pathlib import Path
    for module in (reader,sources,evidence,raw_sources):
        path=tmp_path/(module.__name__+'.py');path.write_bytes(Path(module.__file__).read_bytes());path.chmod(0o644)
        monkeypatch.setattr(module,'__file__',str(path))
    # Code must match the selected source path as it does in a frozen stage.
    for module,name in ((reader,'_snapshot'),(sources,'replay_temperature_source')):
        fn=getattr(module,name);monkeypatch.setattr(fn,'__code__',fn.__code__.replace(co_filename=module.__file__))
    target=Path(reader.__file__);original=reader._snapshot;query=sources.replay_temperature_source
    with pytest.raises(ValueError):
        with reuse._temperature_reads(lambda:None):
            assert reader._snapshot(raw(),AT,'indoor',POLICY)[1]['temperatureF']==70
            if damage=='replace':
                replacement=tmp_path/'replacement';replacement.write_bytes(target.read_bytes());replacement.chmod(0o644);replacement.replace(target)
            elif damage=='symlink':
                replacement=tmp_path/'replacement';replacement.write_bytes(target.read_bytes());replacement.chmod(0o644);target.unlink();target.symlink_to(replacement)
            elif damage=='permission':target.chmod(0o666)
            else:target.write_bytes(target.read_bytes()+b' ')
    assert reader._snapshot is original and sources.replay_temperature_source is query
