"""Matched future AC-energy observations keep invalid rows and missing duration."""
from datetime import timedelta
from test_household_ac_load_sources import START,raw
from test_household_ac_load_transport import Connection
from household.codec import identity
import importlib
import pytest

END=START+timedelta(hours=1)


def source(rows=None):
    api=importlib.import_module('household_ac_load_window')
    if rows is None:rows=[(START+timedelta(seconds=s),raw(START+timedelta(seconds=s),i+1)) for i,s in enumerate((0,5,10))]+[(START+timedelta(seconds=15),'invalid')]
    value=api.build_hour_source(rows=rows,start=START,end=END,requested_at=END+timedelta(minutes=5),received_at=END+timedelta(minutes=5,seconds=1),item_id=613)
    return api,value


def test_hour_outcome_retains_barriers_and_reports_known_energy_without_imputing_missing():
    api,value=source();out=api.account_hour(value,assessed_at=END+timedelta(minutes=6),start=START,end=END)
    assert out['known_ac_kwh']==pytest.approx(15/3600) and out['covered_seconds']==15 and out['coverage']==15/3600
    assert out['missing_seconds']==3585 and out['status']=='accounted' and value['rows'][-1][1]=='invalid'
    assert out['source_sha256']==value['source_sha256']


def test_sequence_ambiguity_withholds_outcome_instead_of_repair():
    api,value=source([(START,raw(START,2)),(START+timedelta(seconds=5),raw(START+timedelta(seconds=5),1))])
    out=api.account_hour(value,assessed_at=END+timedelta(minutes=6),start=START,end=END)
    assert out['status']=='unavailable' and out['known_ac_kwh'] is None and out['reason']=='ambiguous_source_sequence'


@pytest.mark.parametrize('damage',['future','wrong_target','hash','outside','duplicate','long_query','oversized'])
def test_hour_source_bounds_maturity_and_original_identity_refuse(damage):
    api,value=source();end=END;assessed=END+timedelta(minutes=6)
    if damage=='future':assessed=END+timedelta(minutes=4)
    elif damage=='wrong_target':end+=timedelta(hours=1)
    elif damage=='hash':value['source_sha256']='f'*64
    elif damage=='outside':value['rows'][0][0]=(START-timedelta(seconds=121)).isoformat()
    elif damage=='duplicate':value['rows'][1][0]=value['rows'][0][0]
    elif damage=='long_query':value['received_at']=(END+timedelta(minutes=6)).isoformat()
    else:value['rows'][0][1]='x'*4097
    if damage!='hash':value['source_sha256']=identity({k:v for k,v in value.items() if k!='source_sha256'})
    with pytest.raises(ValueError):api.account_hour(value,assessed_at=assessed,start=START,end=end)


def test_hour_capture_uses_fixed_bounded_readonly_query_and_closes():
    api=importlib.import_module('household_ac_load_window');connection=Connection();times=iter([END+timedelta(minutes=5),END+timedelta(minutes=5,seconds=1)])
    value=api.capture_hour(connect=lambda **kw:connection,start=START,end=END,clock=lambda:next(times),remaining=lambda:10.)
    assert value['rows'][0][1]==raw(START) and connection.closed and connection.session['readonly'] is True
    query,args=next((q,a) for q,a in connection.calls if 'FROM public.item0613' in q)
    assert 'LIMIT 2001' in query and args==(START-timedelta(seconds=120),END)
    assert all(q.split()[0] in {'SELECT','SHOW','SET'} for q,_ in connection.calls)
