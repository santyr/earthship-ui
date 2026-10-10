"""Private configuration and bounded source/telemetry transports for live issue.

All database connections are dedicated read-only local snapshots. HTTP can
update only the two fixed String telemetry Items. No commands, fitting or
provider fallback is available here.
"""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,build_opener,ProxyHandler

from .forcing_capture import _canonical,_private_directory
from .graduation_policy import _utc
from .runtime_bundle import _owned_bytes
from .origin_capture import _object
from .policy_registration import _read_private
from .capture_readers import BASES,ReadBudget,_NoRedirect,bounded_journal_dsn
from .installed_shade_published_origin import NUMERIC_ITEM,PUBLICATION_ITEM

SCHEMA='earthship-installed-shade-live-config/v1'
RAW_SCHEMA='earthship-installed-shade-live-config/v2'
SOURCE_PATHS={'release_inputs_path','token_file','journal_dsn_file','forecast_dsn_file','native_db_config','native_policy'}
FIELDS=SOURCE_PATHS|{'schema','openhab_base','evidence_directory'}
ITEMS={NUMERIC_ITEM,PUBLICATION_ITEM}
MAX_RESPONSE_BYTES=262144
MAX_TOTAL_BYTES=2097152


def _clock():return datetime.now(timezone.utc)


def load_raw_live_settings(path):
    return load_live_settings(path,_version=2)


def load_live_settings(path,*,_version=1):
    path=Path(path);_private_directory(path.parent);value=_read_private(path)
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=(RAW_SCHEMA if _version==2 else SCHEMA) or value['openhab_base'] not in BASES:
        raise ValueError('closed private installed live configuration required')
    for key in SOURCE_PATHS|{'evidence_directory'}:
        name=value[key]
        if not isinstance(name,str) or not 1<=len(name)<=1024:raise ValueError('bounded explicit source path required')
        target=Path(name)
        if not target.is_absolute() or target.resolve()!=target:raise ValueError('resolved original source path required')
        if key=='evidence_directory':_private_directory(target)
        else:_private_directory(target.parent);_owned_bytes(target,16384)
    if _version==2:
        from .installed_shade_publication import COMPLETE_RAW_REFERENCE_SCHEMA,REFERENCE_FIELDS
        refs=_read_private(Path(value['release_inputs_path']))
        if not isinstance(refs,dict) or set(refs)!=REFERENCE_FIELDS or refs['schema']!=COMPLETE_RAW_REFERENCE_SCHEMA:
            raise ValueError('complete raw release references required')
    return deepcopy(value)


class TelemetryTransport:
    def __init__(self,*,base,token_reader,budget,opener=None):
        if base not in BASES:raise ValueError('approved local telemetry endpoint required')
        self.base=base;self.token_reader=token_reader;self.budget=budget
        self.opener=opener or build_opener(ProxyHandler({}),_NoRedirect()).open
        self.total=0;self.checked=set()
    def _request(self,path,*,method='GET',state=None,preflight=None):
        token=self.token_reader()
        if not isinstance(token,str) or not 1<=len(token)<=4096 or any(ord(c)<32 for c in token):raise ValueError('bounded original token required')
        url=self.base+path;headers={'Authorization':'Bearer '+token}
        if state is not None:headers['Content-Type']='text/plain'
        request=Request(url,method=method,headers=headers,data=None if state is None else state.encode())
        timeout=self.budget.begin()
        # Item lookup and pacing may outlive native receipts. The sender runs
        # the final source/runtime/expiry guard after those delays.
        if preflight is not None:preflight()
        timeout=min(timeout,self.budget.remaining())
        with self.opener(request,timeout=timeout) as response:
            if hasattr(response,'geturl') and response.geturl()!=url:raise ValueError('telemetry redirect refused')
            raw=response.read(MAX_RESPONSE_BYTES+1);self.total+=len(raw)
            if len(raw)>MAX_RESPONSE_BYTES or self.total>MAX_TOTAL_BYTES:raise ValueError('bounded telemetry response required')
        self.budget.remaining()
        if method=='PUT':return None
        def reject(_):raise ValueError('nonfinite telemetry response')
        return json.loads(raw,object_pairs_hook=_object,parse_constant=reject)
    def require_string(self,item):
        if item not in ITEMS:raise ValueError('fixed thermal telemetry Item required')
        value=self._request('/items/'+item)
        if not isinstance(value,dict) or value.get('name')!=item or value.get('type')!='String':raise ValueError('existing exact String telemetry Item required')
        self.checked.add(item)
    def put(self,item,state,*,preflight=None):
        if item not in ITEMS or not isinstance(state,str) or len(state.encode())>=16384:raise ValueError('bounded fixed String telemetry write required')
        if item not in self.checked:self.require_string(item)
        self._request('/items/'+item+'/state',method='PUT',state=state,preflight=preflight)
    def persisted(self,item,state,*,since,until,preflight=None):
        if item not in ITEMS:raise ValueError('fixed actual telemetry receipt required')
        since,until=map(_utc,(since,until));floor=since.replace(microsecond=since.microsecond//1000*1000)
        if not floor<=until or until-floor>timedelta(minutes=2):raise ValueError('bounded actual publication receipt interval required')
        query=urlencode(dict(serviceId='jdbc',starttime=floor.isoformat(),endtime=until.isoformat()))
        value=self._request('/persistence/items/'+item+'?'+query,preflight=preflight)
        rows=value.get('data') if isinstance(value,dict) else None
        if not isinstance(rows,list) or len(rows)>32:raise ValueError('bounded actual persisted rows required')
        expected=json.loads(state,object_pairs_hook=_object)
        selected=[]
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'time','state'} or type(row['time']) is not int or not isinstance(row['state'],str):raise ValueError('closed actual persisted receipt row required')
            at=datetime(1970,1,1,tzinfo=timezone.utc)+timedelta(milliseconds=row['time'])
            if not floor<=at<=until:continue
            try:actual=json.loads(row['state'],object_pairs_hook=_object)
            except ValueError:continue
            if _canonical(actual)==_canonical(expected):selected.append(dict(item=item,**row))
        if len(selected)!=1:raise ValueError('one exact actual persisted publication required')
        return selected[0]


class LiveBackend:
    def __init__(self,settings):
        self.settings=deepcopy(settings);self.budget=ReadBudget(85,max_requests=24)
        self.hashes={name:sha256(_owned_bytes(Path(settings[name]),16384)).hexdigest() for name in SOURCE_PATHS}
        self.token=_owned_bytes(Path(settings['token_file']),4096).decode().strip()
        self.transport=TelemetryTransport(base=settings['openhab_base'],token_reader=lambda:self.token,budget=self.budget)
        self.journal_dsn=bounded_journal_dsn(_owned_bytes(Path(settings['journal_dsn_file']),4096).decode().strip())
        self.forecast_dsn=bounded_journal_dsn(_owned_bytes(Path(settings['forecast_dsn_file']),4096).decode().strip())
        from thermal_temperature_runtime import _configured_sensor_epochs
        self.env=dict(THERMAL_TEMP_POLICY=settings['native_policy'],THERMAL_TEMP_DB_CONFIG=settings['native_db_config'])
        self.epochs=_configured_sensor_epochs(self.env)
    def verify_unchanged(self):
        self.budget.remaining()
        if any(sha256(_owned_bytes(Path(self.settings[name]),16384)).hexdigest()!=digest for name,digest in self.hashes.items()):
            raise ValueError('original publication source configuration changed')
    def _connect(self,dsn):
        import psycopg2
        self.budget.begin()
        try:connection=psycopg2.connect(dsn)
        except psycopg2.Error:raise ValueError('bounded original database source unavailable') from None
        try:self.budget.remaining();return connection
        except BaseException:connection.close();raise
    def collect(self,*,issue,known_at):
        import psycopg2
        try:return self._collect(issue=issue,known_at=known_at)
        except psycopg2.Error:raise ValueError('bounded original database source unavailable') from None
    def _collect(self,*,issue,known_at):
        from .forecast_history import fetch_pending_origin_forecast_with_receipts
        from .action_history import fetch_origin_actions
        from thermal_temperature_runtime import collect_v2,shadow_temperatures_v2
        from .temperature_history import STREAMS
        from .dataset import latent_mass_from_series
        from psycopg2.extensions import make_dsn
        known_at,issue=map(_utc,(known_at,issue))
        if not timedelta(0)<issue-known_at<=timedelta(seconds=60) or known_at>_clock():raise ValueError('bounded actual pre-issue collection clock required')
        forecast=fetch_pending_origin_forecast_with_receipts(lambda:self._connect(self.forecast_dsn),origin=issue,horizon_hours=24,available_by=known_at)
        if forecast is None:raise ValueError('original archived weather unavailable')
        saved=[]
        def grid(stream,targets,assessed):
            role=next(role for role,values in STREAMS.items() if values[0]==stream)
            request=dict(stream=stream,targets=[at.isoformat() for at in targets],assessed_at=assessed.isoformat(),receipt_version=2,sensor_epoch=self.epochs[role])
            return collect_v2(request,config_path=self.settings['native_db_config'],policy_path=self.settings['native_policy'],
                connection_factory=lambda config:self._connect(bounded_journal_dsn(make_dsn(**config))))
        selected=shadow_temperatures_v2(known_at,grid,sensor_epochs=self.epochs,origin_observer=saved.append)
        current={role:deepcopy(value['current']) for role,value in selected.items()}
        # Match the established causal initial-state observer. Retain the
        # original raw grid and receipt clocks; only the derived mass value
        # changes, and origin replay independently recomputes it.
        history=list(selected['mass']['history']);reading=current['mass']
        if not history or reading['at']>history[-1][0]:history.append((reading['at'],reading['value']))
        latent=latent_mass_from_series(history)
        if latent is not None:current['mass']['value']=latent[1]
        snapshot=fetch_origin_actions(lambda:self._connect(self.journal_dsn),origin=known_at)
        # Freeze knowledge actually collected before issue; do not query future
        # journal creation times or claim that later physical actions occurred.
        snapshot=deepcopy(snapshot);snapshot['origin']=issue
        self.budget.remaining()
        return dict(forecast=forecast,current=current,
            origin_temperatures=saved[0],action_snapshot=snapshot)
    def put(self,item,state,*,preflight=None):return self.transport.put(item,state,preflight=preflight)
    def persisted(self,item,state,*,since):return self.transport.persisted(item,state,since=since,until=_clock())


WITHDRAW_SCHEMA='earthship-installed-shade-withdraw-config/v1'
RAW_WITHDRAW_SCHEMA='earthship-installed-shade-withdraw-config/v2'
WITHDRAW_FIELDS={'schema','openhab_base','token_file','evidence_directory'}


def load_raw_withdraw_settings(path):
    return load_withdraw_settings(path,_version=2)


def load_withdraw_settings(path,*,_version=1):
    path=Path(path);_private_directory(path.parent);value=_read_private(path)
    if not isinstance(value,dict) or set(value)!=WITHDRAW_FIELDS or value['schema']!=(RAW_WITHDRAW_SCHEMA if _version==2 else WITHDRAW_SCHEMA) or value['openhab_base'] not in BASES:
        raise ValueError('closed private withdrawal configuration required')
    for name in ('token_file','evidence_directory'):
        raw=value[name]
        if not isinstance(raw,str) or not 1<=len(raw)<=1024:raise ValueError('bounded withdrawal source path required')
        target=Path(raw)
        if not target.is_absolute() or target.resolve()!=target:raise ValueError('resolved withdrawal source required')
        if name=='evidence_directory':_private_directory(target)
        else:_private_directory(target.parent);_owned_bytes(target,4096)
    return deepcopy(value)


class WithdrawalBackend:
    def __init__(self,settings):
        self.settings=deepcopy(settings);self.budget=ReadBudget(25,max_requests=8)
        raw=_owned_bytes(Path(settings['token_file']),4096);self.token_sha256=sha256(raw).hexdigest();token=raw.decode().strip()
        self.transport=TelemetryTransport(base=settings['openhab_base'],token_reader=lambda:token,budget=self.budget)
    def verify_unchanged(self):
        self.budget.remaining()
        if sha256(_owned_bytes(Path(self.settings['token_file']),4096)).hexdigest()!=self.token_sha256:
            raise ValueError('withdrawal credential changed')
    def put(self,item,state,*,preflight=None):
        if item!=PUBLICATION_ITEM:raise ValueError('withdrawal targets main thermal telemetry only')
        def final_preflight():
            self.verify_unchanged()
            if preflight:preflight()
        self.verify_unchanged();self.transport.put(item,state,preflight=final_preflight)
    def persisted(self,item,state,*,since):
        if item!=PUBLICATION_ITEM:raise ValueError('withdrawal receipt must be main thermal telemetry')
        self.verify_unchanged()
        receipt=self.transport.persisted(item,state,since=since,until=_utc(_clock()))
        self.verify_unchanged();return receipt
