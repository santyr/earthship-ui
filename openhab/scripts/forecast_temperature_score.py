"""Replay original correction forecasts and native outcomes; no release authority.

These descriptive auxiliary scores do not fit models or authorize publication.
Summaries consume original source packets, never precomputed scalar scores.
"""
from collections import defaultdict
from datetime import datetime,timedelta,time,timezone,date
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from forecast_input_capture import _canonical,_directory,_instant
from forecast_temperature_origin import read_origin,_policy
from weather_temperature_reader import select_temperature_grid_v2
from weather_temperature_config import _object,_nonfinite

SOURCE_SCHEMA='earthship-temperature-correction-score-sources/v1'
SCORE_SCHEMA='earthship-temperature-correction-score/v1'
SUMMARY_SCHEMA='earthship-temperature-correction-summary/v1'
FIELDS={'schema','origin_sha256','publication_receipt','target','assessed_at','history_start','native_rows'}
MAX_BYTES=5*1024*1024
MAX_ROWS=512
MAX_PACKETS=2048


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        raise ValueError('finite original forecast required')
    return float(value)


def _source_packet(packet):
    if not isinstance(packet,dict) or set(packet)!=FIELDS or packet['schema']!=SOURCE_SCHEMA:
        raise ValueError('closed correction source packet required')
    if not isinstance(packet['origin_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',packet['origin_sha256']):
        raise ValueError('original origin digest required')
    target,assessed,start=(_instant(packet[name]) for name in ('target','assessed_at','history_start'))
    rows=packet['native_rows']
    if not isinstance(rows,list) or len(rows)>MAX_ROWS:
        raise ValueError('bounded complete native source rows required')
    for row in rows:
        if (not isinstance(row,list) or len(row)!=2 or not isinstance(row[1],str)
                or len(row[1].encode())>8192 or not _instant(row[0])<=min(target,assessed)):
            raise ValueError('original native row invalid or future')
    if len(_canonical(packet))>MAX_BYTES:
        raise ValueError('bounded source packet required')
    return target,assessed,start,[(_instant(at),raw) for at,raw in rows]


def _frame(origin,weather):
    """Align raw and actually published rows in original provider order.

    Equal local clock labels at a DST fold retain their distinct issued offsets.
    Duplicate UTC targets or offsets inconsistent with the original site refuse.
    """
    snapshot=weather['snapshot'];detail=json.loads(origin['detail_state'],object_pairs_hook=_object,parse_constant=_nonfinite)
    units=snapshot.get('hourly_units')
    if not isinstance(units,dict) or units.get('temperature_2m')!='°F':
        raise ValueError('explicit original Fahrenheit weather units required')
    zone=ZoneInfo(detail['timezone']);hourly=snapshot['hourly'];times=hourly.get('time');raws=hourly.get('temperature_2m')
    if (not isinstance(times,list) or not isinstance(raws,list) or len(times)!=len(raws) or len(times)>1024
            or any(not isinstance(t,str) for t in times)):
        raise ValueError('bounded original hourly weather required')
    daily=snapshot['daily'].get('time')
    if not isinstance(daily,list) or [d['date'] for d in detail['days']]!=daily[:10]:
        raise ValueError('original published day identity differs')
    if len(set(daily))!=len(daily):raise ValueError('duplicate original weather days')
    codes=hourly.get('weather_code',[])
    if not isinstance(codes,list):raise ValueError('original weather code series required')
    result={}
    for day in detail['days']:
        indices=[i for i,t in enumerate(times) if t[:10]==day['date']]
        if len(indices)!=len(day['hours']):raise ValueError('original raw/published hourly counts differ')
        for i,hour in zip(indices,day['hours']):
            raw_at=datetime.fromisoformat(times[i]);issued_at=datetime.fromisoformat(hour['at']);target=_instant(hour['at'])
            local=target.astimezone(zone)
            if (issued_at.replace(tzinfo=None)!=local.replace(tzinfo=None)
                    or issued_at.utcoffset()!=local.utcoffset()):
                raise ValueError('issued local clock does not round-trip in original timezone')
            if raw_at.utcoffset() is None:
                candidates={candidate for fold in (0,1)
                    if (candidate:=raw_at.replace(tzinfo=zone,fold=fold).astimezone(timezone.utc))
                    .astimezone(zone).replace(tzinfo=None)==raw_at}
                if issued_at.replace(tzinfo=None)!=raw_at or target not in candidates:
                    raise ValueError('original raw/published local target differs')
            elif _instant(times[i])!=target:
                raise ValueError('original aware weather target differs')
            code=codes[i] if i<len(codes) else None
            if code!=hour.get('weatherCode') or target in result:
                raise ValueError('original weather category or unique target differs')
            result[target]=(raws[i],hour.get('tempF'),code)
    return detail,zone,result


def _publication(origin,packet,assessed):
    receipt=packet['publication_receipt']
    if (not isinstance(receipt,dict) or set(receipt)!={'item','stored_at','state'}
            or receipt['item']!='Forecast_10Day_JSON' or receipt['state']!=origin['detail_state']):
        raise ValueError('actual exact persisted detail receipt required')
    stored=_instant(receipt['stored_at']);start=_instant(origin['publication_started_at'])
    floor=start.replace(microsecond=start.microsecond//1000*1000)
    end=_instant(origin['publication_completed_at'])
    if not floor<=stored<=end+timedelta(minutes=5) or not end<=assessed or stored>assessed:
        raise ValueError('actual original publication time incompatible')
    return stored


def _lead(hours):
    for ceiling,label in ((6,'0-6h'),(12,'6-12h'),(24,'12-24h'),(48,'24-48h')):
        if hours<=ceiling:return label
    return 'over-48h'


def score_sources(origin_directory,packet):
    target,assessed,start,rows=_source_packet(packet)
    root=_directory(Path(origin_directory));path=root/(packet['origin_sha256']+'.temperature-origin-v1.json')
    origin,weather=read_origin(root,path);stored=_publication(origin,packet,assessed)
    detail,zone,frame=_frame(origin,weather)
    if target not in frame or target<=stored:
        raise ValueError('target is not an original future published forecast')
    policies,epochs=_policy(origin['native_policy']);policy=policies['outdoor']
    if start>target-timedelta(seconds=policy.validity_seconds):
        raise ValueError('complete original native history interval required')
    raw,corrected,code=frame[target];raw,corrected=map(_number,(raw,corrected))
    local=target.astimezone(zone);season=('winter','spring','summer','autumn')[(local.month%12)//3]
    state_digest=sha256(_canonical({'hourly_model':origin['hourly_model'],'daily_adjustment':origin['daily_adjustment']})).hexdigest()
    result={'schema':SCORE_SCHEMA,'origin_sha256':packet['origin_sha256'],'target':target.isoformat(),
        'publication_stored_at':stored.isoformat(),'assessed_at':assessed.isoformat(),
        'runtime_revision':origin['runtime']['code_revision'],'adjustment_state_sha256':state_digest,
        'sensor_epoch':epochs['outdoor'],'timezone':detail['timezone'],'target_day':local.date().isoformat(),
        'local_hour':local.hour,'lead_hours':(target-stored).total_seconds()/3600,
        'lead_bucket':_lead((target-stored).total_seconds()/3600),'calendar_season':season,
        'weather_category':('weather_code:'+str(code) if type(code) is int and 0<=code<=99 else 'unknown'),
        'status':'pending','release_authority':False}
    if assessed<target+timedelta(minutes=5):return result
    selected=select_temperature_grid_v2(rows,targets=[target],assessed_at=assessed,
        history_start=start,stream='outdoor',policy=policy,sensor_epoch=epochs['outdoor'])[0][1]
    if selected is None:
        result['status']='withheld';return result
    measured=selected['temperatureF']
    result.update(status='qualified',raw_forecast_f=raw,corrected_forecast_f=corrected,measured_f=measured,
        raw_error_f=raw-measured,corrected_error_f=corrected-measured,
        native_snapshot_sha256=selected['snapshotSha256'])
    return result


def _metrics(rows,field):
    # Equal weight per target calendar day, not per dense forecast row.
    days=defaultdict(list)
    for row in rows:days[row['target_day']].append(row[field])
    scale=max(abs(value) for values in days.values() for value in values)
    if scale==0:return {'mae_f':0.,'rmse_f':0.,'bias_f':0.}
    absolute=[math.fsum(abs(x/scale) for x in values)/len(values) for values in days.values()]
    squares=[math.fsum((x/scale)**2 for x in values)/len(values) for values in days.values()]
    signed=[math.fsum(x/scale for x in values)/len(values) for values in days.values()]
    return {'mae_f':scale*min(1.,math.fsum(absolute)/len(absolute)),
            'rmse_f':scale*math.sqrt(min(1.,math.fsum(squares)/len(squares))),
            'bias_f':scale*max(-1.,min(1.,math.fsum(signed)/len(signed)))}



def _complete_days(origin_directory,cohorts):
    completed=set()
    for (digest,day),targets in cohorts.items():
        root=Path(origin_directory);origin,weather=read_origin(root,root/(digest+'.temperature-origin-v1.json'))
        detail,zone,frame=_frame(origin,weather);d=date.fromisoformat(day)
        start=datetime.combine(d,time(),tzinfo=zone).astimezone(timezone.utc)
        end=datetime.combine(d+timedelta(days=1),time(),tzinfo=zone).astimezone(timezone.utc)
        expected={start+timedelta(hours=i) for i in range(int((end-start).total_seconds()/3600))}
        if expected<=set(frame) and expected==targets:
            completed.add((detail['timezone'],day))
    return len(completed)


def summarize_sources(origin_directory,packets):
    seen=set();qualified=[];counts=defaultdict(int);cohorts=defaultdict(set)
    for n,packet in enumerate(packets,1):
        if n>MAX_PACKETS:raise ValueError('bounded original-source summary required')
        pair=(packet['origin_sha256'],_instant(packet['target']))
        if pair in seen:raise ValueError('duplicate original forecast/target pair')
        seen.add(pair);row=score_sources(origin_directory,packet);counts[row['status']]+=1
        if row['status']=='qualified':
            qualified.append(row);cohorts[(row['origin_sha256'],row['target_day'])].add(_instant(row['target']))
    keys=('runtime_revision','sensor_epoch','local_hour','lead_bucket','calendar_season','weather_category')
    groups=defaultdict(list)
    for row in qualified:groups[tuple(row[k] for k in keys)].append(row)
    summaries=[]
    for group,rows in sorted(groups.items()):
        # Distinct origins in one lead bucket may predict the same actual point.
        # Earliest original publication wins deterministically before scoring;
        # alternative forecasts remain counted only as descriptive raw support.
        points={}
        for row in sorted(rows,key=lambda r:(r['publication_stored_at'],r['origin_sha256'])):
            points.setdefault(row['target'],row)
        selected=list(points.values());states=defaultdict(list)
        for row in selected:states[row['adjustment_state_sha256']].append(row)
        summaries.append({**dict(zip(keys,group)),'qualified_observation_count':len(rows),
            'unique_target_count':len(selected),'unique_target_days':len({r['target_day'] for r in selected}),
            'metrics':{'raw':_metrics(selected,'raw_error_f'),'corrected':_metrics(selected,'corrected_error_f')},
            'adjustment_state_strata':[{'sha256':state,'qualified_observation_count':len(values),
                'metrics':{'raw':_metrics(values,'raw_error_f'),'corrected':_metrics(values,'corrected_error_f')}}
                for state,values in sorted(states.items())],
            'mixed_adjustment_states':len(states)>1})
    return {'schema':SUMMARY_SCHEMA,'source_packet_count':len(seen),'qualified_observation_count':len(qualified),
        'withheld_observation_count':counts['withheld'],'pending_observation_count':counts['pending'],
        'unique_target_days':len({(r['timezone'],r['target_day']) for r in qualified}),
        'complete_issued_hour_days':_complete_days(origin_directory,cohorts),
        'metric_weighting':'equal_target_day_weight_after_unique_target_selection_per_stratum',
        'complete_day_definition':'one_original_issue_with_qualified_all_expected_UTC_hour_targets_for_local_day',
        'confidence':'not_release_assessed','release_authority':False,'groups':summaries}


def write_sources(directory,packet):
    from forecast_temperature_origin import _write
    _source_packet(packet)
    raw=_canonical(packet)
    return _write(_directory(Path(directory)),sha256(raw).hexdigest()+'.temperature-score-sources-v1.json',raw)


def read_sources(directory,path):
    from forecast_temperature_origin import _read
    root=_directory(Path(directory));path=Path(path)
    if path.parent!=root or not re.fullmatch(r'[0-9a-f]{64}\.temperature-score-sources-v1\.json',path.name):
        raise ValueError('original score source path required')
    raw=_read(path,MAX_BYTES)
    if sha256(raw).hexdigest()!=path.name.split('.')[0]:
        raise ValueError('original score source digest mismatch')
    packet=json.loads(raw,object_pairs_hook=_object,parse_constant=_nonfinite)
    _source_packet(packet)
    if _canonical(packet)!=raw:raise ValueError('canonical original score source required')
    return packet
