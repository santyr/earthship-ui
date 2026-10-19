"""Inactive Google-only provider boundary; availability is not release authority.

Original sources are rederived before conversion. No network fallback, legacy
state, Kalman seeding, fitting, publication or equipment operation lives here.
"""
from datetime import date,datetime,time,timedelta,timezone
import json,sqlite3
from zoneinfo import ZoneInfo

from .config import Site
from .contracts import canonical,identity,instant
from .evidence import utc
from .features import temperature_targets
from .normalize import daily_solar_energy

TEMPERATURE='station_head_temperature_2m'
GHI='surface_solar_radiation_downwards_1hr'
DIRECT='total_sky_direct_solar_radiation_at_surface_1hr'
RAIN='total_precipitation_1hr'
WIND='wind_speed_10m'
CLOUD='total_cloud_cover'
REQUIRED=frozenset({TEMPERATURE,GHI,DIRECT,RAIN,WIND,CLOUD})


class ProviderSnapshot:
    __slots__=('_raw',)
    def __init__(self,*args,**kwargs):raise TypeError('construct provider through original archive selection')
    def __setattr__(self,name,value):raise AttributeError('provider snapshot is immutable')
    def to_dict(self):return json.loads(self._raw)


def _freeze(body):
    body['provider_snapshot_sha256']=identity(body)
    value=object.__new__(ProviderSnapshot)
    object.__setattr__(value,'_raw',canonical(body))
    return value


def _body(decision,required_horizon,site,variables):
    return dict(schema='earthship-weathernext-provider/v1',provider='weathernext3',
        decision_at=decision.isoformat(),required_horizon_seconds=required_horizon.total_seconds(),
        timezone=site.timezone,required_variables=sorted(variables),status='UNAVAILABLE',reason='NO_ELIGIBLE_SOURCE',
        source=None,issue_sha256=None,learning_namespace='weathernext3-temperature-v1',
        model=dict(status='UNTRAINED',sha256=None,parent_artifacts=[]),hours=[],days=[],
        solar_context=None,solar_context_reason='NOT_PROVIDED',
        release_authorized=False,automatic_actuation=False)


def _daily(points,days,zone):
    # Instantaneous temperature belongs to [midnight, next midnight); native
    # one-hour energy/depth accumulations belong to (midnight, next midnight].
    by_variable={}
    for point in points:
        by_variable.setdefault(point['variable'],{})[instant(point['valid_at'])]=point['value']
    result=[]
    for day_string in days:
        day=date.fromisoformat(day_string)
        start=datetime.combine(day,time.min,zone).astimezone(timezone.utc)
        end=datetime.combine(day+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
        def values(variable,interval=False):
            rows=by_variable.get(variable,{})
            at=start+timedelta(hours=1) if interval else start
            stop=end+timedelta(hours=1) if interval else end
            selected=[]
            while at<stop:
                if rows.get(at) is None:return None
                selected.append(rows[at]);at+=timedelta(hours=1)
            return selected
        temperatures=values(TEMPERATURE);rain=values(RAIN,True)
        result.append(dict(date=day_string,
            high_f=None if temperatures is None else max(temperatures)*9/5+32,
            low_f=None if temperatures is None else min(temperatures)*9/5+32,
            precip_sum_in=None if rain is None else sum(rain)/25.4,
            solar_kwh_m2=daily_solar_energy(points,day,zone.key,variable=GHI),
            direct_solar_kwh_m2=daily_solar_energy(points,day,zone.key,variable=DIRECT)))
    return result


def _solar_schedule(source,*,decision,site):
    """Retain exact validated native daylight; no local astronomical substitute."""
    from astro_forecast_context import validate
    if not isinstance(source,dict) or set(source)!={'raw','available_at'}:
        raise ValueError('original Astro state and availability required')
    available=utc(source['available_at'])
    if available>decision:raise ValueError('Astro state unavailable at decision')
    checked=validate(source['raw'],origin=decision,latitude=site.latitude,longitude=site.longitude,timezone_name=site.timezone)
    if instant(checked['recordedAt'])>available:raise ValueError('Astro acquisition precedes its original source')
    return dict(sourceSha256=checked['sourceSha256'],recordedAt=checked['recordedAt'],availableAt=available.isoformat(),
        days=json.loads(source['raw'])['days'])


def load_production_forecast(archive,*,decision_at,required_horizon,site,required_variables=REQUIRED,astro_source=None):
    """Prepare a read-only source for future production integration.

    A missing/stale/incomplete Google source is UNAVAILABLE. A malformed selected
    original is INVALID_SOURCE. Neither condition makes an external request or
    selects another provider. The returned object grants no release authority.
    """
    decision=utc(decision_at)
    if not isinstance(site,Site) or not isinstance(required_horizon,timedelta) or not timedelta(0)<required_horizon<=timedelta(hours=336):
        raise ValueError('authoritative site and bounded provider horizon required')
    if not isinstance(required_variables,(set,frozenset)) or not required_variables or not required_variables<=REQUIRED:
        raise ValueError('explicit supported required variables required')
    body=_body(decision,required_horizon,site,required_variables)
    end=decision+required_horizon
    last=end.replace(minute=0,second=0,microsecond=0)
    if last<end:last+=timedelta(hours=1)
    try:
        snapshot=archive.eligible_snapshot(decision,last,required_variables=required_variables)
        if snapshot is None:return _freeze(body)
        if snapshot['site']!=dict(latitude=site.latitude,longitude=site.longitude,timezone=site.timezone):raise ValueError('authoritative site differs')
        # Reuse the complete original-capsule/unit rederivation. This checks all
        # normalized variables, even when only temperature is requested.
        temperature_targets(snapshot,issued_at=decision)
        means=[row for row in snapshot['points'] if row['statistic']=='mean']
        points=[row for row in means if decision<instant(row['valid_at'])<=last]
        values={}
        for row in points:values.setdefault(instant(row['valid_at']),{})[row['variable']]=row['value']
        hours=[]
        def convert(value,factor=1,offset=0):return None if value is None else value*factor+offset
        for at,rows in sorted(values.items()):
            hours.append(dict(at=at.isoformat(),temp_f=convert(rows.get(TEMPERATURE),9/5,32),
                radiation_wm2=rows.get(GHI),direct_radiation_wm2=rows.get(DIRECT),
                precip_in=convert(rows.get(RAIN),1/25.4),wind_mph=convert(rows.get(WIND),3600/1609.344),
                cloud_pct=rows.get(CLOUD)))
        zone=ZoneInfo(site.timezone);days=sorted({instant(row['at']).astimezone(zone).date().isoformat() for row in hours})
        source=dict(snapshot_sha256=snapshot['snapshot_sha256'],run_id=snapshot['run_id'],initialized_at=snapshot['initialized_at'],
            first_seen_at=snapshot['first_seen_at'],ingestion_completed_at=snapshot['ingestion_completed_at'])
        if astro_source is not None:
            try:
                body['solar_context']=_solar_schedule(astro_source,decision=decision,site=site)
                body['solar_context_reason']=None
            except (ValueError,KeyError,TypeError,OverflowError):
                body['solar_context_reason']='UNAVAILABLE_OR_INCOMPATIBLE'
        body.update(status='AVAILABLE',reason=None,source=source,
            issue_sha256=identity(dict(snapshot_sha256=source['snapshot_sha256'],issued_at=decision.isoformat())),
            hours=hours,days=_daily(means,days,zone))
        return _freeze(body)
    except (ValueError,KeyError,TypeError,OverflowError):
        body=_body(decision,required_horizon,site,required_variables);body['reason']='INVALID_SOURCE'
        return _freeze(body)
    except (OSError,sqlite3.Error):
        body=_body(decision,required_horizon,site,required_variables);body['reason']='ARCHIVE_UNAVAILABLE'
        return _freeze(body)


def forecast_payloads(provider,*,now):
    """Map raw Google values into existing nullable UI contracts, without seeds.

    Version 1 declares no temperature correction. Fitted Google/local candidates
    require their own validated integration; no incumbent adjustment is accepted.
    Unavailable source produces empty arrays and an explicit unavailable detail,
    so the future publisher can withdraw old values instead of retaining them.
    """
    if not isinstance(provider,ProviderSnapshot):raise ValueError('original prepared provider required')
    value=provider.to_dict();now=utc(now)
    if now!=instant(value['decision_at']):raise ValueError('provider at its exact original decision required')
    zone=ZoneInfo(value['timezone']);today=now.astimezone(zone).date();grouped={row['date']:[] for row in value['days'][:10]}
    solar=value['solar_context'];solar_days={} if solar is None else {row['day']:row for row in solar['days']}
    def is_day(at):
        row=solar_days.get(at.astimezone(zone).date().isoformat())
        return None if row is None else instant(row['daylightStartAt'])<=at<instant(row['sunsetAt'])

    for row in value['hours']:
        at=instant(row['at']);key=at.astimezone(zone).date().isoformat()
        if key in grouped:grouped[key].append(dict(at=at.astimezone(zone).isoformat(),isDay=is_day(at),tempF=row['temp_f'],
            precipPct=None,precipIn=row['precip_in'],cloudPct=row['cloud_pct'],radiationWm2=row['radiation_wm2'],windMph=row['wind_mph'],weatherCode=None))
    days=[]
    for row in value['days'][:10]:
        day=date.fromisoformat(row['date']);label='Today' if day==today else day.strftime('%a')
        days.append(dict(date=row['date'],label=label,summary=dict(highF=row['high_f'],lowF=row['low_f'],precipPct=None,
            precipSumIn=row['precip_sum_in'],weatherCode=None,pvKwh=None,
            cloudPct=(sum(h['cloudPct'] for h in grouped[row['date']])/len(grouped[row['date']])
                if grouped[row['date']] and all(h['cloudPct'] is not None for h in grouped[row['date']]) else None),
            daylightSeconds=None if row['date'] not in solar_days else solar_days[row['date']]['daylightSeconds']),hours=grouped[row['date']]))
    detail=dict(version=1,generatedAt=now.astimezone(zone).isoformat(),timezone=zone.key,provider='weathernext3',
        providerSnapshotSha256=value['provider_snapshot_sha256'],providerStatus=value['status'],providerReason=value['reason'],
        source=value['source'],issueSha256=value['issue_sha256'],
        solarSource=dict(status='UNAVAILABLE' if solar is None else 'AVAILABLE',reason=value['solar_context_reason'],
            sourceSha256=None if solar is None else solar['sourceSha256'],recordedAt=None if solar is None else solar['recordedAt'],
            availableAt=None if solar is None else solar['availableAt']),
        learningNamespace=value['learning_namespace'],model=value['model'],releaseAuthorized=False,days=days)
    def rounded(number):return None if number is None else round(number)
    hourly=[dict(at=row['at'],isDay=is_day(instant(row['at'])),h=instant(row['at']).astimezone(zone).strftime('%-I%p').lower(),t=rounded(row['temp_f']),
        p=None,a=row['precip_in'],r=rounded(row['radiation_wm2']),w=None,c=row['cloud_pct']) for row in value['hours'][:14]]
    daily=[dict(d=row['label'],hi=rounded(row['summary']['highF']),lo=rounded(row['summary']['lowF']),p=None,
        a=row['summary']['precipSumIn'],w=None,pv=None) for row in days[:7]]
    return hourly,daily,detail


def publication_states(provider,*,now):
    """Preflight all three existing Item states, including explicit withdrawal.

    This prepares bytes only. Production authorization, scheduling and state
    writes belong to the attended cutover, not this inactive provider adapter.
    """
    payloads=forecast_payloads(provider,now=now)
    result={item:canonical(payload).decode() for item,payload in zip(
        ('Forecast_Hourly_JSON','Forecast_Daily_JSON','Forecast_10Day_JSON'),payloads)}
    if any(len(raw.encode())>=65536 for raw in result.values()):raise ValueError('forecast Item byte limit exceeded')
    return result
