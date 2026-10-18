"""WeatherNext-only features and qualified local outcomes, with original clocks.

No incumbent module/state is imported. Point labels are adapted from the existing
native outdoor reader, whose source/epoch/lifetime policy remains authoritative.
"""
from dataclasses import asdict,dataclass
from datetime import datetime,timedelta
import math
from zoneinfo import ZoneInfo

from .config import COLLECTIONS,Site
from .contracts import canonical,digest,finite,identity,instant,validate_snapshot
from .evidence import utc

FEATURE_NAMES=('temperature_c','spread_c','lead_days','hour_sin','hour_cos','season_sin','season_cos')


@dataclass(frozen=True)
class TemperatureTarget:
    snapshot_digest:str
    issue_digest:str
    initialized_at:datetime
    issued_at:datetime
    target_at:datetime
    mean_c:float
    spread_c:float|None
    site_timezone:str
    grid_digest:str
    provider:str='weathernext3'


@dataclass(frozen=True)
class TemperatureOutcome:
    target_at:datetime
    value_c:float
    available_at:datetime
    assessed_at:datetime
    sensor_epoch:str
    receipt_digest:str


@dataclass(frozen=True)
class TrainingPair:
    forecast:TemperatureTarget
    outcome:TemperatureOutcome

    @property
    def cohort(self):return self.forecast.grid_digest,self.outcome.sensor_epoch

    @property
    def pair_digest(self):
        value=_jsonable(asdict(self))
        # A later read of the same original receipt is the same scientific pair.
        value['outcome'].pop('assessed_at')
        return identity(value)


def _jsonable(value):
    if isinstance(value,datetime):return utc(value).isoformat()
    if isinstance(value,dict):return {key:_jsonable(item) for key,item in value.items()}
    return value


def validate_target(target):
    if not isinstance(target,TemperatureTarget) or target.provider!='weathernext3':
        raise ValueError('WeatherNext-only temperature target required')
    for name in ('snapshot_digest','issue_digest','grid_digest'):digest(getattr(target,name))
    initialized,issued,at=map(utc,(target.initialized_at,target.issued_at,target.target_at))
    if not initialized<=issued<at<=initialized+timedelta(hours=360) or issued-initialized>timedelta(hours=24):
        raise ValueError('eligible original issue/target clocks required')
    if not finite(target.mean_c) or (target.spread_c is not None and (not finite(target.spread_c) or target.spread_c<0)):
        raise ValueError('finite WeatherNext estimate/spread required')
    ZoneInfo(target.site_timezone)
    return target


def temperature_targets(snapshot,*,issued_at):
    """Build all future hourly targets once per original issue, rechecking originals.

    `issued_at` is the retained household decision, not the provider init time.
    Historical/backfilled snapshots are never promoted to prospective features.
    """
    from .weathernext_ee import parse_collection_response
    issued_at=utc(issued_at)
    if not isinstance(snapshot,dict):raise ValueError('original snapshot required')
    body={key:value for key,value in snapshot.items() if key!='snapshot_sha256'}
    validate_snapshot(body)
    snapshot_digest=identity(body)
    if 'snapshot_sha256' in snapshot and snapshot['snapshot_sha256']!=snapshot_digest:
        raise ValueError('original snapshot digest differs')
    initialized=instant(body['initialized_at'])
    if body['historical'] or instant(body['ingestion_completed_at'])>issued_at or not initialized<=issued_at<=initialized+timedelta(hours=24):
        raise ValueError('prospectively available WeatherNext issue required')
    site=Site(**body['site'])
    rebuilt=[]
    for original in body['source_originals']:
        payload=original['payload']
        if not isinstance(payload.get('region'),list) or not payload['region']:
            raise ValueError('retained native source rows required')
        _,points=parse_collection_response(payload,collection=original['collection'],bands=payload['region'][0][4:],site=site,
            initialized_at=initialized,horizon=len(payload.get('metadata',[])))
        rebuilt.extend(points)
    order=lambda row:(row['variable'],row['statistic'],instant(row['valid_at']))
    if canonical(sorted(rebuilt,key=order))!=canonical(sorted(body['points'],key=order)):
        raise ValueError('normalized points differ from retained original rows')
    rows={}
    for point in rebuilt:
        if point['variable']=='station_head_temperature_2m' and instant(point['valid_at'])>issued_at:
            rows.setdefault(instant(point['valid_at']),{})[point['statistic']]=point
    issue_digest=identity({'snapshot_sha256':snapshot_digest,'issued_at':issued_at.isoformat()})
    result=[]
    for at,statistics in sorted(rows.items()):
        center=statistics.get('mean')
        if center is None or center['value'] is None:continue
        low,high=(statistics.get(name,{}).get('value') for name in ('p10','p90'))
        spread=None if low is None or high is None else high-low
        grid=identity({'site':body['site'],'collection':COLLECTIONS['station'],'variable':center['variable'],
                       'latitude':center['latitude'],'longitude':center['longitude']})
        result.append(validate_target(TemperatureTarget(snapshot_digest,issue_digest,initialized,issued_at,at,
            center['value'],spread,site.timezone,grid)))
    return tuple(result)


def local_temperature_outcome(metadata,*,target_at,assessed_at,sensor_epoch):
    from daily_temperature_runtime import SOURCE_POLICY
    from weather_temperature_evidence import TemperaturePolicy,sensor_epoch_id
    from weather_temperature_reader import validate_temperature_metadata_v2
    target_at,assessed_at=map(utc,(target_at,assessed_at))
    if target_at>assessed_at:raise ValueError('completed local target required')
    validate_temperature_metadata_v2(metadata,target_at,policy=TemperaturePolicy(**SOURCE_POLICY),sensor_epoch=sensor_epoch)
    # The original receipt was persisted by target_at. A later query does not
    # move its availability clock, nor make the future target known earlier.
    return TemperatureOutcome(target_at,(metadata['temperatureF']-32)*5/9,target_at,assessed_at,
        sensor_epoch_id(sensor_epoch),metadata['snapshotSha256'])


def training_pair(forecast,outcome):
    from weather_temperature_evidence import sensor_epoch_id
    validate_target(forecast)
    if not isinstance(outcome,TemperatureOutcome) or outcome.target_at!=forecast.target_at:
        raise ValueError('matching qualified local temperature outcome required')
    if not finite(outcome.value_c) or not utc(outcome.target_at)<=utc(outcome.available_at)<=utc(outcome.assessed_at):
        raise ValueError('finite completed local outcome required')
    digest(outcome.receipt_digest);sensor_epoch_id(outcome.sensor_epoch)
    return TrainingPair(forecast,outcome)


def feature_vector(target):
    validate_target(target)
    if target.spread_c is None:raise ValueError('residual model requires native quantile spread')
    local=target.target_at.astimezone(ZoneInfo(target.site_timezone))
    hour=2*math.pi*(local.hour+local.minute/60)/24
    season=2*math.pi*(local.timetuple().tm_yday-1)/366
    return (target.mean_c,target.spread_c,(target.target_at-target.initialized_at).total_seconds()/86400,
        math.sin(hour),math.cos(hour),math.sin(season),math.cos(season))


def recent_innovation(pairs,*,issued_at,cohort,hours=72):
    """Prior Google errors only; one latest issue per independently observed target."""
    issued_at=utc(issued_at)
    if not isinstance(pairs,(list,tuple)) or len(pairs)>20000 or type(hours) is not int or not 1<=hours<=168:
        raise ValueError('bounded prior innovations required')
    selected={}
    for pair in pairs:
        pair=training_pair(pair.forecast,pair.outcome)
        at=pair.outcome.target_at
        if pair.cohort!=cohort or not issued_at-timedelta(hours=hours)<=at<issued_at or pair.outcome.available_at>issued_at:continue
        previous=selected.get(at)
        if previous is None or pair.forecast.issued_at>previous.forecast.issued_at:selected[at]=pair
    if not selected:return None
    return sum(pair.outcome.value_c-pair.forecast.mean_c for pair in selected.values())/len(selected)
