"""Explicit historical candidates in the existing read-only shadow owner."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from math import sin,cos,pi,exp
from zoneinfo import ZoneInfo
from bisect import bisect_left
import json
from weather_source_files import _read
from .contracts import identity,instant,finite
from .site_calibration import _model as temperature_model
from .weather_response import validate_model as wind_model,predict_gain

SELECTION_FIELDS={'schema','kind','experiment_path','experiment_file_sha256','experiment_receipt_sha256','model_path','model_file_sha256','model_sha256','target_dates','sensor_epoch','available_at','automatic_actuation','selection_sha256'}


def load_selection(path,*,kind,now,sensor_epoch=None):
    value=json.loads(_read(path,16384))
    if set(value)!=SELECTION_FIELDS or value['schema']!='earthship-historical-weather-selection/v1' or value['kind']!=kind or value['automatic_actuation'] is not False or value['selection_sha256']!=identity({k:v for k,v in value.items() if k!='selection_sha256'}):raise ValueError('explicit unchanged historical weather selection required')
    experiment_path=Path(value['experiment_path']);model_path=Path(value['model_path'])
    if not experiment_path.is_absolute() or model_path.parent!=experiment_path.parent:raise ValueError('owned original historical candidate required')
    raw=_read(experiment_path,262144);raw_model=_read(model_path,4*1024**2)
    if sha256(raw).hexdigest()!=value['experiment_file_sha256'] or sha256(raw_model).hexdigest()!=value['model_file_sha256']:raise ValueError('historical candidate originals changed')
    original=json.loads(raw);model=json.loads(raw_model)
    if original['receipt_sha256']!=value['experiment_receipt_sha256'] or original['receipt_sha256']!=identity({k:v for k,v in original.items() if k!='receipt_sha256'}) or original['final_models'][kind]!=value['model_sha256'] or model['model_sha256']!=value['model_sha256']:raise ValueError('historical experiment/model binding differs')
    if kind=='outdoor_temperature_c':
        temperature_model(model);report=original['reports'][kind]
        if model['kind']!=kind or report['pairs']<3 or report['target_days']<2 or not report['candidate_mae']<report['baseline_mae'] or model['correction_limit']>6:raise ValueError('improved bounded historical outdoor model required')
        if model['feature_names']!=sorted(['google_c','lead_days','hour_sin','hour_cos','season_sin','season_cos','origin_bias_decay_c']):raise ValueError('original historical outdoor feature contract required')
        names=('site_calibration.py','historical_pairs.py','contracts.py')
        if value['sensor_epoch']!=sensor_epoch:raise ValueError('selected outdoor sensor epoch differs')
    elif kind=='wind_m_s':
        wind_model(model);report=original['reports'][kind]
        if model['kind']!=kind or report.get('selected') is not True or not report['candidate']['mae']<report['baseline']['mae']:raise ValueError('improved historical wind model required')
        names=('weather_response.py','contracts.py')
        if value['sensor_epoch'] is not None:raise ValueError('numeric wind history cannot infer a sensor epoch')
    else:raise ValueError('supported historical serving kind required')
    if model['schema'] in ('earthship-site-calibration/v2','earthship-site-weather-gain/v2'):
        names+=('weights.py',)
    for name in names:
        key='openhab/scripts/weather_learning/'+name
        if original['runtime_manifest'].get(key)!=sha256((Path(__file__).parent/name).read_bytes()).hexdigest():raise ValueError('historical numerical or training-feature runtime changed')
    if not instant(model['trained_at'])<=instant(value['available_at'])<=now<instant(model['trained_at'])+timedelta(days=14):raise ValueError('historical candidate unavailable or expired')
    if type(value['target_dates']) is not int or not 1<=value['target_dates']<=366:raise ValueError('bounded actual training target dates required')
    return model,value


def temperature_features(target,*,origin,origin_bias_c,timezone_name):
    local=target.target_at.astimezone(ZoneInfo(timezone_name));angle=2*pi*(local.hour+local.minute/60)/24;season=2*pi*local.timetuple().tm_yday/365.25;lead=(target.target_at-origin).total_seconds()/3600
    if not 0<lead<=360:raise ValueError('bounded original future temperature target required')
    return dict(google_c=target.mean_c,lead_days=lead/24,hour_sin=sin(angle),hour_cos=cos(angle),season_sin=sin(season),season_cos=cos(season),origin_bias_decay_c=origin_bias_c*exp(-lead/24))


class HistoricalPredictor:
    def __init__(self,model,*,now,timezone_name,origin_bias_c,sensor_epoch,target_dates,selection=None):
        if not finite(origin_bias_c):raise ValueError('qualified finite origin temperature bias required')
        self.model=model;self.now=now;self.zone=timezone_name;self.bias=origin_bias_c;self.epoch=sensor_epoch
        from .provenance import issue_provenance
        self.issue_provenance=issue_provenance(model,historical=True,selection_original_sha256=None if selection is None else selection['selection_sha256'])
        self.summary=dict(status='SHADOW_ONLY',sha256=model['model_sha256'],fittedAt=model['trained_at'],trainingEnd=model['training_end'],sampleCount=model['sample_count'],targetDates=target_dates,validation=None)

    def predict(self,target,*,sensor_epoch):
        from .site_calibration import predict
        if sensor_epoch!=self.epoch:raise ValueError('outdoor serving sensor epoch differs')
        features=temperature_features(target,origin=self.now,origin_bias_c=self.bias,timezone_name=self.zone)
        return dict(value_c=predict(self.model,features,baseline=target.mean_c,origin=self.now))


def prepare_temperature(archive,state,*,now,site,policy,sensor_epoch,db_config,horizon):
    from .features import local_temperature_outcome
    from hourly_temperature_runtime import read_db_config
    from weather_temperature_history import fetch_temperature_grid_v2
    import psycopg2
    model,selection=load_selection(state.root/'historical-outdoor.json',kind='outdoor_temperature_c',now=now,sensor_epoch=sensor_epoch)
    end=(now+timedelta(hours=horizon)).replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    snapshot=archive.eligible_snapshot(now,end,required_variables={'station_head_temperature_2m'})
    if snapshot is None:return None
    if snapshot['site']!=site.__dict__:raise ValueError('historical serving site differs')
    values=sorted((instant(p['valid_at']),p['value']) for p in snapshot['points'] if p['variable']=='station_head_temperature_2m' and p['statistic']=='mean' and finite(p['value']))
    times=[at for at,_ in values];i=bisect_left(times,now)
    if i==0 or i==len(values):raise ValueError('original Google origin interpolation unavailable')
    a,b=values[i-1],values[i];fraction=(now-a[0]).total_seconds()/(b[0]-a[0]).total_seconds();google=a[1]*(1-fraction)+b[1]*fraction
    config=read_db_config(db_config)
    labels=fetch_temperature_grid_v2(lambda:psycopg2.connect(**config,connect_timeout=3),targets=[now],assessed_at=now,stream='outdoor',policy=policy,sensor_epoch=sensor_epoch)
    label=dict(labels).get(now)
    if label is None:raise ValueError('qualified original outdoor origin required')
    outcome=local_temperature_outcome(label,target_at=now,assessed_at=now,sensor_epoch=sensor_epoch)
    return HistoricalPredictor(model,now=now,timezone_name=site.timezone,origin_bias_c=outcome.value_c-google,sensor_epoch=sensor_epoch,target_dates=selection['target_dates'],selection=selection)


def publish_wind(archive,state,*,payload,now):
    model,selection=load_selection(state.root/'historical-wind.json',kind='wind_m_s',now=now)
    if payload['status']!='READY':return 'source_unavailable'
    snapshot=archive.read(payload['source']['snapshotSha256']);points={}
    for p in snapshot['points']:
        if p['variable']=='wind_speed_10m' and p['statistic']=='mean':
            if p['unit']!='m s-1' or p['period_seconds']!=0:raise ValueError('native instantaneous wind unit required')
            points[p['valid_at']]=p['value']
    start=now.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1);rows=[]
    while start+timedelta(hours=1)<=now+timedelta(hours=24):
        end=start+timedelta(hours=1);a,b=points.get(start.isoformat()),points.get(end.isoformat());raw=None if not all(finite(v) and v>=0 for v in (a,b)) else (a+b)/2
        rows.append(dict(start=start.isoformat(),end=end.isoformat(),raw_m_s=raw,local_m_s=None if raw is None else predict_gain(model,raw,origin=now)));start=end
    value=dict(schema='earthship-site-wind-shadow/v1',issued_at=now.isoformat(),generated_at=datetime.now(timezone.utc).isoformat(),valid_until=(now+timedelta(minutes=90)).isoformat(),source_snapshot_sha256=payload['source']['snapshotSha256'],
        model_sha256=model['model_sha256'],training_end=model['training_end'],trained_at=model['trained_at'],target='hour_mean_local_station_wind_m_s',baseline='trapezoid_of_adjacent_native_instantaneous_forecasts',hours=rows,
        measurement_health_qualified=False,prospective_score=False,automatic_actuation=False)
    value['view_sha256']=identity(value)
    from .correction_monitor import retain_wind_issue
    retain_wind_issue(state,value,model=model,selection=selection,snapshot=snapshot)
    state._write(state.root/'site-wind.json',value);return 'published_read_only'
