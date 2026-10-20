"""Observed durations require contact evidence and communication supervision."""
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from services.observations.contract import instant


def summarize(history,registry,now,timezone_name='America/Denver'):
    zone=ZoneInfo(timezone_name);daily=defaultdict(lambda:dict(open_seconds=0,observed_seconds=0))
    recent=[];by_sensor=defaultdict(list);counts=defaultdict(int);barriers=defaultdict(list)
    communication=defaultdict(list)
    for row in history:
        device=registry.devices.get(row['sensor_id'])
        if device is None or row['hardware_epoch']!=device['hardware_epoch']:continue
        received=instant(row['received_at'])
        if received>now:continue
        if row['event_type']=='quality_barrier':barriers[row['sensor_id']].append(row)
        if row['event_type'] in ('opened','closed','tamper','tamper_cleared') or row['event_type'].startswith('communication_'):
            recent.append({k:row.get(k) for k in ('sensor_id','event_type','observed_at','received_at','continuity','synthetic')})
        # Every decoded packet proves communication at receipt, including status
        # and archived datalog packets. Snapshot health events prove no reception.
        # Multiple decoded records from one packet are unioned below.
        if row.get('raw_id') and row.get('source_epoch') is not None:
            key=(row['sensor_id'],row['source_epoch'])
            communication[key].append((received,received+timedelta(seconds=device['communication_stale_seconds'])))
        if row.get('historical') or row.get('contact_state') not in ('OPEN','CLOSED'):continue
        by_sensor[row['sensor_id']].append(row);counts[row['sensor_id']]+=1
    for key,intervals in communication.items():
        merged=[]
        for start,end in sorted(intervals):
            if merged and start<=merged[-1][1]:
                merged[-1]=(merged[-1][0],max(merged[-1][1],end))
            else:merged.append((start,end))
        communication[key]=merged
    for sensor_id,rows in by_sensor.items():
        rows.sort(key=lambda r:(instant(r['observed_at']),r.get('journal_sequence',0)))
        for i,row in enumerate(rows):
            observed=instant(row['observed_at'])
            start=max(observed,instant(row['received_at']));end=min(now,instant(row['valid_until']))
            # A barrier withdraws evidence already held at that journal position.
            # It must not withdraw a later recovery whose device clock is older
            # than the fault, or whose timestamp happens to equal the fault.
            applicable=[]
            for barrier in barriers[sensor_id]:
                if (barrier.get('reason')=='missing_frames' and row.get('continuity')=='gap' and
                    barrier['received_at']==row['received_at']):continue
                after=(barrier['journal_sequence']>row['journal_sequence'] if
                    'journal_sequence' in barrier and 'journal_sequence' in row else
                    instant(barrier['received_at'])>=instant(row['received_at']))
                if after:applicable.append(instant(barrier['observed_at']))
            if i+1<len(rows):
                following=rows[i+1];end=min(end,instant(following['observed_at']))
                if following.get('continuity')=='gap' and not any(observed<=b<=end for b in applicable):end=start
            next_barrier=min((b for b in applicable if observed<=b<=end),default=end)
            end=min(end,next_barrier)
            # Contact freshness is never renewed by a status packet. Conversely,
            # its valid interval cannot span a communication outage or an epoch.
            for comm_start,comm_end in communication[(sensor_id,row.get('source_epoch'))]:
                if comm_end<=start:continue
                if comm_start>=end:break
                cursor=max(start,comm_start);covered_end=min(end,comm_end)
                while cursor<covered_end:
                    local=cursor.astimezone(zone)
                    midnight=datetime.combine(local.date()+timedelta(days=1),datetime.min.time(),zone).astimezone(cursor.tzinfo)
                    boundary=min(covered_end,midnight);seconds=(boundary-cursor).total_seconds()
                    key=(sensor_id,str(local.date()));daily[key]['observed_seconds']+=seconds
                    if row['contact_state']=='OPEN':daily[key]['open_seconds']+=seconds
                    cursor=boundary
    durations=[dict(sensor_id=sid,date=day,**values,basis='supervised_estimate',
        complete=False,zone=registry.devices[sid]['zone']) for (sid,day),values in sorted(daily.items(),reverse=True)][:256]
    recent.sort(key=lambda r:instant(r['observed_at']),reverse=True)
    reliability=[dict(sensor_id=sid,retained_contact_reports=count) for sid,count in sorted(counts.items())]
    return recent[:48],durations,reliability
