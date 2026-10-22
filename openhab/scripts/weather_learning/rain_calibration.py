"""Source-bound rain intervals and gauge-aware events; no selection or controls."""
from dataclasses import dataclass,asdict
from datetime import datetime,time,timedelta,timezone
from math import fsum
from zoneinfo import ZoneInfo
import json
from .contracts import canonical,identity,instant,finite
from .native_forecast import _snapshot,_encode,_decode
from .capabilities import validate_quantiles

POLICY_SHA256='e064f05044d5cf6f518578a673c66726289df58290100045ff4ca53e0db52d7c'
PRODUCTS=('total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr')
SCHEMA='earthship-original-rain-interval-forecast/v1'
REQUEST={'start','end','issued_at','completed_at','interval_kind','availability_basis'}
FIELDS={'schema','request','source_original','snapshot_sha256','initialized_at','actual_source_available_at','grid_sha256','site','start','end','issued_at','completed_at','interval_kind','availability_basis','hours','products_mm','hourly_statistics','common_complete_targets','as_issued_score','automatic_actuation','forecast_sha256'}
MAX_BYTES=16*1024**2


def _policy(policy):
    if not isinstance(policy,dict) or policy.get('policy_sha256')!=POLICY_SHA256 or identity({k:v for k,v in policy.items() if k!='policy_sha256'})!=POLICY_SHA256:raise ValueError('frozen original rain protocol required')
    return policy


def _ceil_hour(at):
    floor=at.replace(minute=0,second=0,microsecond=0)
    return floor+timedelta(hours=1)


def _interval(request,zone):
    if not isinstance(request,dict) or set(request)!=REQUEST:raise ValueError('closed original rain interval request required')
    start,end,issued,completed=map(instant,(request['start'],request['end'],request['issued_at'],request['completed_at']));hours=(end-start).total_seconds()/3600
    if (not issued<=completed<start<end or not 1<=hours<=25 or hours!=int(hours) or any(t.minute or t.second or t.microsecond for t in (start,end))):raise ValueError('complete future native rain hours required')
    local=start.astimezone(zone);midnight=datetime.combine(local.date(),time.min,zone).astimezone(timezone.utc);tomorrow=datetime.combine(local.date()+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
    kind=request['interval_kind']
    if kind=='local_calendar_day':
        if start!=midnight or end!=tomorrow:raise ValueError('exact original local-calendar day required')
    elif kind=='rolling_24_hours':
        if hours!=24:raise ValueError('24 elapsed native hours required')
    elif kind=='remaining_day':
        if end!=tomorrow or start!=_ceil_hour(completed):raise ValueError('remaining complete native hours must start after original completion')
    else:raise ValueError('declared rain interval kind required')
    return start,end,issued,completed,int(hours)


def _forecast(request,capsule):
    source=_snapshot(_decode(capsule));zone=ZoneInfo(source['site']['timezone']);start,end,issued,completed,hours=_interval(request,zone);initialized=instant(source['initialized_at']);acquired=instant(source['ingestion_completed_at']);basis=request['availability_basis']
    if not initialized<=issued<=initialized+timedelta(hours=24) or end>initialized+timedelta(hours=360):raise ValueError('rain interval outside original run horizon')
    if basis=='recorded_ingestion_availability':
        if acquired>issued:raise ValueError('actual rain forecast acquisition follows decision')
    elif basis=='historical_assumed_full_cycle_9h':
        if source['historical'] is not True or issued<initialized+timedelta(hours=9):raise ValueError('explicit historical full-cycle assumption required')
    else:raise ValueError('declared rain source availability basis required')
    points=[p for p in source['points'] if p['variable'] in PRODUCTS];cells={(p['source_ref'].rsplit('/',1)[0],p['latitude'],p['longitude']) for p in points}
    if len(cells)!=1:raise ValueError('one original native rain grid required')
    index={};products={};hourly={}
    for point in points:index.setdefault((point['variable'],instant(point['valid_at'])),[]).append(point)
    for product in PRODUCTS:
        selected=[];means=[]
        for i in range(1,hours+1):
            at=start+timedelta(hours=i);rows=index.get((product,at),[])
            if any(p['period_seconds']!=3600 or p['raw_unit']!='m' or p['unit']!='mm' for p in rows):raise ValueError('native one-hour rain-depth units required')
            statistics={p['statistic']:p['value'] for p in rows};mean=statistics.get('mean');means.append(mean)
            try:validate_quantiles(statistics or {'mean':None});status='available' if any(v is not None for k,v in statistics.items() if k!='mean') else 'unavailable'
            except ValueError:status='crossing_quantiles_refused'
            selected.append(dict(start=(at-timedelta(hours=1)).isoformat(),end=at.isoformat(),statistics=statistics,quantile_status=status))
        products[product]=None if any(v is None for v in means) else fsum(means);hourly[product]=selected
    value=dict(schema=SCHEMA,request=request,source_original=capsule,snapshot_sha256=identity(source),initialized_at=source['initialized_at'],actual_source_available_at=source['ingestion_completed_at'],grid_sha256=identity(dict(site=source['site'],cells=sorted(cells),products=PRODUCTS)),site=source['site'],start=start.isoformat(),end=end.isoformat(),issued_at=issued.isoformat(),completed_at=completed.isoformat(),interval_kind=request['interval_kind'],availability_basis=basis,hours=hours,products_mm=products,hourly_statistics=hourly,common_complete_targets=all(v is not None for v in products.values()),as_issued_score=False,automatic_actuation=False)
    value['forecast_sha256']=identity(value);return value


@dataclass(frozen=True)
class RainForecast:
    content:bytes
    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ValueError('bounded original rain forecast required')
        value=json.loads(self.content)
        if not isinstance(value,dict) or set(value)!=FIELDS or canonical(_forecast(value['request'],value['source_original']))!=canonical(value):raise ValueError('rain forecast differs from original native source/interval')
    def to_dict(self):return json.loads(self.content)


def make_forecast(*,snapshot,start,end,issued_at,completed_at,interval_kind,availability_basis):
    if not isinstance(snapshot,dict):raise ValueError('original native rain source required')
    header={k:v for k,v in snapshot.items() if k not in ('points','snapshot_sha256')};source=_snapshot(header)
    if canonical(source)!=canonical({k:v for k,v in snapshot.items() if k!='snapshot_sha256'}) or 'snapshot_sha256' in snapshot and snapshot['snapshot_sha256']!=identity(source):raise ValueError('rain source normalized rows or identity changed')
    request=dict(start=start.isoformat(),end=end.isoformat(),issued_at=issued_at.isoformat(),completed_at=completed_at.isoformat(),interval_kind=interval_kind,availability_basis=availability_basis)
    return RainForecast(canonical(_forecast(request,_encode(header))))


def total_depth(forecast,*,statistic='mean'):
    if statistic!='mean':raise ValueError('marginal rain quantiles cannot be added into an interval quantile')
    if type(forecast) is not RainForecast:raise ValueError('typed original rain interval forecast required')
    return RainForecast(forecast.content).to_dict()['products_mm']


def classify_event(*,observed_mm,uncertainty_mm,measured_resolution_mm,policy):
    rule=_policy(policy)['wet_threshold_rule']
    if not finite(observed_mm) or observed_mm<0 or not finite(uncertainty_mm) or uncertainty_mm<0:raise ValueError('finite nonnegative observed rain and boundary width required')
    result=dict(observed_mm=observed_mm,boundary_uncertainty_mm=uncertainty_mm,measured_resolution_mm=measured_resolution_mm,threshold_mm=None,lower_mm=None,upper_mm=None,classification='insufficient_evidence',event_label=None,reason='measured_resolution_required',target='named_interval_meets_gauge_based_wet_event_threshold; below_threshold_is_not_asserted_physically_dry',physical_calibration_qualified=False,automatic_actuation=False)
    if measured_resolution_mm is None:return result
    if not finite(measured_resolution_mm) or not 0<measured_resolution_mm<=100:raise ValueError('finite positive independently evidenced measurement resolution required')
    threshold=max(rule['minimum_threshold_mm'],rule['gauge_resolution_multiplier']*measured_resolution_mm);margin=rule['boundary_ambiguity_resolution_multiples']*measured_resolution_mm;lower=max(0.,observed_mm-uncertainty_mm/2-margin);upper=observed_mm+uncertainty_mm/2+margin
    label='wet' if lower>=threshold else 'below_threshold' if upper<threshold else 'ambiguous'
    result.update(threshold_mm=threshold,lower_mm=lower,upper_mm=upper,classification=label,event_label=1 if label=='wet' else 0 if label=='below_threshold' else None,reason=None if label!='ambiguous' else 'boundary_resolution_band_crosses_event_threshold');return result


OBSERVATION_FIELDS={'schema','request','sources','source_item','native_summary','observed_mm','boundary_uncertainty_mm','available_at','observation_policy_sha256','cohort_sha256','resolution_status','resolution_reason','resolution_source_sha256','event','physical_calibration_qualified','automatic_actuation','observation_sha256'}
OBSERVATION_REQUEST={'start','end','requested_at','received_at','cutover','policy'}
RESOLUTION_FIELDS={'schema','source_item','sensor_id','observation_policy_sha256','basis','measured_at','available_at','resolution_mm','trials'}


def _resolution(document,*,policy,received):
    if (not isinstance(document,dict) or set(document)!=RESOLUTION_FIELDS or
            document['schema']!='earthship-independent-rain-counter-resolution/v1' or document['source_item']!='Weather_Rain_Evidence_JSON' or
            document['sensor_id']!=policy.sensor_id or type(document['sensor_id']) is not int or document['observation_policy_sha256']!=identity(asdict(policy)) or
            document['basis']!='independently_counted_local_gauge_tips' or len(canonical(document))>65536):raise ValueError('independent local resolution source/policy required')
    if not instant(document['measured_at'])<=instant(document['available_at'])<=received:raise ValueError('resolution measurement not actually available by acquisition')
    resolution=document['resolution_mm'];trials=document['trials']
    if (not finite(resolution) or not 0<resolution<=100 or not isinstance(trials,list) or not 3<=len(trials)<=100):raise ValueError('bounded independent resolution trials required')
    for trial in trials:
        if not isinstance(trial,dict) or set(trial)!={'counter_before_in','counter_after_in','independent_tip_count'}:raise ValueError('literal independent counter/tip trial required')
        before,after,tips=trial['counter_before_in'],trial['counter_after_in'],trial['independent_tip_count']
        if (not finite(before) or not finite(after) or not 0<=before<after<=policy.maximum_counter_in or type(tips) is not int or not 1<=tips<=10000 or
                abs((after-before)*25.4/tips-resolution)>max(1e-8,resolution*1e-6)):raise ValueError('independent resolution trials differ from declared resolution')
    return resolution


def _observation(request,sources):
    from weather_rain_evidence import RainPolicy
    from weather_rain_day import qualify_rain_interval,MAX_ROWS
    if (not isinstance(request,dict) or set(request)!=OBSERVATION_REQUEST or not isinstance(sources,dict) or set(sources)!={'observations','resolution_source','experiment_policy'}):raise ValueError('closed original rain observation required')
    experiment=_policy(sources['experiment_policy']);native=RainPolicy(**request['policy']);start,end,requested,received,cutover=map(instant,(request['start'],request['end'],request['requested_at'],request['received_at'],request['cutover']))
    if (not cutover<=start<end or not end+timedelta(seconds=native.validity_seconds)<=requested<=received or received-requested>timedelta(seconds=15) or
            not isinstance(sources['observations'],list) or len(sources['observations'])>MAX_ROWS):raise ValueError('mature bounded actual rain acquisition required')
    rows=[(instant(at),raw) for at,raw in sources['observations']];summary=qualify_rain_interval(start=start,end=end,as_of=requested,observations=rows,policy=native);observed=summary['rain_in']*25.4;uncertainty=summary['uncertainty_in']*25.4
    resolution=None;status='not_supplied';reason='measured_resolution_required';pin=None
    if sources['resolution_source'] is not None:
        try:resolution=_resolution(sources['resolution_source'],policy=native,received=received);status='source_bound_independent_measurement';reason=None;pin=identity(sources['resolution_source'])
        except ValueError as error:status='source_unavailable';reason=str(error)
    event=classify_event(observed_mm=observed,uncertainty_mm=uncertainty,measured_resolution_mm=resolution,policy=experiment);policy_pin=identity(request['policy']);cohort=identity(dict(source_item='Weather_Rain_Evidence_JSON',policy_sha256=policy_pin,cutover=request['cutover'],stream_epoch=summary['stream_epoch'],resolution_source_sha256=pin,experiment_policy_sha256=experiment['policy_sha256']))
    value=dict(schema='earthship-original-rain-interval-observation/v1',request=request,sources=sources,source_item='Weather_Rain_Evidence_JSON',native_summary=summary,observed_mm=observed,boundary_uncertainty_mm=uncertainty,available_at=received.isoformat(),observation_policy_sha256=policy_pin,cohort_sha256=cohort,resolution_status=status,resolution_reason=reason,resolution_source_sha256=pin,event=event,physical_calibration_qualified=False,automatic_actuation=False);value['observation_sha256']=identity(value);return value


@dataclass(frozen=True)
class RainObservation:
    content:bytes
    def __post_init__(self):
        if not isinstance(self.content,bytes) or len(self.content)>MAX_BYTES:raise ValueError('bounded original rain observation required')
        value=json.loads(self.content)
        if not isinstance(value,dict) or set(value)!=OBSERVATION_FIELDS or canonical(_observation(value['request'],value['sources']))!=canonical(value):raise ValueError('rain observation differs from original counter/acquisition sources')
    def to_dict(self):return json.loads(self.content)


def make_observation(*,start,end,requested_at,received_at,cutover,observations,policy,resolution_source,experiment_policy):
    from weather_rain_day import MAX_ROWS
    from itertools import islice
    request=dict(start=start.isoformat(),end=end.isoformat(),requested_at=requested_at.isoformat(),received_at=received_at.isoformat(),cutover=cutover.isoformat(),policy=asdict(policy));sources=dict(observations=[(at.isoformat(),raw) for at,raw in islice(observations,MAX_ROWS+1)],resolution_source=resolution_source,experiment_policy=experiment_policy)
    return RainObservation(canonical(_observation(request,sources)))
