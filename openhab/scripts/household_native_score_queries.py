"""Read only the validity windows needed by native historical endpoint pairs.

Outside the fitted runtime: source containers, selection and scoring remain
original. One pair uses one stable transaction and one paced request.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from thermal_model.forcing_capture import _canonical
from astro_geometry import _instant
import native_thermal_live as native


class EndpointWindowScoreReader(native.NativeScoreReader):
    def native(self,targets,*,assessed_at,sensor_epoch):
        from hourly_temperature_runtime import read_db_config
        from weather_temperature_config import load_temperature_receiver_configuration
        from weather_temperature_sources import (write_compressed_temperature_source,
            read_compressed_temperature_source,replay_temperature_source)
        from thermal_model.replay_budget import remaining_budget
        import psycopg2
        if not isinstance(targets,list) or not 1<=len(targets)<=2 or sensor_epoch!=self.epochs['air']:
            raise ValueError('bounded same-phase native pair required')
        targets=list(map(_instant,deepcopy(targets)));assessed=_instant(assessed_at)
        if (len(set(targets))!=len(targets) or targets!=sorted(targets) or targets[-1]>assessed or
                targets[-1]-targets[0]>timedelta(days=1) or assessed>datetime.now(timezone.utc)):
            raise ValueError('original elapsed native pair assessment required')
        self._acquisition_check()
        policies,epochs=load_temperature_receiver_configuration(self.settings['native_policy'])
        if epochs is None or epochs.get('indoor')!=sensor_epoch:raise ValueError('original native phase changed')
        config=read_db_config(self.settings['native_db_config']);key=(tuple(targets),assessed,sensor_epoch)
        path=self._paired_sources.get(key)
        def remaining():
            self._acquisition_check();return remaining_budget(self.budget.remaining())
        if path is None:
            try:packet=self._fetch_packet(config,targets=targets,assessed_at=assessed,
                stream='indoor',policy=policies['indoor'],sensor_epoch=sensor_epoch,remaining_timeout=remaining)
            except psycopg2.Error:raise ValueError('bounded original paired native source unavailable') from None
            size=len(_canonical(packet))
            if self._query_bytes+size+getattr(self,'_pending_query_bytes',0)>native.MAX_QUERY_BYTES:raise ValueError('aggregate native pair source bytes exceed bound')
            path=write_compressed_temperature_source(self.settings['output_directory'],packet,before_publish=self._acquisition_check)
        else:size=self._paired_sizes[key]
        retained=read_compressed_temperature_source(path.parent,path)
        if (retained['targets']!=[at.isoformat() for at in targets] or _instant(retained['assessed_at'])!=assessed or
                retained['sensor_epoch']!=sensor_epoch or retained['stream']!='indoor'):
            raise ValueError('original paired native request context differs')
        selected=replay_temperature_source(retained)
        self._acquisition_check()
        if key not in self._paired_sources:
            if len(self._paired_sources)>=40:raise ValueError('bounded native pair source inventory required')
            self._query_bytes+=size;self._paired_sizes[key]=size;self._paired_sources[key]=path
            self.native_source_paths.append(str(path))
        return selected


    def _fetch_packet(self,config,**request):
        return fetch_endpoint_source(lambda:self._connect(config),**request)


class RecentCycleWindowReader(EndpointWindowScoreReader):
    """Acquire one baseline batch; retain only packets the comparator requests."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._pending_packets={};self._pending_query_bytes=0;self._pending_context=None

    def verify_unchanged(self):
        # Offline scoring/report replay may continue after acquisition ends.
        # The caller's full-job guard still bounds CPU work and preparation time.
        from hashlib import sha256
        from pathlib import Path
        from thermal_model.runtime_bundle import _owned_bytes
        if self.shared_lock_guard is not None:self.shared_lock_guard()
        if any(sha256(_owned_bytes(Path(self.settings[key]),16384)).hexdigest()!=value
               for key,value in self.hashes.items()):
            raise ValueError('original score source configuration changed')

    def _acquisition_check(self):
        # Every actual read keeps the original 50-second acquisition deadline.
        self.budget.remaining()
        super()._acquisition_check()
        self.budget.remaining()

    def _fetch_packet(self,config,**request):
        targets=request['targets'];assessed=request['assessed_at'];epoch=request['sensor_epoch']
        key=(tuple(targets),assessed,epoch)
        if key not in self._pending_packets and len(targets)==2:
            from thermal_model.recent_cycles import POLICY,shifted_clock
            span=targets[-1]-targets[0];context=(assessed,epoch,span)
            pairs=[]
            for lag in range(1,POLICY['lookback_days']+1):
                origin=shifted_clock(assessed,lag);end=shifted_clock(assessed+span,lag)
                if origin is not None and end is not None and origin<end<assessed and end-origin==span:
                    pairs.append([origin,end])
            if targets in pairs and context!=self._pending_context:
                self._pending_packets={};self._pending_query_bytes=0
                requests=[dict(request,targets=pair) for pair in pairs]
                packets=_fetch_endpoint_packets(lambda:self._connect(config),requests,remaining_timeout=request['remaining_timeout'])
                size=sum(len(_canonical(packet)) for packet in packets)
                if self._query_bytes+size>native.MAX_QUERY_BYTES:raise ValueError('aggregate native pair source bytes exceed bound')
                self._pending_packets={(tuple(pair),assessed,epoch):packet for pair,packet in zip(pairs,packets)}
                self._pending_query_bytes=size;self._pending_context=context
        if key in self._pending_packets:
            packet=self._pending_packets.pop(key);self._pending_query_bytes-=len(_canonical(packet))
            return packet
        return super()._fetch_packet(config,**request)


def fetch_endpoint_source(connection_factory,*,remaining_timeout,**request):
    return _fetch_endpoint_packets(connection_factory,[request],remaining_timeout=remaining_timeout)[0]


def _fetch_endpoint_packets(connection_factory,requests,*,remaining_timeout):
    from weather_temperature_sources import build_temperature_source
    from weather_temperature_reader import _utc
    if not isinstance(requests,list) or not 1<=len(requests)<=31:raise ValueError('bounded original endpoint requests required')
    requests=[{key:value for key,value in request.items() if key!='remaining_timeout'} for request in requests]
    for request in requests:
        if not 1<=len(request['targets'])<=2:raise ValueError('bounded original endpoint pair required')
        build_temperature_source(rows=[],**request)
    def remaining():
        import math
        seconds=remaining_timeout()
        if type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<0.001:
            raise ValueError('native query deadline elapsed or too short')
        return seconds
    connection=None
    try:
        remaining();connection=connection_factory();remaining()
        if connection.get_transaction_status()!=0:raise ValueError('dedicated idle connection required')
        connection.set_session(readonly=True,autocommit=False,isolation_level='REPEATABLE READ')
        packets=[];total_rows=0;total_bytes=0
        with connection.cursor() as cursor:
            def execute(query,params=None):
                milliseconds=min(2000,int(remaining()*1000))
                cursor.execute('SET LOCAL statement_timeout = %s',(f'{milliseconds}ms',))
                remaining();cursor.execute(query,params);remaining()
            execute("SET LOCAL lock_timeout = '1000ms'")
            execute("SET LOCAL idle_in_transaction_session_timeout = '5000ms'")
            execute('SHOW transaction_read_only')
            if cursor.fetchone()!=('on',):raise ValueError('read-only transaction required')
            execute('SHOW transaction_isolation')
            if cursor.fetchone()!=('repeatable read',):raise ValueError('stable snapshot required')
            from weather_temperature_history import EVIDENCE_ITEM
            execute('SELECT itemid FROM public.items WHERE itemname=%s LIMIT 2',(EVIDENCE_ITEM,))
            matches=cursor.fetchall()
            if len(matches)!=1 or type(matches[0][0]) is not int or not 0<=matches[0][0]<=2147483647:
                raise ValueError('unique evidence Item mapping required')
            table=f'public.item{matches[0][0]:04d}'
            value='CASE WHEN octet_length(value::text) <= 8192 THEN value::text ELSE NULL END'
            for request in requests:
                observations=[]
                for target in request['targets']:
                    start=target-timedelta(seconds=request['policy'].validity_seconds)
                    execute(f'SELECT time, {value} FROM {table} WHERE time < %s ORDER BY time DESC LIMIT 1',(start,))
                    carry=cursor.fetchone()
                    execute(f'SELECT time, {value} FROM {table} WHERE time >= %s AND time <= %s ORDER BY time LIMIT 10001',(start,target))
                    rows=cursor.fetchall()
                    if carry is not None and _utc(carry[0])>=start:raise ValueError('invalid carry boundary')
                    if any(not start<=_utc(at)<=target for at,_ in rows):raise ValueError('history outside window')
                    added=([] if carry is None else [carry])+rows;total_rows+=len(added)
                    if total_rows>10000:raise ValueError('history row bound exceeded')
                    observations.extend(added)
                # Endpoint freshness makes earlier barriers irrelevant; preserve
                # complete validity windows and carries, including nulls.
                observations.sort(key=lambda row:_utc(row[0]));unique=[]
                for at,raw in observations:
                    row=(_utc(at),raw)
                    if not unique or row!=unique[-1]:unique.append(row)
                packet=build_temperature_source(rows=unique,**request);total_bytes+=len(_canonical(packet))
                if total_bytes>native.MAX_QUERY_BYTES:raise ValueError('aggregate native pair source bytes exceed bound')
                packets.append(packet);remaining()
        remaining();return packets
    finally:
        if connection is not None:
            try:connection.close()  # Always rollback; never commit.
            except Exception:pass
