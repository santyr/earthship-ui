"""Retrospective Google/local examples with explicit assumed publication latency.

Temperature labels retain actual receipt/hardware evidence. Forecast origins
here are experimental clocks, never a reconstruction of operational issuance.
"""
from datetime import timedelta
from math import sin,cos,pi,exp
from zoneinfo import ZoneInfo
from .contracts import identity,instant,finite
from .historical import verify_history

KINDS={'outdoor_temperature_c':'outdoor','indoor_temperature_c':'indoor','wall_temperature_c':'north_wall'}


def _c(label):return (label['temperatureF']-32)*5/9


def _validate_label(label,target):
    if label.get('at')!=target.isoformat() or not finite(label.get('temperatureF')) or not -40<=label['temperatureF']<=140:
        raise ValueError('finite original historical temperature target required')
    if label.get('provenance')=='persisted_numeric_state':
        from .numeric_history import MAX_STATE_AGE
        age=target-instant(label['storedAt'])
        if (label.get('receiptVersion') is not None or label.get('sensorEpoch') is not None or label.get('receivedAt') is not None or
            label.get('validUntil') is not None or label.get('measurement_health_qualified') is not False or
            not timedelta(0)<=age<=MAX_STATE_AGE or label.get('stateAgeSeconds')!=age.total_seconds()):
            raise ValueError('explicit unqualified numeric history provenance required')
    elif (label.get('receiptVersion') not in (1,2) or
        not instant(label['receivedAt'])<=instant(label['storedAt'])<=target<instant(label['validUntil'])):
        raise ValueError('qualified historical temperature receipt required')


def _row(kind,*,source,origin,target,label,features,baseline,origin_labels=None,availability_basis='retrospective_assumed_full_cycle_9h'):
    _validate_label(label,target)
    row=dict(schema='earthship-historical-learning-pair/v1',kind=kind,origin=origin.isoformat(),target_at=target.isoformat(),
        lead_hours=(target-origin).total_seconds()/3600,availability_basis=availability_basis,
        forecast_sha256=source,features=features,baseline=baseline,outcome=_c(label),label=label,origin_labels=origin_labels or {},
        prospective_score=False,automatic_actuation=False)
    row['pair_sha256']=identity(row);return row


def pair_temperatures(snapshot,measurements,*,target_end=None,allow_recorded_availability=False):
    source=verify_history(snapshot)
    if source['historical'] is not True and not allow_recorded_availability:raise ValueError('explicit historical forecast required')
    pin=identity(source)
    if snapshot.get('snapshot_sha256',pin)!=pin:raise ValueError('original historical snapshot identity differs')
    init=instant(source['initialized_at']);origin=init+timedelta(hours=9);basis='retrospective_assumed_full_cycle_9h'
    if source['historical'] is not True:
        available=instant(source['ingestion_completed_at']);origin=available.replace(minute=0,second=0,microsecond=0)
        if origin<available:origin+=timedelta(hours=1)
        basis='retrospective_recorded_ingestion_next_whole_hour'
    zone=ZoneInfo(source['site']['timezone']);hours={}
    for p in source['points']:
        if p['statistic']=='mean':hours.setdefault(p['valid_at'],{})[p['variable']]=p['value']
    origin_labels=measurements.get(origin.isoformat(),{})
    air=origin_labels.get('indoor');mass=origin_labels.get('north_wall');outside=origin_labels.get('outdoor')
    thermal=all(v is not None for v in (air,mass,outside))
    if thermal:
        for value in (air,mass,outside):
            _validate_label(value,origin)
            if value['at']!=origin.isoformat() or instant(value['storedAt'])>origin:raise ValueError('thermal origin evidence arrived after origin')
    origin_google=hours.get(origin.isoformat(),{}).get('station_head_temperature_2m')
    origin_bias=None
    if outside is not None and finite(origin_google):
        _validate_label(outside,origin);origin_bias=_c(outside)-origin_google
    rows=[];temp_total=solar_total=0.;forcing_complete=True
    for offset in range(1,352):
        target=origin+timedelta(hours=offset)
        if target_end is not None and target>=target_end:break
        forecast=hours.get(target.isoformat(),{});labels=measurements.get(target.isoformat(),{})
        temperature=forecast.get('station_head_temperature_2m');radiation=forecast.get('surface_solar_radiation_downwards_1hr')
        if finite(temperature) and finite(radiation) and radiation>=0:
            temp_total+=temperature;solar_total+=radiation/1000
        else:forcing_complete=False
        local=target.astimezone(zone);angle=2*pi*(local.hour+local.minute/60)/24;season=2*pi*local.timetuple().tm_yday/365.25
        if origin_bias is not None and finite(temperature) and labels.get('outdoor') is not None and (offset<=72 or offset in (96,120,144,168,240,336)):
            features=dict(google_c=temperature,lead_days=offset/24,hour_sin=sin(angle),hour_cos=cos(angle),season_sin=sin(season),season_cos=cos(season),origin_bias_decay_c=origin_bias*exp(-offset/24))
            rows.append(_row('outdoor_temperature_c',source=pin,origin=origin,target=target,label=labels['outdoor'],features=features,baseline=temperature,origin_labels={'outdoor':outside},availability_basis=basis))
        if thermal and forcing_complete and offset<=24:
            for kind,stream,baseline in (('indoor_temperature_c','indoor',_c(air)),('wall_temperature_c','north_wall',_c(mass))):
                if labels.get(stream) is None:continue
                features=dict(air_origin_c=_c(air),mass_origin_c=_c(mass),outdoor_origin_c=_c(outside),
                    google_mean_c=temp_total/offset,solar_kwh_m2=solar_total,lead_days=offset/24,hour_sin=sin(angle),hour_cos=cos(angle))
                rows.append(_row(kind,source=pin,origin=origin,target=target,label=labels[stream],features=features,baseline=baseline,
                    origin_labels={key:origin_labels[key] for key in ('indoor','north_wall','outdoor')},availability_basis=basis))
    return rows
