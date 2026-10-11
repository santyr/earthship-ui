"""Original fixed power reads share the base collector's total time budget."""
import importlib
from datetime import timedelta
import pytest
from test_household_power_snapshot import source,inputs,NOW,POWER_EPOCH,AC_EPOCH,build
from test_household_replay import bundle
from test_weather_temperature_history import Connection


def api():return importlib.import_module('household.power_capture')


def fetch(c,kind='power',remaining=lambda:15.):
    return api().fetch_power_receipt(lambda **kwargs:c,kind=kind,start=NOW-timedelta(seconds=120),end=NOW,remaining=remaining)


@pytest.mark.parametrize('kind,item',[('power','Power_Evidence_JSON'),('inverter_ac','Inverter_AC_Evidence_JSON')])
def test_exact_fixed_mapping_stable_readonly_and_bounded_rows(kind,item):
    raw=source(kind)['raw'];c=Connection(rows=[(NOW,raw)])
    assert fetch(c,kind)==(NOW,raw)
    assert c.closed and c.session==dict(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
    assert (item,) in [params for _,params in c.calls]
    assert all(query.startswith(('SET LOCAL','SHOW ','SELECT ')) for query,_ in c.calls)
    assert 'ORDER BY time DESC LIMIT 2' in c.calls[-1][0] and 'octet_length' in c.calls[-1][0]
    assert c.calls[-1][1]==(NOW-timedelta(seconds=120),NOW)


@pytest.mark.parametrize('damage',['mapping','write','isolation','tie','future','size','kind','query','deadline'])
def test_bad_or_unbounded_query_cannot_return_a_source(damage):
    kwargs={'rows':[(NOW,source()['raw'])]};kind='power';remaining=lambda:15.
    if damage=='mapping':kwargs['mapping']=[(1,),(2,)]
    elif damage=='write':kwargs['read_only']='off'
    elif damage=='isolation':kwargs['isolation']='read committed'
    elif damage=='tie':kwargs['rows']*=2
    elif damage=='future':kwargs['rows']=[(NOW+timedelta(seconds=1),source()['raw'])]
    elif damage=='size':kwargs['rows']=[(NOW,'x'*4097)]
    elif damage=='kind':kind='arbitrary_item'
    elif damage=='query':kwargs['fail']='public.items'
    else:remaining=lambda:0.
    c=Connection(**kwargs)
    with pytest.raises(ValueError) as e:fetch(c,kind,remaining)
    assert 'SECRET' not in str(e.value)
    assert c.closed or not c.calls


@pytest.mark.parametrize('raw',[None,'bad newest original'])
def test_newest_barrier_never_falls_back_to_older_valid_value(raw):
    c=Connection(rows=[(NOW,raw),(NOW-timedelta(seconds=1),source()['raw'])])
    assert fetch(c)==(NOW,raw)


def collect(**changes):
    args=dict(base_epochs={'battery_soc':bundle()['sources'][0]['expected_epoch']},base_policy=bundle()['policy'],
        power_epochs={'power':POWER_EPOCH,'inverter_ac':AC_EPOCH},power_policy=inputs()['power_policy'],
        receipt_reader=lambda *a:(NOW,bundle()['sources'][0]['raw']),native_reader=lambda **k:pytest.fail('unexpected native read'),
        power_reader=lambda kind,start,end,remaining:(NOW,source(kind)['raw']),clock=lambda:NOW,monotonic=lambda:0.)
    args.update(changes);return api().collect_power_inputs(**args)


def test_originals_freeze_into_one_clock_and_replay():
    result=collect();assert result['base_inputs']['as_of']==NOW.isoformat()
    assert len(result['power_sources'])==2
    assert build(result)['snapshot']['completeness']['current_energy'] is True


def test_later_final_clock_does_not_renew_source_expiry():
    clocks=iter([NOW,NOW+timedelta(seconds=1),NOW+timedelta(seconds=2)])
    result=collect(clock=lambda:next(clocks))
    assert result['base_inputs']['as_of']==(NOW+timedelta(seconds=2)).isoformat()
    assert build(result)['snapshot']['domains']['energy']['battery_power_w']['evidence']['valid_until']==(NOW+timedelta(seconds=115)).isoformat()


def test_nested_base_and_power_reads_share_one_total_deadline():
    ticks=[0.];budgets=[]
    def base_reader(*args):ticks[0]=10.;return NOW,bundle()['sources'][0]['raw']
    def power_reader(kind,start,end,remaining):
        budgets.append(remaining());ticks[0]=16.;return NOW,source(kind)['raw']
    with pytest.raises(ValueError):collect(receipt_reader=base_reader,power_reader=power_reader,monotonic=lambda:ticks[0])
    assert budgets==[5.]


@pytest.mark.parametrize('damage',['epochs','policy','row_future','row_old','bytes','backward'])
def test_invalid_collection_refuses_without_partial_snapshot(damage):
    changes={}
    if damage=='epochs':changes['power_epochs']={'load':POWER_EPOCH}
    elif damage=='policy':changes['power_policy']={**inputs()['power_policy'],'max_skew_seconds':True}
    elif damage=='row_future':changes['power_reader']=lambda *a:(NOW+timedelta(seconds=1),source()['raw'])
    elif damage=='row_old':changes['power_reader']=lambda *a:(NOW-timedelta(seconds=121),source()['raw'])
    elif damage=='bytes':changes['power_reader']=lambda *a:(NOW,'x'*4097)
    else:
        clocks=iter([NOW,NOW,NOW-timedelta(seconds=1)]);changes['clock']=lambda:next(clocks)
    with pytest.raises(ValueError):collect(**changes)
