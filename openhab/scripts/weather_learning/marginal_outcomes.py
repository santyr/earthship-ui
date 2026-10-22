"""Original marginal labels with actual first acquisition, never backdated reads."""
from datetime import datetime,timedelta,timezone
from .contracts import canonical,digest,finite,identity,instant
from .evidence import utc
from .probabilistic import _Frozen,_freeze,KINDS
from .features import _jsonable,local_temperature_outcome
from .shadow import _read


class MarginalObservation(_Frozen):
    __slots__=()


def _observation(kind,start,end,value,acquired,policy,quality,original,*,qualified,unit):
    start,end,acquired=map(utc,(start,end,acquired));digest(policy)
    if (kind not in KINDS or not finite(value) or end>acquired or
            (start!=end if kind=='temperature' else end-start!=timedelta(hours=1) or start.minute or start.second or start.microsecond) or
            kind!='temperature' and value<0):raise ValueError('original mature marginal point/window and actual acquisition required')
    body=dict(schema='earthship-original-marginal-observation/v1',kind=kind,target_start=start.isoformat(),target_end=end.isoformat(),value=value,unit=unit,
        available_at=acquired.isoformat(),observation_policy_sha256=policy,quality=quality,original=_jsonable(original),measurement_health_qualified=qualified,
        physical_calibration_qualified=False,automatic_actuation=False)
    if len(canonical(body))>16*1024**2:raise ValueError('bounded original marginal observation required')
    return _freeze(MarginalObservation,body,'observation_sha256')


def temperature_observation(metadata,*,target,acquired_at,sensor_epoch,observation_policy_sha256):
    from daily_temperature_runtime import SOURCE_POLICY
    from .probabilistic_population import _temperature_quality
    target,acquired=map(utc,(target,acquired_at));raw=_jsonable(metadata);point=dict(raw)
    for key in ('receivedAt','storedAt','validUntil'):point[key]=instant(point[key])
    outcome=local_temperature_outcome(point,target_at=target,assessed_at=acquired,sensor_epoch=sensor_epoch)
    quality=_temperature_quality(raw|dict(sourceModel=SOURCE_POLICY['model'],sourceSensorId=SOURCE_POLICY['sensor_id']))
    return _observation('temperature',target,target,outcome.value_c,acquired,observation_policy_sha256,quality,raw,qualified=True,unit='degC')


def _wind_rows(original,start,end,acquired):
    from .wind_history import ITEM,MAX_BYTES
    from thermal_model.origin_capture import _object
    import json
    if original.get('schema')=='earthship-station-wind-http-source/v1':
        if (original.get('item')!=ITEM or original.get('unit')!='mph' or original.get('query_start')!=(start-timedelta(seconds=120)).isoformat() or
                original.get('query_end')!=end.isoformat() or not instant(original['assessment_started_at'])<=instant(original['requested_at'])<=instant(original['received_at'])<=acquired or
                original.get('automatic_actuation') is not False or not isinstance(original.get('raw'),str) or len(original['raw'].encode())>MAX_BYTES):raise ValueError('original wind HTTP acquisition differs')
        def reject(_):raise ValueError('finite original wind response required')
        body=json.loads(original['raw'],object_pairs_hook=_object,parse_constant=reject)
        if body.get('name')!=ITEM or body.get('unit')!='mph' or not isinstance(body.get('data'),list) or len(body['data'])>10000:raise ValueError('original wind response differs')
        values=[]
        for row in body['data']:
            if not finite(row.get('time')):raise ValueError('finite original wind time required')
            at=datetime.fromtimestamp(row['time']/1000,timezone.utc);state=row.get('state')
            if not isinstance(state,str) or len(state)>128:raise ValueError('bounded original wind state required')
            words=state.split()
            if len(words)>2 or len(words)==2 and words[1]!='mph':raise ValueError('original wind unit differs')
            try:value=float(words[0])
            except (ValueError,IndexError):value=None
            values.append((at,value if finite(value) else None))
    else:
        if set(original)!={'unit','rows'} or original['unit']!='mph' or not isinstance(original['rows'],list) or len(original['rows'])>10000:raise ValueError('original numeric wind rows required')
        values=[(instant(at),value) for at,value in original['rows']]
    rows=[]
    for at,value in values:
        if not start-timedelta(seconds=120)<=at<=end or rows and at<rows[-1][0]:raise ValueError('ordered original wind window required')
        if rows and at==rows[-1][0]:
            if rows[-1][1]!=value:rows[-1]=(at,None)
        else:rows.append((at,value))
    return rows


def wind_observation(value,*,acquired_at,observation_policy_sha256):
    from .correction_monitor import wind_outcome
    from .probabilistic_issue import wind_context
    start,end,acquired=map(instant,(value['start'],value['end'],utc(acquired_at).isoformat()));original=value['original']
    if value['source_sha256']!=identity(original) or not end==start+timedelta(hours=1) or instant(value['available_at'])>acquired or instant(value['assessed_at'])>acquired or value.get('measurement_health_qualified') is not False:raise ValueError('original numeric wind evidence required')
    rows=_wind_rows(original,start,end,acquired);rebuilt=wind_outcome(rows,start=start,assessed_at=acquired,source_available_at=acquired,unit='mph')
    if rebuilt is None or not finite(value['value']) or abs(rebuilt['value']-value['value'])>1e-12 or rebuilt['coverage_seconds']!=value['coverage_seconds']:raise ValueError('original wind value replay differs')
    quality=wind_context(decision=acquired).quality_at(acquired)
    return _observation('wind',start,end,rebuilt['value'],acquired,observation_policy_sha256,quality,value,qualified=False,unit='m_s')


def solar_observation(source,*,start,acquired_at,observation_policy_sha256):
    from .solar_shadow import _source
    from .correction_monitor import solar_outcome
    source=_source(source);start,acquired=map(utc,(start,acquired_at));value=solar_outcome(source,start=start)
    if instant(source['assessed_at'])>acquired:raise ValueError('original solar proxy acquisition differs')
    quality=dict(provenance='source_qualified_lux_to_solar_proxy',stream_epoch=source['stream_epoch'],policy=source['policy'],source_item='Weather_Radiation_Evidence_JSON',physical_irradiance_calibration_qualified=False)
    return _observation('solar_proxy',start,start+timedelta(hours=1),value['value'],acquired,observation_policy_sha256,quality,source,qualified=True,unit='W_m2_reported_proxy')


def load_observation(value):
    if (not isinstance(value,dict) or value.get('observation_sha256')!=identity({k:v for k,v in value.items() if k!='observation_sha256'}) or
            value.get('schema')!='earthship-original-marginal-observation/v1' or value.get('kind') not in KINDS):raise ValueError('unchanged original marginal observation required')
    args=dict(acquired_at=instant(value['available_at']),observation_policy_sha256=value['observation_policy_sha256'])
    if value['kind']=='temperature':obj=temperature_observation(value['original'],target=instant(value['target_end']),sensor_epoch=value['quality']['sensorEpoch'],**args)
    elif value['kind']=='wind':obj=wind_observation(value['original'],**args)
    else:obj=solar_observation(value['original'],start=instant(value['target_start']),**args)
    if obj.to_dict()!=value:raise ValueError('original marginal observation replay differs')
    return obj


def observation_key(work,policy):
    digest(policy)
    if not isinstance(work,dict) or set(work)!={'kind','start','end'} or work['kind'] not in KINDS:raise ValueError('closed original observation work required')
    start,end=map(instant,(work['start'],work['end']))
    if (start!=end if work['kind']=='temperature' else end-start!=timedelta(hours=1)):raise ValueError('matching observation point/window required')
    return identity(dict(work=work,observation_policy_sha256=policy))


def captured_observations(state,work,*,now,observation_policy_sha256,read,apply,clock,guard=lambda:None):
    now=utc(now);policy=digest(observation_policy_sha256)
    if type(apply) is not bool or not isinstance(work,list) or len(work)>8 or not callable(read):raise ValueError('bounded explicit marginal label capture required')
    result={}
    for request in work:
        guard();key=observation_key(request,policy)
        if key in result:continue
        path=state.root/'weather-outcomes'/(key+'.marginal.json')
        try:obj=load_observation(_read(path,16*1024**2))
        except FileNotFoundError:
            requested=max(now,utc(clock()));obj=read(request,now);guard();finished=utc(clock())
            if finished<requested:raise ValueError('actual marginal capture clock moved backwards')
            if obj is None:continue
            if not isinstance(obj,MarginalObservation):raise ValueError('original marginal observation adapter required')
            obj=load_observation(obj.to_dict());value=obj.to_dict()
            if not requested<=instant(value['available_at'])<=finished:raise ValueError('actual marginal acquisition cannot be backdated')
            if (value['kind'],value['target_start'],value['target_end'],value['observation_policy_sha256'])!=(request['kind'],request['start'],request['end'],policy):raise ValueError('matching original marginal capture required')
            if apply:state._write(path,value,immutable=True)
        value=obj.to_dict()
        if (value['kind'],value['target_start'],value['target_end'],value['observation_policy_sha256'])!=(request['kind'],request['start'],request['end'],policy) or instant(value['available_at'])>max(now,utc(clock())):raise ValueError('original marginal capture scope or clock differs')
        result[key]=obj
    return result
