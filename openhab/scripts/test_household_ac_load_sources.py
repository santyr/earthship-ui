"""Original AC receipts remain barriers and retain bounded source lineage."""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from copy import deepcopy
import importlib,json
import pytest

ZONE=ZoneInfo('America/Denver');START=datetime(2026,10,1,tzinfo=ZONE).astimezone(timezone.utc)
EPOCH='00000000-0000-4000-8000-000000000001'


def raw(at,sequence=1):
    stamp=int(at.timestamp()*1000)
    return json.dumps(dict(version=1,basis='inverter_output',streamEpoch=EPOCH,sequence=sequence,recordedAt=stamp,
        fields={'inverter.ac_output_w':dict(status='valid',reason='ok',observedAt=stamp,validUntil=stamp+30000,watts=1000)}))


def packet(*,rows=None,start=START,end=None):
    api=importlib.import_module('household_ac_load_sources');end=end or start+timedelta(days=1)
    if rows is None:rows=[(start+timedelta(seconds=s),raw(start+timedelta(seconds=s),i+1)) for i,s in enumerate((0,5,10))]+[(start+timedelta(seconds=15),'not-json')]
    return api,api.build_day_source(rows=rows,start=start,end=end,requested_at=end+timedelta(seconds=1),received_at=end+timedelta(seconds=2),item_id=613)


def test_day_accounting_uses_qualified_intervals_and_retains_invalid_barriers():
    api,source=packet();original=deepcopy(source);result=api.summarize_day(source)
    assert source==original and result['status']=='accounted' and len(result['hourly_rows'])==24
    first=result['hourly_rows'][0]
    assert first['covered_seconds']==15 and first['known_ac_kwh']==pytest.approx(15/3600)
    assert result['hourly_rows'][1]['covered_seconds']==0 and result['hourly_rows'][1]['known_ac_kwh']==0
    assert result['source_sha256']==source['source_sha256'] and source['rows'][-1][1]=='not-json'


def test_ambiguous_source_sequence_withholds_day_instead_of_reordering_or_repair():
    at=START;api,source=packet(rows=[(at,raw(at,2)),(at+timedelta(seconds=5),raw(at+timedelta(seconds=5),1))])
    result=api.summarize_day(source)
    assert result['status']=='unavailable' and result['reason']=='ambiguous_source_sequence' and result['hourly_rows']==[]


@pytest.mark.parametrize('damage',['sha','identity','future_query','duplicate_time','long_request','out_of_window','oversize'])
def test_original_source_integrity_clocks_and_bounds_refuse(damage):
    api,source=packet()
    if damage=='sha':source['source_sha256']='f'*64
    elif damage=='identity':source['source_identity']='household-guessed-load'
    elif damage=='future_query':source['requested_at']=(START+timedelta(hours=23)).isoformat()
    elif damage=='duplicate_time':source['rows'][1][0]=source['rows'][0][0]
    elif damage=='long_request':source['received_at']=(START+timedelta(days=1,seconds=30)).isoformat()
    elif damage=='out_of_window':source['rows'][0][0]=(START-timedelta(seconds=121)).isoformat()
    else:source['rows'][0][1]='x'*4097
    # Resealing cannot legitimize a contradictory original wrapper.
    if damage!='sha':
        from household.codec import identity
        source['source_sha256']=identity({k:v for k,v in source.items() if k!='source_sha256'})
    with pytest.raises(ValueError):api.summarize_day(source)


@pytest.mark.parametrize('month,day,count',[(3,8,23),(11,1,25)])
def test_completed_local_days_preserve_dst_elapsed_hours(month,day,count):
    local=datetime(2026,month,day,tzinfo=ZONE);start=local.astimezone(timezone.utc);end=(local+timedelta(days=1)).astimezone(timezone.utc)
    api,source=packet(rows=[(start,raw(start))],start=start,end=end);result=api.summarize_day(source)
    assert len(result['hourly_rows'])==count and result['hourly_rows'][-1]['end']==end.isoformat()
