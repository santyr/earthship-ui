"""Observed durations are censored at freshness barriers and local midnight."""
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from services.observations.contract import instant


def summarize(history,registry,now,timezone_name='America/Denver'):
    zone=ZoneInfo(timezone_name);daily=defaultdict(lambda:dict(open_seconds=0,observed_seconds=0))
    recent=[];by_sensor=defaultdict(list);counts=defaultdict(int);barriers=defaultdict(list)
    for row in history:
        device=registry.devices.get(row['sensor_id'])
        if device is None or row['hardware_epoch']!=device['hardware_epoch']:continue
        if instant(row['received_at'])>now:continue
        if row['event_type']=='quality_barrier':barriers[row['sensor_id']].append(instant(row['observed_at']))
        if row['event_type'] in ('opened','closed','tamper','tamper_cleared') or row['event_type'].startswith('communication_'):
            recent.append({k:row.get(k) for k in ('sensor_id','event_type','observed_at','received_at','continuity','synthetic')})
        if row.get('historical') or row.get('contact_state') not in ('OPEN','CLOSED'):continue
        by_sensor[row['sensor_id']].append(row);counts[row['sensor_id']]+=1
    for sensor_id,rows in by_sensor.items():
        rows.sort(key=lambda r:(r['observed_at'],r.get('journal_sequence',0)))
        for i,row in enumerate(rows):
            start=instant(row['observed_at']);end=min(now,instant(row['valid_until']))
            if i+1<len(rows):
                following=rows[i+1];end=min(end,instant(following['observed_at']))
                if following.get('continuity')=='gap' and not any(start<=b<=end for b in barriers[sensor_id]):end=start
            next_barrier=min((b for b in barriers[sensor_id] if start<=b<=end),default=end)
            end=min(end,next_barrier)
            while start<end:
                local=start.astimezone(zone)
                midnight=datetime.combine(local.date()+timedelta(days=1),datetime.min.time(),zone).astimezone(start.tzinfo)
                boundary=min(end,midnight);seconds=(boundary-start).total_seconds()
                key=(sensor_id,str(local.date()));daily[key]['observed_seconds']+=seconds
                if row['contact_state']=='OPEN':daily[key]['open_seconds']+=seconds
                start=boundary
    durations=[dict(sensor_id=sid,date=day,**values,basis='supervised_estimate',
        complete=False,zone=registry.devices[sid]['zone']) for (sid,day),values in sorted(daily.items(),reverse=True)][:256]
    recent.sort(key=lambda r:r['observed_at'],reverse=True)
    reliability=[dict(sensor_id=sid,retained_contact_reports=count) for sid,count in sorted(counts.items())]
    return recent[:48],durations,reliability
