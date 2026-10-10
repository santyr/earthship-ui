"""Private bounded native/JDBC readers for mature forecast score collection.

Only read endpoints and dedicated local read-only connections are used. No
weather fallback, Item PUT, fitting or release override is exposed.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path

from .forcing_capture import _private_directory
from .graduation_policy import _utc
from .runtime_bundle import _owned_bytes
from .policy_registration import _read_private
from .capture_readers import BASES,ReadBudget,bounded_journal_dsn
from .installed_shade_live_inputs import TelemetryTransport
from .installed_shade_published_origin import _receipt,NUMERIC_ITEM,PUBLICATION_ITEM

SCHEMA='earthship-installed-shade-score-config/v1'
RAW_SCHEMA='earthship-installed-shade-score-config/v2'
SOURCE_PATHS={'token_file','native_db_config','native_policy'}
FIELDS=SOURCE_PATHS|{'schema','openhab_base','output_directory'}


def _clock():return datetime.now(timezone.utc)


def load_raw_score_settings(path):
    return load_score_settings(path,_version=2)


def load_score_settings(path,*,_version=1):
    path=Path(path);_private_directory(path.parent);value=_read_private(path)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=(RAW_SCHEMA if _version==2 else SCHEMA) or value['openhab_base'] not in BASES:
        raise ValueError('closed private score configuration required')
    for key in SOURCE_PATHS|{'output_directory'}:
        name=value[key]
        if not isinstance(name,str) or not 1<=len(name)<=1024:raise ValueError('bounded explicit source path required')
        target=Path(name)
        if not target.is_absolute() or target.resolve()!=target:raise ValueError('resolved original score source path required')
        if key=='output_directory':_private_directory(target)
        else:_private_directory(target.parent);_owned_bytes(target,16384)
    return deepcopy(value)


class ScoreReader:
    def __init__(self,settings,*,shared_lock_guard=None):
        self.shared_lock_guard=shared_lock_guard
        if shared_lock_guard is not None:shared_lock_guard()
        self.settings=deepcopy(settings);self.budget=ReadBudget(85,max_requests=24);self.native_source_paths=[];self._native_sources={}
        self.hashes={key:sha256(_owned_bytes(Path(settings[key]),16384)).hexdigest() for key in SOURCE_PATHS}
        token=_owned_bytes(Path(settings['token_file']),4096).decode().strip()
        self.transport=TelemetryTransport(base=settings['openhab_base'],token_reader=lambda:token,budget=self.budget)
        from thermal_temperature_runtime import _configured_sensor_epochs
        self.epochs=_configured_sensor_epochs(dict(THERMAL_TEMP_POLICY=settings['native_policy']))
    def verify_unchanged(self):
        guard=getattr(self,'shared_lock_guard',None)
        if guard is not None:guard()
        self.budget.remaining()
        if any(sha256(_owned_bytes(Path(self.settings[key]),16384)).hexdigest()!=value for key,value in self.hashes.items()):
            raise ValueError('original score source configuration changed')
    def publication(self,receipt):
        if not isinstance(receipt,dict) or receipt.get('item') not in (NUMERIC_ITEM,PUBLICATION_ITEM):raise ValueError('fixed original telemetry receipt required')
        _,at=_receipt(receipt,receipt['item'])
        if at>_utc(_clock()):raise ValueError('future original telemetry receipt refused')
        self.verify_unchanged()
        result=self.transport.persisted(receipt['item'],receipt['state'],since=at,until=at+timedelta(milliseconds=1),preflight=self.verify_unchanged)
        self.verify_unchanged();return result
    def _connect(self,config):
        self.verify_unchanged()
        import psycopg2
        from psycopg2.extensions import make_dsn,parse_dsn
        params=parse_dsn(bounded_journal_dsn(make_dsn(**config)));timeout=self.budget.begin()
        if timeout<2:raise ValueError('bounded native connection deadline unavailable')
        params['connect_timeout']=str(min(3,int(timeout)))
        self.verify_unchanged()
        try:connection=psycopg2.connect(make_dsn(**params))
        except psycopg2.Error:raise ValueError('bounded original native source unavailable') from None
        try:self.budget.remaining();return connection
        except BaseException:connection.close();raise
    def native(self,targets,*,assessed_at,sensor_epoch):
        import psycopg2
        from hourly_temperature_runtime import read_db_config
        from weather_temperature_config import load_temperature_receiver_configuration
        from weather_temperature_sources import fetch_temperature_source,write_temperature_source,read_temperature_source,replay_temperature_source
        assessed_at=_utc(assessed_at)
        if (not isinstance(targets,list) or not 1<=len(targets)<=2 or sensor_epoch!=self.epochs['air']):raise ValueError('bounded same-phase native target request required')
        targets=list(map(_utc,targets))
        if (len(set(targets))!=len(targets) or targets!=sorted(targets) or targets[-1]>assessed_at or
                targets[-1]-targets[0]>timedelta(days=1) or assessed_at>_utc(_clock())):
            raise ValueError('original elapsed native assessment required')
        self.verify_unchanged()
        policies,epochs=load_temperature_receiver_configuration(self.settings['native_policy'])
        if epochs is None or epochs.get('indoor')!=sensor_epoch:raise ValueError('original native phase changed')
        config=read_db_config(self.settings['native_db_config'])
        rows=[]
        for target in targets:
            self.verify_unchanged()
            key=(target,assessed_at,sensor_epoch)
            path=self._native_sources.get(key)
            if path is None:
                try:packet=fetch_temperature_source(lambda:self._connect(config),targets=[target],assessed_at=assessed_at,
                    stream='indoor',policy=policies['indoor'],sensor_epoch=sensor_epoch)
                except psycopg2.Error:raise ValueError('bounded original native source unavailable') from None
                self.verify_unchanged()
                path=write_temperature_source(self.settings['output_directory'],packet)
            retained=read_temperature_source(path.parent,path)
            selected=replay_temperature_source(retained)
            if (retained['targets']!=[target.isoformat()] or _utc(retained['assessed_at'])!=assessed_at or
                    retained['sensor_epoch']!=sensor_epoch or retained['stream']!='indoor'):
                raise ValueError('original endpoint query context differs')
            self.verify_unchanged()
            self._native_sources[key]=path
            if str(path) not in self.native_source_paths:self.native_source_paths.append(str(path))
            rows.extend(selected)
        return rows
