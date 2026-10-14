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
            try:packet=fetch_endpoint_source(lambda:self._connect(config),targets=targets,assessed_at=assessed,
                stream='indoor',policy=policies['indoor'],sensor_epoch=sensor_epoch,remaining_timeout=remaining)
            except psycopg2.Error:raise ValueError('bounded original paired native source unavailable') from None
            size=len(_canonical(packet))
            if self._query_bytes+size>native.MAX_QUERY_BYTES:raise ValueError('aggregate native pair source bytes exceed bound')
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


def fetch_endpoint_source(connection_factory,*,targets,assessed_at,stream,policy,sensor_epoch,remaining_timeout):
    from weather_temperature_sources import build_temperature_source
    from weather_temperature_reader import _utc
    request=dict(targets=targets,assessed_at=assessed_at,stream=stream,policy=policy,sensor_epoch=sensor_epoch)
    build_temperature_source(rows=[],**request)  # Validate before any connection.
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
        observations=[]
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
            # A receipt fresh at an endpoint must have receivedAt later
            # than endpoint-validity. Earlier barriers cannot survive that
            # fresh receipt; retain the carry and every barrier in the window.
            for target in targets:
                start=target-timedelta(seconds=policy.validity_seconds)
                execute(f'SELECT time, {value} FROM {table} WHERE time < %s ORDER BY time DESC LIMIT 1',(start,))
                carry=cursor.fetchone()
                execute(f'SELECT time, {value} FROM {table} WHERE time >= %s AND time <= %s ORDER BY time LIMIT 10001',(start,target))
                rows=cursor.fetchall()
                if carry is not None and _utc(carry[0])>=start:raise ValueError('invalid carry boundary')
                if any(not start<=_utc(at)<=target for at,_ in rows):raise ValueError('history outside window')
                observations.extend(([] if carry is None else [carry])+rows)
                if len(observations)>10000:raise ValueError('history row bound exceeded')
        remaining()
        # Overlapping windows may return the same original row twice. Keep
        # conflicts so the unchanged replay validator refuses them.
        observations.sort(key=lambda row:_utc(row[0]))
        unique=[]
        for at,raw in observations:
            row=(_utc(at),raw)
            if not unique or row!=unique[-1]:unique.append(row)
        return build_temperature_source(rows=unique,**request)
    finally:
        if connection is not None:
            try:connection.close()  # Always rollback; never commit.
            except Exception:pass
