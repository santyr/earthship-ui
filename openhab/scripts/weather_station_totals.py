"""Durable recorded rain amounts for displays, separate from qualified intervals.

Only accepted, continuous counter increments are accumulated. Unknown gaps,
receiver restarts and increments straddling midnight do not contribute rain.
Saved amounts never restore a sensor value, receipt clock or learning evidence.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import fcntl
import logging
import math
import os
import stat
import tempfile

SCHEMA='earthship-station-recorded-rain/v1'
UTC=timezone.utc

def starts(at,zone):
    if not isinstance(at,datetime) or at.utcoffset() is None:raise ValueError('aware rain receipt required')
    day=at.astimezone(zone).replace(hour=0,minute=0,second=0,microsecond=0)
    return {k:v.astimezone(UTC) for k,v in {'day':day,'week':day-timedelta(days=(day.weekday()+1)%7),'month':day.replace(day=1)}.items()}

def _object(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('duplicate saved rain field')
        result[k]=v
    return result

class RecordedRainTotals:
    def __init__(self,timezone_name,path=None):
        self.zone=ZoneInfo(timezone_name);self.path=None if path is None else Path(path);self.periods={};self.original=None;self.persistence_error=False
        if self.path is not None and not self.path.is_absolute():raise ValueError('absolute recorded rain file required')
        raw=self._read() if self.path is not None else None
        if raw is not None:
            value=json.loads(raw,object_pairs_hook=_object)
            if not isinstance(value,dict) or set(value)!={'schema','timezone','periods'} or value['schema']!=SCHEMA or value['timezone']!=self.zone.key:raise ValueError('recorded rain identity differs')
            periods=value['periods']
            if not isinstance(periods,dict) or set(periods)!={'day','week','month'}:raise ValueError('three recorded rain periods required')
            for name,p in periods.items():
                if not isinstance(p,dict) or set(p)!={'start','amount_in'}:raise ValueError('closed recorded rain period required')
                at=datetime.fromisoformat(p['start']);amount=p['amount_in']
                if starts(at,self.zone)[name]!=at or type(amount) not in (int,float) or not math.isfinite(amount) or not 0<=amount<=100000:raise ValueError('invalid saved rain period')
            self.periods=periods;self.original=raw

    def _read(self):
        try:fd=os.open(self.path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:return None
        try:
            meta=os.fstat(fd)
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=os.geteuid() or meta.st_mode&0o077 or not 1<=meta.st_size<=4096:raise ValueError('owned private bounded recorded rain file required')
            return os.read(fd,4097)
        finally:os.close(fd)

    def save(self):
        if self.path is None:return
        lock=os.open(str(self.path)+'.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            meta=os.fstat(lock)
            if not stat.S_ISREG(meta.st_mode) or meta.st_uid!=os.geteuid() or meta.st_mode&0o077:raise ValueError('private recorded rain lock required')
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            current=self._read()
            if current!=self.original:raise ValueError('recorded rain ledger changed concurrently')
            raw=json.dumps({'schema':SCHEMA,'timezone':self.zone.key,'periods':self.periods},sort_keys=True,separators=(',',':')).encode()
            fd,name=tempfile.mkstemp(prefix='.rain-totals-',dir=self.path.parent)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(raw);stream.flush();os.fsync(stream.fileno())
                os.replace(name,self.path);self.original=raw
            finally:
                if os.path.exists(name):os.unlink(name)
        finally:os.close(lock)

    def observe(self,delta_in,*,at,previous_at):
        if delta_in is not None and (type(delta_in) not in (int,float) or not math.isfinite(delta_in) or not 0<=delta_in<=.5):raise ValueError('accepted bounded increment required')
        changed=False
        for name,start in starts(at,self.zone).items():
            period=self.periods.get(name)
            if period is None or period['start']!=start.isoformat():
                period={'start':start.isoformat(),'amount_in':0.};self.periods[name]=period;changed=True
            if delta_in and previous_at is not None and start<=previous_at<=at:
                period['amount_in']+=delta_in;changed=True
        if changed and not self.persistence_error:
            try:self.save()
            except (OSError,ValueError):
                self.persistence_error=True
                logging.getLogger(__name__).error('Recorded rain persistence unavailable; live ingestion retained')


def replay_recorded_totals(observations,*,timezone_name):
    """Read original OpenHAB receipts; invalid rows create continuity barriers.

    This produces display counts only. It never declares an interval qualified,
    seeds measurement freshness, or infers rain across epochs or source faults.
    """
    from weather_rain_day import parse_rain_snapshot
    from weather_rain_evidence import RainPolicy
    from weather_station_counter import CounterTracker
    result=RecordedRainTotals(timezone_name);previous=None;tracker=None;last_persisted=None
    for index,(persisted,raw) in enumerate(observations):
        if index>=90000:raise ValueError('recorded rain history row bound exceeded')
        try:
            at=datetime.fromisoformat(persisted) if isinstance(persisted,str) else persisted
            sample=parse_rain_snapshot(raw,at,RainPolicy(sensor_id=206))
            if last_persisted is not None and at<=last_persisted:raise ValueError('history order differs')
            last_persisted=at
            if previous is not None and sample.received_at==previous.received_at and sample==previous:continue
            if previous is not None and sample.received_at==previous.received_at and sample.counter_in==previous.counter_in and sample.epoch==previous.epoch and sample.packet_count==previous.packet_count:continue
            continuous=(previous is not None and sample.received_at>previous.received_at and sample.epoch==previous.epoch and sample.packet_count>previous.packet_count and (sample.invalid_packets,sample.counter_drops,sample.counter_jumps)==(previous.invalid_packets,previous.counter_drops,previous.counter_jumps))
            if not continuous:tracker=CounterTracker(validity_seconds=120,maximum_counter_in=100000)
            transition=tracker.observe(sample.counter_in,at=sample.received_at,tick=sample.received_at.timestamp())
            result.observe(transition.delta_in,at=sample.received_at,previous_at=previous.received_at if continuous else None)
            previous=sample
        except (ValueError,TypeError,KeyError,OverflowError):
            previous=None;tracker=None
    return result
