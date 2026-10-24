"""Eight-role source-only v2 acquisition; fake cursor never opens a household DSN."""
from datetime import timedelta
import json

import pytest

from test_thermal_shade_history import Connection
from test_thermal_shade_observations_v2 import T, PROFILE, state, service, bridge

try:
    from thermal_model import shade_history_v2 as reader
except ImportError:
    reader = None

ROLES = ('diagnostic_state','availability','scalar_position','service_availability',
         'bridge_availability','service_state','bridge_state','provider_status')
ITEMS = {role:f'Synthetic_Shade_01_{role}' for role in ROLES}
IDS = {name:700+index for index,name in enumerate(ITEMS.values())}


def connection(**changes):
    carries = {IDS[ITEMS[role]]:(T-timedelta(seconds=1),value) for role,value in (
        ('availability','ON'),('service_availability','ON'),('bridge_availability','ON'),
        ('provider_status','ONLINE'),('service_state',json.dumps(service())),
        ('bridge_state',json.dumps(bridge())))}
    rows = {IDS[ITEMS['diagnostic_state']]:[
        (T+timedelta(seconds=2),json.dumps(state(T+timedelta(seconds=2),25,'20261024180002000'))),
        (T+timedelta(seconds=4),json.dumps(state(T+timedelta(seconds=4),50,'20261024180004000')))],
        IDS[ITEMS['scalar_position']]:[(T+timedelta(seconds=1),'25'),(T+timedelta(seconds=5),'50')]}
    return Connection(**{'mappings':IDS,'carries':carries,'rows':rows,**changes})


def fetch(conn, **changes):
    assert reader is not None, 'Separate v2 SQL history reader required'
    return reader.fetch_shade_intervals_v2(lambda:conn,items=ITEMS,profile=PROFILE,
        start=T,end=T+timedelta(seconds=10),as_of=T+timedelta(seconds=10),**changes)


def test_separate_eight_role_read_only_snapshot_keeps_partial_positions():
    conn = connection()
    history = fetch(conn)
    assert [(part.start,part.end,part.percent_open) for part in history.intervals] == [
        (T+timedelta(seconds=2),T+timedelta(seconds=4),75),
        (T+timedelta(seconds=5),T+timedelta(seconds=10),50)]
    assert [part.percent_closed for part in history.observations] == [25,50]
    assert conn.closed and conn.session == {
        'readonly':True,'autocommit':False,'isolation_level':'REPEATABLE READ'}
    assert [params[0] for query,params in conn.calls if 'public.items' in query] == list(ITEMS.values())
    assert all(query.startswith(('SET LOCAL','SHOW ','SELECT ')) for query,_ in conn.calls)
    assert sum('LIMIT 10001' in query for query,_ in conn.calls) == 8
    assert sum('octet_length(value::text) <= 8192' in query for query,_ in conn.calls) == 16


@pytest.mark.parametrize('role',ROLES)
def test_missing_or_ambiguous_exact_role_mapping_refuses_whole_acquisition(role):
    assert reader is not None
    for invalid in (None,[(800,),(801,)],'800'):
        conn = connection(mappings={**IDS,ITEMS[role]:invalid})
        with pytest.raises(reader.ShadeHistoryV2Unavailable,match='^v2 shade history unavailable$'):
            fetch(conn)
        assert conn.closed
        assert not any('FROM public.item0' in query for query,_ in conn.calls)


def test_missing_provider_mapping_or_commission_record_fails_before_connecting():
    assert reader is not None
    def forbidden(): pytest.fail('invalid profile/mapping attempted SQL')
    for changes in ({'items':{k:v for k,v in ITEMS.items() if k!='provider_status'}},
        {'items':{**ITEMS,'provider_status':ITEMS['availability']}},
        {'profile':{k:v for k,v in PROFILE.items() if k!='commissioning_ref'}},
        {'profile':{**PROFILE,'source_identity_sha256':'0'*64}},
        {'as_of':T+timedelta(seconds=9)}):
        options={'items':ITEMS,'profile':PROFILE,'start':T,'end':T+timedelta(seconds=10),
                 'as_of':T+timedelta(seconds=10),**changes}
        with pytest.raises(reader.ShadeHistoryV2Unavailable): reader.fetch_shade_intervals_v2(forbidden,**options)


@pytest.mark.parametrize('changes',[{'read_only':'off'},{'isolation':'read committed'},
    {'fail':'public.items'},{'fail':'LIMIT 10001'},
    {'rows':{700:[(T+timedelta(seconds=2),'{}')]*10001}},
    {'rows':{700:[(T+timedelta(seconds=2),'{}')]*2}},
    {'rows':{700:[(T+timedelta(seconds=10),'{}')]}}])
def test_invalid_transport_duplicates_or_bounds_never_return_partial_history(changes):
    assert reader is not None
    conn = connection(**changes)
    with pytest.raises(reader.ShadeHistoryV2Unavailable,match='^v2 shade history unavailable$'): fetch(conn)
    assert conn.closed


def test_missing_provider_history_keeps_observation_but_withholds_all_intervals():
    conn=connection()
    del conn.carries[IDS[ITEMS['provider_status']]]
    history=fetch(conn)
    assert not history.intervals
    assert [part.percent_closed for part in history.observations] == [25,50]
