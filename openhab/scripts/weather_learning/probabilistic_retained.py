"""Immutable original-source adapter for all declared marginal lead scopes.

No observations enter forecast preprocessing. Hourly scalar wind uses native
boundary means; its hourly quantiles are unavailable even if instantaneous
quantiles exist. Solar is the original one-hour normalized energy rate.
"""
from dataclasses import dataclass
from datetime import timedelta
from .contracts import identity,instant,finite
from .evidence import utc
from .historical import verify_history
from .pv_training_sources import forecast_origin
from .config import COLLECTIONS
from .probabilistic import ForecastInput,_lead

SPECS={'temperature':('station_head_temperature_2m','station','degC',0,-100,70),
       'solar_proxy':('surface_solar_radiation_downwards_1hr','gridded','W m-2',3600,0,2500),
       'wind':('wind_speed_10m','gridded','m s-1',0,0,200)}


@dataclass(frozen=True)
class NativeValue:
    kind:str
    target:str
    statistic:str
    value:float|None
    grid_sha256:str
    asset_sha256:str


@dataclass(frozen=True)
class MarginalSource:
    snapshot_sha256:str
    initialized_at:str
    actual_available_at:str
    origin:str
    historical:bool
    timezone:str
    points:tuple

    def forecast(self,kind,*,target,quality,origin=None):
        if kind not in SPECS or not isinstance(quality,dict) or not quality:raise ValueError('declared measured-target quality and marginal kind required')
        target=utc(target);origin=instant(self.origin) if origin is None else utc(origin)
        if self.historical and origin!=instant(self.origin):raise ValueError('original historical readiness origin required')
        at=target.isoformat();index={(p.target,p.statistic):p for p in self.points if p.kind==kind};mean=index.get((at,'mean'))
        if mean is None or mean.value is None:return None
        quantiles={name:None for name in ('p10','p50','p90')};baseline=mean.value
        if kind=='wind':
            left=index.get(((target-timedelta(hours=1)).isoformat(),'mean'))
            if left is None or left.value is None or left.grid_sha256!=mean.grid_sha256:return None
            baseline=(left.value+mean.value)/2
        else:
            for name in quantiles:
                point=index.get((at,name))
                if point is not None and point.grid_sha256==mean.grid_sha256 and point.asset_sha256==mean.asset_sha256:quantiles[name]=point.value
        basis='historical_assumed_availability' if self.historical else 'recorded_ingestion_availability'
        cohort=identity(dict(kind=kind,measurement_quality=quality,grid_sha256=mean.grid_sha256,availability_basis=basis,lead_scope_hours=_lead(origin.isoformat(),at)))
        return ForecastInput(kind=kind,origin=origin.isoformat(),initialized_at=self.initialized_at,target_start=at if kind=='temperature' else (target-timedelta(hours=1)).isoformat(),
            target_end=at,baseline=baseline,incumbent=None,incumbent_sha256=None,**quantiles,
            source_ready_at=self.origin if self.historical else self.actual_available_at,actual_source_available_at=self.actual_available_at,
            availability_basis=basis,forecast_sha256=self.snapshot_sha256,grid_sha256=mean.grid_sha256,cohort_sha256=cohort,timezone=self.timezone)


def prepare_marginal_source(snapshot,*,assessed_at):
    assessed_at=utc(assessed_at);body=verify_history(snapshot);pin=identity(body)
    if snapshot.get('snapshot_sha256',pin)!=pin:raise ValueError('original native marginal identity differs')
    if instant(body['ingestion_completed_at'])>assessed_at:raise ValueError('actual source not available at assessment')
    points=[];variables={v[0]:kind for kind,v in SPECS.items()}
    for p in body['points']:
        if p['variable'] not in variables or p['statistic'] not in ('mean','p10','p50','p90'):continue
        kind=variables[p['variable']];_,grid,unit,period,lo,hi=SPECS[kind]
        if (p['unit'],p['period_seconds'])!=(unit,period) or not p['source_ref'].startswith(COLLECTIONS[grid]+'/'):raise ValueError('original marginal units/grid/period differ')
        if p['value'] is not None and not lo<=p['value']<=hi:raise ValueError('original marginal value outside declared domain')
        points.append(NativeValue(kind,p['valid_at'],p['statistic'],p['value'],identity(dict(collection=COLLECTIONS[grid],latitude=p['latitude'],longitude=p['longitude'])),identity(p['source_ref'])))
    origin=forecast_origin(body,recorded=not body['historical'])
    return MarginalSource(pin,body['initialized_at'],body['ingestion_completed_at'],origin.isoformat(),body['historical'],body['site']['timezone'],tuple(points))


def proxy_labels(originals,*,guard=lambda:None):
    from .solar_shadow import _source
    if not isinstance(originals,list) or len(originals)>10000:raise ValueError('bounded original proxy receipts required')
    chosen={}
    for original in originals:
        guard();source=_source(original)
        quality=dict(provenance='source_qualified_lux_to_solar_proxy',stream_epoch=source['stream_epoch'],policy=source['policy'],source_item=source['source_item'],physical_irradiance_calibration_qualified=False)
        for h in source['hourly']:
            end=instant(h['end']);value=h['proxy_wh_m2']
            # A complete one-hour energy divided by exactly one hour has this
            # numeric W/m2 value. Never a PV electrical output observation.
            label=dict(target_start=(end-timedelta(hours=1)).isoformat(),target_end=end.isoformat(),value=value,quality=quality,
                actual_available_at=source['assessed_at'],receipt_sha256=source['source_sha256'])
            key=(identity(quality),h['end']);old=chosen.get(key)
            if old is not None and old['value']!=value:raise ValueError('conflicting original proxy hour')
            if old is None or (instant(label['actual_available_at']),label['receipt_sha256'])<(instant(old['actual_available_at']),old['receipt_sha256']):chosen[key]=label
    return [chosen[k] for k in sorted(chosen)]


def _pair(frame,value,actual,receipt):
    from .probabilistic import CalibrationPair
    if frame is None:raise ValueError('complete original native marginal target required')
    ready=(instant(frame.target_end)+timedelta(minutes=2)).isoformat() if frame.availability_basis=='historical_assumed_availability' else actual
    return CalibrationPair(forecast=frame,value=value,outcome_ready_at=ready,actual_outcome_available_at=actual,receipt_sha256=receipt)


def temperature_pair(parent,*,snapshot,source,measurements,availability,hours=None):
    from .atmospheric_retained import verify_temperature_parent
    verify_temperature_parent(parent,snapshot,measurements,forecast_sha256=source.snapshot_sha256,hours=hours)
    label=parent['label'];quality={k:label.get(k) for k in ('provenance','measurement_health_qualified','receiptVersion','sensorEpoch','sourceModel','sourceSensorId','sourceItem','unit','unit_basis')}
    if label['receivedAt'] is not None:quality['receipt_validity_seconds']=(instant(label['validUntil'])-instant(label['receivedAt'])).total_seconds()
    frame=source.forecast('temperature',target=instant(parent['target_at']),quality=quality)
    if frame is None or parent['origin']!=frame.origin or abs(parent['baseline']-frame.baseline)>1e-9:raise ValueError('temperature original point replay differs')
    return _pair(frame,parent['outcome'],availability[(parent['target_at'],'outdoor')],identity(label))


def wind_pair(parent,*,source,label):
    from .weather_response import _pair as validate
    from .solar_experiment import BASES
    validate(parent)
    quality=dict(provenance=parent['measurement_quality'],measurement_health_qualified=False,unit='m_s',target='complete_one_hour_mean_scalar')
    frame=source.forecast('wind',target=instant(parent['target_end']),quality=quality)
    if (frame is None or frame.forecast_sha256!=parent['source_sha256'] or frame.origin!=parent['origin'] or frame.target_start!=parent['target_start'] or
            parent['availability_basis']!=BASES[source.historical] or abs(frame.baseline-parent['baseline'])>1e-9 or label is None or
            abs(parent['outcome']-label['mean_m_s'])>1e-9 or parent['measurement_sha256']!=label['source_sha256']):raise ValueError('wind original source/window/measurement replay differs')
    return _pair(frame,parent['outcome'],label['actual_available_at'],identity(label))


def partition_population(rows,*,maximum_rows=10000):
    from collections import defaultdict
    from dataclasses import replace
    from .probabilistic import _cohort,_validate
    if type(maximum_rows) is not int or not 1<=maximum_rows<=10000:raise ValueError('declared coherent population bound required')
    groups=defaultdict(list);descriptors={};output=[]
    for p in rows:groups[_cohort(p.forecast)].append(p)
    for context,values in sorted(groups.items()):
        if len(values)<=maximum_rows:output.extend(_validate(values));continue
        divided=defaultdict(list)
        for p in values:
            f=p.forecast;lead=(instant(f.target_end)-instant(f.origin)).total_seconds()/3600
            descriptor=dict(parent_cohort_sha256=f.cohort_sha256,exact_lead_hours=lead);pin=identity(descriptor);descriptors[pin]=descriptor
            divided[pin].append(replace(p,forecast=replace(f,cohort_sha256=pin)))
        if any(len(v)>maximum_rows for v in divided.values()):raise ValueError('coherent exact-lead population exceeds frozen bound; no rows truncated')
        for key,subset in sorted(divided.items()):output.extend(_validate(subset))
    return output,descriptors


def build_population(*,base,temperature_parent,wind_parent,assessed_at,read,guard,progress=lambda **kw:None):
    """Replay every declared parent row and all retained qualified proxy hours.

    Measured quality strata are explicit retrospective cohort descriptors, not
    a claim that a future sensor phase was known at an operational issue.
    """
    from pathlib import Path
    from collections import defaultdict,Counter
    from .archive import Archive
    from .atmospheric_dataset import document,read_dataset,temperature_receipts,numeric_measurements,wind_measurements
    from .config import Site
    base=Path(base);assessed_at=utc(assessed_at);excluded=[];by_source=defaultdict(lambda:defaultdict(list))
    tr=document(Path(temperature_parent)/'experiment.json','receipt_sha256',read=read)
    temp_data,temps=read_dataset(temperature_parent,tr['datasets']['outdoor_temperature_c'],read=read,guard=guard)
    wr=document(Path(wind_parent)/'experiment.json','receipt_sha256',read=read)
    wind_data,winds=read_dataset(wind_parent,wr['dataset_sha256'],read=read,guard=guard)
    wind_rows=[r for r in winds if r['kind']=='wind_m_s']
    for row in temps:by_source[row['forecast_sha256']]['temperature'].append(row)
    for row in wind_rows:by_source[row['source_sha256']]['wind'].append(row)
    archives=[Archive.open_readonly(str(base/name)) for name in ('historical-2026','archive')];references={}
    for a in archives:
        with a._connect() as db:refs=db.execute('SELECT digest FROM snapshots WHERE completed<=? ORDER BY initialized,completed,digest LIMIT 2001',(assessed_at.isoformat(),)).fetchall()
        if len(refs)>2000:raise ValueError('bounded complete marginal original census exceeded')
        for pin, in refs:references[pin]=a
    if not references or any(pin not in references for pin in by_source):raise ValueError('exact original marginal parent forecast missing')
    first=next(iter(references));initial=references[first].read(first);site=Site(**initial['site'])
    receipts,receipt_ready=temperature_receipts(base/'historical-measurements',temp_data['measurement_manifest'],read=read,guard=guard)
    numeric,numeric_ready=numeric_measurements(base/'historical-numeric',temp_data['numeric_manifest'],receipts,site=site.__dict__,read=read,guard=guard)
    measurements={**numeric,**receipts};availability={**numeric_ready,**receipt_ready}
    wind_labels=wind_measurements(base/'historical-weather-inventory',wind_data['measurement_manifest'],read=read,guard=guard)
    proxy_originals=[];paths=sorted((base/'shadow/google-local-v2/weather-outcomes').glob('*.json'))
    if len(paths)>10000:raise ValueError('bounded complete local proxy original census exceeded')
    for path in paths:
        guard();value=__import__('json').loads(read(path,16*1024**2))
        if value.get('schema')=='earthship-qualified-solar-proxy-source/v1' and instant(value['assessed_at'])<=assessed_at:proxy_originals.append(value)
    proxies=proxy_labels(proxy_originals,guard=guard);progress(phase='measurement_originals_replayed',temperature_targets=len(measurements),wind_targets=len(wind_labels),qualified_proxy_targets=len(proxies))
    pairs=[];native_stats=Counter();quality_contexts={};source_metadata=[]
    for index,(pin,archive) in enumerate(sorted(references.items())):
        guard();path=archive.objects/(pin+'.json');snapshot=__import__('json').loads(read(path,8*1024**2));source=prepare_marginal_source(snapshot,assessed_at=assessed_at)
        if pin!=source.snapshot_sha256 or snapshot['site']!=site.__dict__:raise ValueError('original marginal source/site differs from census')
        hours={}
        for p in source.points:
            if p.kind=='temperature' and p.statistic=='mean':hours.setdefault(p.target,{})['station_head_temperature_2m']=p.value
        for row in by_source[pin]['temperature']:
            guard();pair=temperature_pair(row,snapshot=snapshot,source=source,measurements=measurements,availability=availability,hours=hours);pairs.append(pair)
            quality_contexts[pair.forecast.cohort_sha256]=dict(kind='temperature',measurement_quality={k:row['label'].get(k) for k in ('provenance','measurement_health_qualified','receiptVersion','sensorEpoch','sourceModel','sourceSensorId','sourceItem','unit','unit_basis')},retrospective_cohort_only=True)
        for row in by_source[pin]['wind']:
            guard();pair=wind_pair(row,source=source,label=wind_labels.get(row['target_end']));pairs.append(pair)
            quality_contexts[pair.forecast.cohort_sha256]=dict(kind='wind',measurement_quality=row['measurement_quality'],measurement_health_qualified=False,retrospective_cohort_only=True)
        origin=instant(source.origin);init=instant(source.initialized_at)
        for label in proxies:
            end=instant(label['target_end']);start=instant(label['target_start'])
            if not origin<=start<end<=init+timedelta(hours=360) or not 0<(end-origin).total_seconds()/3600<=336 or origin-init>timedelta(hours=24):continue
            frame=source.forecast('solar_proxy',target=end,quality=label['quality'])
            if frame is None:
                excluded.append(dict(kind='solar_proxy',forecast_sha256=pin,target_end=label['target_end'],reason='native_solar_interval_missing'));continue
            pairs.append(_pair(frame,label['value'],label['actual_available_at'],label['receipt_sha256']))
            quality_contexts[frame.cohort_sha256]=dict(kind='solar_proxy',measurement_quality=label['quality'],retrospective_cohort_only=True)
        for p in source.points:
            if p.value is not None:native_stats[(p.kind,p.statistic)]+=1
        source_metadata.append(dict(snapshot_sha256=pin,initialized_at=source.initialized_at,actual_available_at=source.actual_available_at,origin=source.origin,historical=source.historical))
        if (index+1)%50==0:progress(phase='forecast_originals_replayed',sources=index+1,total=len(references),pairs=len(pairs))
    pairs,partitions=partition_population(pairs)
    counts=Counter(p.forecast.kind for p in pairs);progress(phase='population_complete',pairs=len(pairs),cohorts=len({p.forecast.cohort_sha256 for p in pairs}))
    return dict(pairs=pairs,parents=dict(temperature=temp_data['dataset_sha256'],wind=wind_data['dataset_sha256']),parent_counts=dict(temperature=len(temps),wind=len(wind_rows),qualified_proxy_hours=len(proxies),qualified_proxy_originals=len(proxy_originals)),
        counts=dict(counts),quality_contexts=quality_contexts,partitions=partitions,original_forecasts=source_metadata,native_statistics_census=[dict(kind=k[0],statistic=k[1],points=n) for k,n in sorted(native_stats.items())],excluded=excluded,
        cohort_assignment='retrospective_observed_measurement_strata; no historical as-issued or future-phase availability claim',timezone=site.timezone)


def restore_population(path,*,policy,read,guard=lambda:None):
    from pathlib import Path
    from dataclasses import asdict
    from .atmospheric_dataset import compressed_document
    from .probabilistic import CalibrationPair,_policy
    _policy(policy);path=Path(path);body,_=compressed_document(path,read=read,maximum=64*1024**2)
    if (body.get('schema')!='earthship-marginal-calibration-population/v1' or body.get('policy_sha256')!=policy['policy_sha256'] or
            body.get('population_sha256')!=identity({k:v for k,v in body.items() if k!='population_sha256'}) or
            path.name!=body['population_sha256']+'.population.json.gz' or not isinstance(body.get('rows'),list) or len(body['rows'])>100000):
        raise ValueError('unchanged original marginal population identity required')
    pairs=[]
    for row in body['rows']:
        guard();f=dict(row['forecast']);f.pop('input_sha256');p=dict(row);p.pop('pair_sha256');p['forecast']=ForecastInput(**f);pair=CalibrationPair(**p)
        if asdict(pair)!=row:raise ValueError('original marginal pair identity differs after reconstruction')
        pairs.append(pair)
    partitioned,_=partition_population(pairs)
    if pairs!=partitioned and sorted(p.pair_sha256 for p in pairs)!=sorted(p.pair_sha256 for p in partitioned):raise ValueError('original population partition differs')
    return pairs,{k:v for k,v in body.items() if k!='rows'}
