"""Versioned statistics-only contracts. Pure: no cloud, fitting or publication.

Profiles describe requested coverage from initialization. They never extend
remaining coverage from a later decision or make optional fields core inputs.
"""
from dataclasses import asdict,dataclass
from datetime import datetime,timedelta,timezone
from types import MappingProxyType
import math,re
from .config import Site
from .contracts import canonical,digest,finite,identity,instant
from .normalize import VARIABLES

STATISTICS=('mean','p10','p25','p50','p75','p90')
QUANTILES=('p10','p25','p50','p75','p90')
QUANTILE_TOLERANCE=1e-9
SCHEMA='earthship-weathernext-capabilities/v1'

def _label(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9_:/.-]{1,128}',value):
        raise ValueError('bounded declared identity required')
    return value

def _band(grid,band):
    if grid not in ('station','gridded') or not isinstance(band,str) or '_' not in band:
        raise ValueError('explicit native grid and band required')
    variable,statistic=band.rsplit('_',1)
    if (variable not in VARIABLES or statistic not in STATISTICS or
            variable.startswith('station_head_')!=(grid=='station')):
        raise ValueError('mapped statistic on its native grid required')
    return variable,statistic

@dataclass(frozen=True)
class CapabilityProfile:
    name:str
    bands:tuple[tuple[str,str],...]
    consumer:str
    optional:bool=True
    priority:int=1
    horizons:tuple[int,...]=(48,360)
    frequency:str='existing_collection_cycle'
    remote_allowed:bool=True
    max_bytes:int=8*1024**2
    max_seconds:int=75
    max_requests:int=32
    max_pixels:int=16
    attempts:int=2
    version:int=1

    def __post_init__(self):
        _label(self.name);_label(self.consumer)
        if (type(self.version) is not int or self.version!=1 or
                type(self.optional) is not bool or type(self.remote_allowed) is not bool or
                type(self.priority) is not int or not 0<=self.priority<=3 or
                not isinstance(self.bands,tuple) or not 1<=len(self.bands)<=48 or
                len(set(self.bands))!=len(self.bands)):
            raise ValueError('immutable bounded capability profile required')
        for entry in self.bands:
            if not isinstance(entry,tuple) or len(entry)!=2:raise ValueError('immutable native band required')
            _band(*entry)
        if (not isinstance(self.horizons,tuple) or not self.horizons or
                len(set(self.horizons))!=len(self.horizons) or
                any(type(h) is not int or h not in (48,360) for h in self.horizons) or
                self.frequency not in ('existing_collection_cycle','full_runs_only','retained_sources_only')):
            raise ValueError('declared existing run coverage and frequency required')
        for name,low,high in [('max_bytes',1024,8*1024**2),('max_seconds',1,75),
                ('max_requests',1,32),('max_pixels',1,16),('attempts',1,2)]:
            value=getattr(self,name)
            if type(value) is not int or not low<=value<=high:raise ValueError('existing '+name+' bound required')

    @property
    def bands_by_grid(self):
        result={}
        for grid,band in self.bands:result.setdefault(grid,[]).append(band)
        return {k:tuple(v) for k,v in result.items()}

    def to_dict(self):
        return asdict(self)|dict(grid_policy='one_existing_native_cell_per_collection_no_percentile_interpolation',
            units=[dict(grid=g,band=b,native=VARIABLES[_band(g,b)[0]][0],unit=VARIABLES[_band(g,b)[0]][1],
                period_seconds=VARIABLES[_band(g,b)[0]][4]) for g,b in self.bands],
            coverage='complete_requested_targets_from_initialization_not_from_arrival',
            max_rows_per_grid=max(self.horizons),max_normalized_points=len(self.bands)*max(self.horizons),
            archive_growth_upper_bytes_per_original=self.max_bytes,
            eecu_cost=None,cost_basis='request_transfer_and_wall_time_bounds_not_eecu')

    @property
    def signature(self):return identity(self.to_dict())

_CORE=(('station','station_head_temperature_2m_mean'),('station','station_head_temperature_2m_p10'),
    ('station','station_head_temperature_2m_p90'),('station','station_head_dewpoint_temperature_2m_mean'),
    *(('gridded',v+'_mean') for v in ('surface_solar_radiation_downwards_1hr',
        'total_sky_direct_solar_radiation_at_surface_1hr','total_precipitation_1hr','imerg_tp_1hr',
        'experimental_tp_1hr','wind_speed_10m','total_cloud_cover','mean_sea_level_pressure')))
_PROFILES=(
    CapabilityProfile('core-v1',_CORE,'legacy_core',optional=False,priority=0),
    CapabilityProfile('temperature-display-v1',_CORE[:3],'hourly_uncertainty_detail',priority=0,
        frequency='retained_sources_only',remote_allowed=False),
    CapabilityProfile('uncertainty-v1',tuple(('station','station_head_temperature_2m_'+s) for s in ('p25','p50','p75'))+
        tuple(('gridded',v+'_'+s) for v in ('surface_solar_radiation_downwards_1hr','wind_speed_10m') for s in ('p10','p50','p90')),'marginal_diagnostics',priority=1),
    # Companion means stay in this new original; legacy quantile-only identities remain frozen.
    CapabilityProfile('uncertainty-complete-v1',tuple(('station','station_head_temperature_2m_'+s) for s in STATISTICS)+
        tuple(('gridded',v+'_'+s) for v in ('surface_solar_radiation_downwards_1hr','wind_speed_10m') for s in ('mean','p10','p50','p90')),
        'marginal_and_temperature_detail',priority=1),
    CapabilityProfile('atmosphere-v1',tuple(('gridded',v+'_mean') for v in ('u_component_of_wind_10m','v_component_of_wind_10m',
        'high_cloud_cover','medium_cloud_cover','low_cloud_cover')),'atmospheric_context',priority=2),
    CapabilityProfile('rain-uncertainty-v1',tuple(('gridded',v+'_'+s) for v in ('total_precipitation_1hr','imerg_tp_1hr','experimental_tp_1hr')
        for s in QUANTILES),'rain_diagnostics',priority=3,horizons=(360,),frequency='full_runs_only'),
)
PROFILES=MappingProxyType({p.name:p for p in _PROFILES})
def profile(name):
    try:return PROFILES[name]
    except (KeyError,TypeError):raise ValueError('reviewed named capability profile required') from None

def enabled_profiles(optional=()):
    if not isinstance(optional,tuple) or len(set(optional))!=len(optional):raise ValueError('explicit unique optional profile names required')
    values=[profile(name) for name in optional]
    if {'uncertainty-v1','uncertainty-complete-v1'}<=set(optional):raise ValueError('one uncertainty acquisition profile per cycle required')
    if any(not p.optional or not p.remote_allowed for p in values):raise ValueError('only explicit acquisition groups can be enabled')
    return (profile('core-v1'),*sorted(values,key=lambda p:(p.priority,p.name)))

def validate_quantiles(values):
    if not isinstance(values,dict) or not values or not set(values)<=set(STATISTICS):
        raise ValueError('named marginal statistics required')
    if any(v is not None and not finite(v) for v in values.values()):raise ValueError('finite nullable statistics required')
    previous=None
    for name in QUANTILES:
        value=values.get(name)
        if value is None:continue
        if previous is not None and value<previous-QUANTILE_TOLERANCE:raise ValueError('crossing original quantiles refused')
        previous=value
    return dict(values)

@dataclass(frozen=True)
class NativeStatisticSeries:
    snapshot_sha256:str
    run_id:str
    initialized_at:str
    first_seen_at:str
    available_at:str
    decision_at:str
    variable:str
    statistic:str
    grid:str
    cell:tuple[float,float]
    raw_unit:str
    unit:str
    period_seconds:int
    valid_at:tuple[str,...]
    interval_start:tuple[str,...]
    raw_values:tuple[float|None,...]
    values:tuple[float|None,...]
    quality_reasons:tuple[str|None,...]

    def __post_init__(self):
        digest(self.snapshot_sha256);_band(self.grid,self.variable+'_'+self.statistic)
        native,unit,factor,offset,period=VARIABLES[self.variable]
        if (self.raw_unit,self.unit,self.period_seconds)!=(native,unit,period):raise ValueError('native units and period must match variable')
        if not isinstance(self.cell,tuple) or len(self.cell)!=2:raise ValueError('one native cell required')
        Site(*self.cell,'UTC')
        init,seen,available,decision=map(instant,(self.initialized_at,self.first_seen_at,self.available_at,self.decision_at))
        if not init<=seen<=available<=decision<=init+timedelta(hours=24):raise ValueError('actual source availability at decision required')
        if self.run_id.startswith('ee:'):run_init=instant(self.run_id[3:])
        elif re.fullmatch(r'\d{8}_\d{2}hr_\d{2}_preds',self.run_id):run_init=datetime.strptime(self.run_id[:11],'%Y%m%d_%H').replace(tzinfo=timezone.utc)
        else:raise ValueError('declared source run required')
        if run_init!=init:raise ValueError('source run initialization differs')
        arrays=[self.valid_at,self.interval_start,self.raw_values,self.values,self.quality_reasons]
        if any(not isinstance(v,tuple) or len(v)!=len(self.valid_at) for v in arrays) or not 1<=len(self.valid_at)<=360:
            raise ValueError('bounded aligned immutable statistic series required')
        times=tuple(map(instant,self.valid_at))
        if times!=tuple(sorted(set(times))):raise ValueError('ordered unique valid targets required')
        for at,start,raw,value,reason in zip(times,self.interval_start,self.raw_values,self.values,self.quality_reasons):
            if not init<at<=init+timedelta(hours=360) or instant(start)!=at-timedelta(seconds=period):
                raise ValueError('exact native interval required')
            if (raw is None)!=(value is None):raise ValueError('paired native and normalized missingness required')
            if raw is None:
                if not isinstance(reason,str) or not reason:raise ValueError('missing value needs quality reason')
            elif (not finite(raw) or not finite(value) or not math.isclose(value,raw*factor+offset,rel_tol=1e-12,abs_tol=1e-9)):
                raise ValueError('normalized value must match original native value')

def native_series(snapshot,variable,statistic,*,decision):
    from .features import prospective_snapshot
    body=prospective_snapshot(snapshot,issued_at=decision)
    rows=sorted((p for p in body['points'] if p['variable']==variable and p['statistic']==statistic),key=lambda p:p['valid_at'])
    if not rows:raise ValueError('requested native statistic unavailable')
    cells={(p['latitude'],p['longitude']) for p in rows}
    if len(cells)!=1:raise ValueError('native statistic changes cell')
    first=rows[0];period=first['period_seconds']
    return NativeStatisticSeries(body['snapshot_sha256'],body['run_id'],body['initialized_at'],body['first_seen_at'],
        body['ingestion_completed_at'],decision.isoformat(),variable,statistic,
        'station' if variable.startswith('station_head_') else 'gridded',next(iter(cells)),first['raw_unit'],first['unit'],period,
        tuple(p['valid_at'] for p in rows),tuple((instant(p['valid_at'])-timedelta(seconds=period)).isoformat() for p in rows),
        tuple(p['raw_value'] for p in rows),tuple(p['value'] for p in rows),tuple('source_null' if p['value'] is None else None for p in rows))

def profile_coverage(snapshot,capability,*,decision,horizon):
    from .features import prospective_snapshot
    if not isinstance(capability,CapabilityProfile) or horizon not in capability.horizons:raise ValueError('declared profile horizon required')
    try:body=prospective_snapshot(snapshot,issued_at=decision)
    except (ValueError,TypeError,KeyError):return dict(status='unavailable_at_decision',profile_sha256=capability.signature,missing_bands=[])
    init=instant(body['initialized_at']);index={(p['variable'],p['statistic'],instant(p['valid_at'])):p['value'] for p in body['points']}
    missing=[]
    for grid,band in capability.bands:
        variable,statistic=_band(grid,band)
        if any(index.get((variable,statistic,init+timedelta(hours=h))) is None for h in range(1,horizon+1)):missing.append(band)
    return dict(status='missing_fields' if missing else 'complete',profile_sha256=capability.signature,missing_bands=missing)

@dataclass(frozen=True)
class ForecastEvidence:
    profile_sha256:str
    snapshot_sha256:str
    method:str
    target:str
    issued_at:str
    available_at:str
    issued_values_sha256:str
    model_sha256:str|None=None
    procedure_sha256:str|None=None
    sensor_epoch:str|None=None
    observation_policy_sha256:str|None=None
    source_status:str='available'
    local_skill:str='not_evaluated'
    probability_calibration:str='unqualified'
    serving_admitted:bool=False
    automatic_actuation:bool=False

    def __post_init__(self):
        for name in ('profile_sha256','snapshot_sha256','issued_values_sha256'):digest(getattr(self,name))
        for name in ('model_sha256','procedure_sha256','observation_policy_sha256'):
            if getattr(self,name) is not None:digest(getattr(self,name))
        _label(self.method);_label(self.target)
        if instant(self.available_at)>instant(self.issued_at):raise ValueError('source cannot become available after issuance')
        if (self.source_status not in ('available','unavailable','withheld') or
                self.local_skill not in ('not_evaluated','insufficient_evidence','evaluated') or
                self.probability_calibration not in ('unqualified','insufficient_evidence','qualified') or
                type(self.serving_admitted) is not bool or self.automatic_actuation is not False):
            raise ValueError('separate source/skill/probability/serving status without actuation required')

@dataclass(frozen=True)
class ScenarioSet:
    profile_sha256:str
    source_sha256:str
    method:str
    seed:int
    issued_at:str
    variables:tuple[str,...]
    interval_ends:tuple[str,...]
    trajectories:tuple[tuple[tuple[float,...],...],...]
    dependence:str
    scope:str
    probability_claim:bool=False
    probability_evidence_sha256:str|None=None

    def __post_init__(self):
        digest(self.profile_sha256);digest(self.source_sha256);_label(self.method);_label(self.dependence);_label(self.scope)
        issue=instant(self.issued_at)
        if (type(self.seed) is not int or not 0<=self.seed<2**32 or not isinstance(self.variables,tuple) or
                not 1<=len(self.variables)<=16 or len(set(self.variables))!=len(self.variables)):
            raise ValueError('bounded deterministic scenario variables/seed required')
        for name in self.variables:_label(name)
        if not isinstance(self.interval_ends,tuple) or not 1<=len(self.interval_ends)<=360:raise ValueError('bounded scenario intervals required')
        ends=tuple(map(instant,self.interval_ends))
        if ends!=tuple(sorted(set(ends))) or not issue<ends[0]<=ends[-1]<=issue+timedelta(hours=360):raise ValueError('ordered future scenario intervals required')
        if not isinstance(self.trajectories,tuple) or not 1<=len(self.trajectories)<=16:raise ValueError('bounded scenario count required')
        for trajectory in self.trajectories:
            if not isinstance(trajectory,tuple) or len(trajectory)!=len(ends):raise ValueError('aligned immutable trajectory required')
            for values in trajectory:
                if not isinstance(values,tuple) or len(values)!=len(self.variables) or any(not finite(v) for v in values):raise ValueError('finite aligned immutable trajectory values required')
        if type(self.probability_claim) is not bool or self.probability_claim and self.probability_evidence_sha256 is None:
            raise ValueError('probability claim requires separate qualified evidence')
        if self.probability_evidence_sha256 is not None:digest(self.probability_evidence_sha256)
        if len(canonical(asdict(self)))>512*1024:raise ValueError('bounded scenario report required')
