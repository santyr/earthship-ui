"""Three read-only shadow Item states. No command, rule or actuator interface."""
from .contracts import canonical,digest,finite,identity,instant

ITEMS=('Forecast_Local_Shadow_JSON','Forecast_Comparison_JSON','Forecast_Provider_Status_JSON')
MAX_BYTES=65536
FIELDS={'version','schema','provider','mode','generation','generatedAt','decisionAt','status','reason','source','model','hours','automaticActuation'}


def seal_payload(body):
    value=dict(body,generation=identity(body))
    validate_payload(value)
    return value


def validate_payload(value):
    if not isinstance(value,dict) or set(value)!=FIELDS or type(value['version']) is not int or value['version']!=2 or value['schema']!='earthship-weather-provider-shadow/v2':
        raise ValueError('closed versioned shadow payload required')
    if value['provider']!='weathernext3' or value['mode']!='shadow' or value['automaticActuation'] is not False:
        raise ValueError('WeatherNext shadow-only authority required')
    digest(value['generation'])
    if value['generation']!=identity({k:v for k,v in value.items() if k!='generation'}):raise ValueError('shadow generation differs')
    issued,generated=map(instant,(value['decisionAt'],value['generatedAt']))
    if generated<issued:raise ValueError('shadow completion precedes decision')
    if value['status'] not in ('READY','UNAVAILABLE') or value['reason'] not in ('NONE','NO_ELIGIBLE_SOURCE','UNTRAINED','MODEL_UNAVAILABLE'):
        raise ValueError('explicit shadow status required')
    source=value['source'];hours=value['hours'];model=value['model']
    if not isinstance(hours,list) or len(hours)>360:raise ValueError('bounded shadow hours required')
    if value['status']=='READY':
        if not isinstance(source,dict) or set(source)!={'snapshotSha256','runId','initializedAt','firstSeenAt','ingestedAt','timezone'} or not hours:
            raise ValueError('complete original source metadata required')
        digest(source['snapshotSha256'])
        init,seen,ingested=map(instant,(source['initializedAt'],source['firstSeenAt'],source['ingestedAt']))
        if not init<=seen<=ingested<=issued or (issued-init).total_seconds()>86400:raise ValueError('source unavailable at decision')
        from zoneinfo import ZoneInfo
        ZoneInfo(source['timezone'])
        if not isinstance(source['runId'],str) or not 1<=len(source['runId'])<=128:raise ValueError('bounded source run required')
    elif source is not None or hours:raise ValueError('unavailable source cannot carry forecasts')
    if not isinstance(model,dict) or set(model)!={'status','sha256','fittedAt','trainingEnd','sampleCount','targetDates','validation'}:
        raise ValueError('closed model summary required')
    if model['status'] not in ('UNTRAINED','SHADOW_ONLY','UNAVAILABLE') or model['validation'] is not None:raise ValueError('unqualified shadow model required')
    for name,bound in (('sampleCount',50000),('targetDates',366)):
        if type(model[name]) is not int or not 0<=model[name]<=bound:raise ValueError('bounded training support required')
    if model['targetDates']>model['sampleCount']:raise ValueError('target dates exceed source pairs')
    if model['status']=='SHADOW_ONLY':
        digest(model['sha256'])
        if not instant(model['trainingEnd'])<=instant(model['fittedAt'])<=issued or model['sampleCount']==0:raise ValueError('original model clocks required')
    elif any(model[k] is not None for k in ('sha256','fittedAt','trainingEnd')) or model['sampleCount'] or model['targetDates']:
        raise ValueError('untrained/unavailable model cannot carry training claims')
    previous=issued
    for row in hours:
        if not isinstance(row,dict) or set(row)!={'at','rawC','localC'}:raise ValueError('closed shadow temperature row required')
        at=instant(row['at'])
        if not previous<at or (at-init).total_seconds()>360*3600:raise ValueError('ordered native forecast horizon required')
        previous=at
        if not finite(row['rawC']) or (row['localC'] is not None and not finite(row['localC'])):raise ValueError('finite or absent temperature required')
        if model['status']!='SHADOW_ONLY' and row['localC'] is not None:raise ValueError('untrained model cannot predict')
    if len(canonical(value))>=MAX_BYTES:raise ValueError('shadow payload exceeds Item bound')
    return value


def publish_item(item,payload,put_state):
    if item not in ITEMS:raise ValueError('only shadow Item state publication is allowed')
    raw=canonical(validate_payload(payload)).decode()
    put_state(item,raw)


def publish_bundle(payload,put_state):
    # Validate/serialize everything before I/O; status is the final commit marker.
    raw=canonical(validate_payload(payload)).decode()
    for item in ITEMS:put_state(item,raw)
