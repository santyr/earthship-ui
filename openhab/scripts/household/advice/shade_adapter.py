"""Bridge the existing qualified OpenHAB/JDBC history into advisory observations.

No transport, subscriptions or commands. Missing native motion/origin remain
unknown; adapter reception is labeled separately from a native source clock.
"""
from datetime import timedelta
from ..codec import canonical,identity
from ..evidence import utc
from thermal_model.shade_observations import qualified_shade_intervals,MAX_ROWS,MAX_WINDOW
from thermal_model.shade_history import fetch_shade_intervals
from .shade_state import normalize_event


def _retain_intervals(store,*,mapping,intervals,start,end):
    if mapping['convention']!='closed_100' or mapping['native_max']!=100:raise ValueError('existing OpenHAB reader requires native percent-closed convention')
    known={e['event_id'] for e in store.originals() if e['shade_id']==mapping['shade_id'] and e['epoch']==mapping['epoch']};last_end=None
    for interval in intervals:
        acquired=interval.report_received_at;available=max(interval.stored_at,acquired)
        event_id=identity([mapping['epoch'],acquired.isoformat(),interval.percent_closed])
        if last_end is not None and interval.start>last_end:
            gap_id=identity(['coverage_gap',mapping['epoch'],last_end.isoformat()])
            if gap_id not in known:
                store.ingest(normalize_event(mapping,dict(device_id=mapping['device_id'],source=mapping['source'],event_id=gap_id,sequence=int(last_end.timestamp()*1000000),native_position=None,native_target=None,
                    movement='unknown',origin='unknown',observed_at=last_end.isoformat(),received_at=last_end.isoformat(),available_at=last_end.isoformat(),online=None,time_basis='adapter_report_reception')))
        if event_id not in known:
            store.ingest(normalize_event(mapping,dict(device_id=mapping['device_id'],source=mapping['source'],event_id=event_id,sequence=int(acquired.timestamp()*1000000),native_position=interval.percent_closed,native_target=None,
                movement='unknown',origin='unknown',observed_at=acquired.isoformat(),received_at=available.isoformat(),available_at=available.isoformat(),online=True,time_basis='adapter_report_reception')))
            known.add(event_id)
        last_end=interval.end
    if intervals and last_end<end:
        gap_id=identity(['coverage_gap',mapping['epoch'],last_end.isoformat()])
        if gap_id not in known:store.ingest(normalize_event(mapping,dict(device_id=mapping['device_id'],source=mapping['source'],event_id=gap_id,sequence=int(last_end.timestamp()*1000000),native_position=None,native_target=None,
            movement='unknown',origin='unknown',observed_at=last_end.isoformat(),received_at=last_end.isoformat(),available_at=last_end.isoformat(),online=None,time_basis='adapter_report_reception')))


def ingest_joined_rows(store,*,mapping,rows,start,end,as_of):
    start,end,as_of=map(utc,(start,end,as_of))
    if not start<end<=as_of or end-start>MAX_WINDOW:raise ValueError('bounded as-of shade history required')
    if not isinstance(rows,(list,tuple)) or len(rows)>MAX_ROWS:raise ValueError('bounded original joined rows required')
    intervals=qualified_shade_intervals(rows,start=start,end=end)
    return _retain_intervals(store,mapping=mapping,intervals=intervals,start=start,end=end)


def ingest_jdbc_history(store,connection_factory,*,mapping,items,start,end,as_of):
    intervals=fetch_shade_intervals(connection_factory,items=items,start=start,end=end,as_of=as_of)
    return _retain_intervals(store,mapping=mapping,intervals=intervals,start=start,end=end)
