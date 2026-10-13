"""Native thermal operational adapters; read-only acquisition grants no authority."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
from astro_geometry import _instant
from thermal_model.forcing_capture import _canonical
from thermal_model.installed_shade_score_inputs import ScoreReader,COMPRESSED_SOURCE_SCHEMA
from thermal_model.capture_readers import ReadBudget

MAX_QUERY_BYTES=64000000


class NativeScoreReader(ScoreReader):
    """One original stable SQL snapshot per historical endpoint pair."""
    def __init__(self,settings,*,shared_lock_guard):
        if not isinstance(settings,dict) or settings.get('schema')!=COMPRESSED_SOURCE_SCHEMA:
            raise ValueError('native score reader requires compressed source profile')
        super().__init__(deepcopy(settings),shared_lock_guard=shared_lock_guard)
        self.budget=ReadBudget(50,max_requests=40,guard=shared_lock_guard)
        self.transport.budget=self.budget
        self._paired_sources={};self._paired_sizes={};self._query_bytes=0

    def native(self,targets,*,assessed_at,sensor_epoch):
        from hourly_temperature_runtime import read_db_config
        from weather_temperature_config import load_temperature_receiver_configuration
        from weather_temperature_sources import (fetch_temperature_source,write_compressed_temperature_source,
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
            try:packet=fetch_temperature_source(lambda:self._connect(config),targets=targets,assessed_at=assessed,
                stream='indoor',policy=policies['indoor'],sensor_epoch=sensor_epoch,remaining_timeout=remaining)
            except psycopg2.Error:raise ValueError('bounded original paired native source unavailable') from None
            size=len(_canonical(packet))
            if self._query_bytes+size>MAX_QUERY_BYTES:raise ValueError('aggregate native pair source bytes exceed bound')
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
