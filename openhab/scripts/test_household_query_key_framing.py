"""Complete raw-query keys use injective framing and isolated plain containers."""
from copy import deepcopy
import pytest
import household_score_report_reuse as reuse
import weather_temperature_sources as sources
from test_weather_temperature_sources import case


def key(packet):return reuse._temperature_query_key(packet)


def test_known_packet_copy_preserves_every_value_and_isolates_mutable_inputs(tmp_path,monkeypatch):
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch));before=deepcopy(packet)
    digest,saved=key(packet)
    assert len(digest)==32 and saved==before
    packet['policy']['minimum_f']+=1;packet['targets'][0]='changed';packet['native_rows'][0][0]='changed';packet['native_rows'][0][1]='changed'
    assert saved==before
    saved['policy']['maximum_f']-=1;saved['targets'].append('other');saved['native_rows'][0][1]='other'
    assert packet['policy']!=saved['policy'] and packet['targets']!=saved['targets'] and packet['native_rows']!=saved['native_rows']


@pytest.mark.parametrize('field',['stream','sensor_epoch','targets','assessed_at','history_start','release_authority','model','sensor_id','minimum_f','maximum_f','validity_seconds','stored_at','raw','row_count','row_order'])
def test_every_original_metadata_policy_clock_and_raw_row_changes_key(tmp_path,monkeypatch,field):
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch));changed=deepcopy(packet)
    if field in ('model','sensor_id','minimum_f','maximum_f','validity_seconds'):
        changed['policy'][field]=changed['policy'][field]+'x' if field=='model' else changed['policy'][field]+1
    elif field=='targets':changed[field][0]+='x'
    elif field=='release_authority':changed[field]=True
    elif field=='stored_at':changed['native_rows'][0][0]+='x'
    elif field=='raw':changed['native_rows'][0][1]+=' '
    elif field=='row_count':changed['native_rows'].append(changed['native_rows'][0].copy())
    elif field=='row_order':changed['native_rows'].reverse()
    else:changed[field]+='x'
    assert key(packet)[0]!=key(changed)[0]


def test_framing_separates_boundaries_null_empty_unicode_order_and_scalar_types(tmp_path,monkeypatch):
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch));variants=[]
    for rows in ([['a','bc']],[['ab','c']],[['a',None]],[['a','']],[['a','null']],[['a','\0']],[['a','雪☀']],[['a','é']],[['a','e\u0301']],[['a','bc'],['d','e']],[['a','b'],['cd','e']],[['d','e'],['a','bc']]):
        changed=deepcopy(packet);changed['native_rows']=[r.copy() for r in rows];variants.append(changed)
    for minimum in (-0.0,0.0,0,False):
        changed=deepcopy(packet);changed['policy']['minimum_f']=minimum;variants.append(changed)
    digests=[key(v)[0] for v in variants]
    assert len(set(digests))==len(variants),'a field, type, length, order or exact raw byte sequence was omitted'
    reordered=dict(reversed(list(packet.items())));reordered['policy']=dict(reversed(list(packet['policy'].items())))
    assert key(reordered)[0]==key(packet)[0],'dictionary insertion order must not change complete canonical metadata'


@pytest.mark.parametrize('damage',['extra_field','schema','tuple_rows','row_alias','cycle','policy_object','raw_subclass'])
def test_unknown_shapes_aliases_cycles_and_objects_fall_back_without_copy_hooks(tmp_path,monkeypatch,damage):
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch))
    class Forbidden:
        def __deepcopy__(self,*a):raise AssertionError('custom copy executed')
        def __reduce__(self):raise AssertionError('custom reducer executed')
    class Raw(str):
        def encode(self,*a,**kw):raise AssertionError('custom string method executed')
    if damage=='extra_field':packet['extra']=Forbidden()
    elif damage=='schema':packet['schema']='unknown source schema'
    elif damage=='tuple_rows':packet['native_rows']=tuple(packet['native_rows'])
    elif damage=='row_alias':packet['native_rows'].append(packet['native_rows'][0])
    elif damage=='cycle':packet['native_rows'][0][1]=packet
    elif damage=='policy_object':packet['policy']['minimum_f']=Forbidden()
    else:packet['native_rows'][0][1]=Raw(packet['native_rows'][0][1])
    with pytest.raises((TypeError,ValueError)):key(packet)


def test_unknown_packet_uses_original_query_without_custom_deepcopy(tmp_path,monkeypatch):
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch))
    class Unknown:
        def __deepcopy__(self,*a):raise AssertionError('custom copy executed')
    packet['policy']['minimum_f']=Unknown()
    with reuse._temperature_reads(lambda:None):
        with pytest.raises(ValueError):sources.replay_temperature_source(packet)


def test_query_uses_complete_input_snapshot_when_guard_mutates_caller_packet(tmp_path,monkeypatch):
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch));original=sources.replay_temperature_source
    expected=original(deepcopy(packet));armed=[False]
    def guard():
        if armed[0]:packet['policy']['maximum_f']=69
    with reuse._temperature_reads(guard):
        armed[0]=True
        assert sources.replay_temperature_source(packet)==expected
        assert sources.replay_temperature_source(packet)==original(deepcopy(packet))
        assert all(receipt is None for _,receipt in sources.replay_temperature_source(packet))


def test_framed_query_keeps_same_bounded_entry_eviction(tmp_path,monkeypatch):
    packet=sources.build_temperature_source(**case(tmp_path,monkeypatch));other=deepcopy(packet);other['policy']['sensor_id']+=1
    calls=[];select=sources.select_temperature_grid_v2
    def counted(*a,**kw):calls.append(True);return select(*a,**kw)
    monkeypatch.setattr(sources,'select_temperature_grid_v2',counted);monkeypatch.setattr(reuse,'MAX_TEMPERATURE_CACHE_ENTRIES',1)
    with reuse._temperature_reads(lambda:None):
        sources.replay_temperature_source(packet);sources.replay_temperature_source(packet);assert len(calls)==1
        sources.replay_temperature_source(other);sources.replay_temperature_source(packet);assert len(calls)==3
