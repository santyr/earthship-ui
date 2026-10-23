"""Complete native marginal matches and bounded independent cohort artifacts.

Legacy parent examples are verified where they exist. Their sampling and
origin-bias-feature requirements do not select this population. All forecast
predictors come from one original run; measurement strata remain retrospective.
"""
from collections import Counter,defaultdict
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
import gzip,json
from .contracts import canonical,identity,instant
from .evidence import utc
from .historical_pairs import _validate_label,_c
from .probabilistic_retained import prepare_marginal_source,_pair,partition_population


def _temperature_quality(label):
    value={k:label.get(k) for k in ('provenance','measurement_health_qualified','receiptVersion','sensorEpoch','sourceModel','sourceSensorId','sourceItem','unit','unit_basis')}
    if label['receivedAt'] is not None:value['receipt_validity_seconds']=(instant(label['validUntil'])-instant(label['receivedAt'])).total_seconds()
    return value


def pair_key(pair):
    f=pair.forecast if hasattr(pair,'forecast') else None
    if f is not None:return f.forecast_sha256,f.kind,f.target_end,f.cohort_sha256
    f=pair['forecast'];return f['forecast_sha256'],f['kind'],f['target_end'],f['cohort_sha256']


def _equivalent(a,b):
    if isinstance(a,dict):return isinstance(b,dict) and set(a)==set(b) and all(_equivalent(v,b[k]) for k,v in a.items() if k!='pair_sha256')
    if type(a) in (float,int) and type(b) in (float,int):return abs(a-b)<=1e-9
    return a==b


def pairs_for_source(snapshot,*,site,assessed_at,temperatures,temperature_ready,winds,proxies,legacy,guard=lambda:None):
    source=prepare_marginal_source(snapshot,assessed_at=assessed_at)
    if snapshot['site']!=site.__dict__:raise ValueError('full native original site differs')
    origin=instant(source.origin);init=instant(source.initialized_at);pairs=[];contexts={};withheld=Counter();checked=exact=without_origin=0
    proxy_by_end=defaultdict(list)
    for label in proxies:proxy_by_end[label['target_end']].append(label)
    for point in source.points:
        guard()
        if point.statistic!='mean':continue
        at=instant(point.target);lead=(at-origin).total_seconds()/3600;kind=point.kind
        if not 0<lead<=336 or at>init+timedelta(hours=360) or origin-init>timedelta(hours=24) or kind!='temperature' and at-timedelta(hours=1)<origin:continue
        if point.value is None:withheld[kind+':native_mean_missing']+=1;continue
        if kind=='temperature':
            label=temperatures.get(point.target,{}).get('outdoor')
            if label is None:withheld[kind+':no_retained_target']+=1;continue
            _validate_label(label,at);quality=_temperature_quality(label)
            observations=[dict(value=_c(label),quality=quality,actual_available_at=temperature_ready[(point.target,'outdoor')],receipt_sha256=identity(label))]
        elif kind=='wind':
            label=winds.get(point.target)
            if label is None:withheld[kind+':no_retained_target']+=1;continue
            quality=dict(provenance='numeric_mph_without_sensor_health_receipts',measurement_health_qualified=False,unit='m_s',target='complete_one_hour_mean_scalar')
            observations=[dict(value=label['mean_m_s'],quality=quality,actual_available_at=label['actual_available_at'],receipt_sha256=identity(label))]
        else:
            observations=proxy_by_end.get(point.target,[])
            if not observations:withheld[kind+':no_retained_target']+=1;continue
        for observation in observations:
            quality=observation['quality'];frame=source.forecast(kind,target=at,quality=quality)
            if frame is None:withheld[kind+':native_window_incomplete']+=1;continue
            pair=_pair(frame,observation['value'],observation['actual_available_at'],observation['receipt_sha256']);key=pair_key(pair);original=legacy.get(key)
            if original is not None:
                if original.get('pair_sha256')!=identity({k:v for k,v in original.items() if k!='pair_sha256'}) or not _equivalent(asdict(pair),original):raise ValueError('legacy marginal pair disagrees with native/measurement original replay')
                checked+=1;exact+=asdict(pair)==original
            if kind=='temperature' and temperatures.get(source.origin,{}).get('outdoor') is None:without_origin+=1
            contexts[frame.cohort_sha256]=dict(kind=kind,measurement_quality=quality,retrospective_cohort_only=True)
            pairs.append(pair)
    return dict(pairs=pairs,quality_contexts=contexts,withheld=dict(withheld),legacy_checked=checked,legacy_exact=exact,matched_without_origin_temperature=without_origin,
        source=dict(snapshot_sha256=source.snapshot_sha256,initialized_at=source.initialized_at,actual_available_at=source.actual_available_at,origin=source.origin,historical=source.historical))



def partition_complete_population(rows,*,maximum_rows=10000):
    from dataclasses import replace
    from .probabilistic import _cohort,_validate
    if type(maximum_rows) is not int or not 1<=maximum_rows<=10000:raise ValueError('declared native cohort row bound required')
    grouped=defaultdict(list)
    for p in rows:grouped[_cohort(p.forecast)].append(p)
    output=[];descriptors={}
    for context,values in sorted(grouped.items()):
        if len(values)<=maximum_rows:output.extend(_validate(values));continue
        leads=defaultdict(list)
        for p in values:
            f=p.forecast;lead=(instant(f.target_end)-instant(f.origin)).total_seconds()/3600;leads[lead].append(p)
        if any(len(v)>maximum_rows for v in leads.values()):raise ValueError('one native lead exceeds coherent row bound; no rows truncated')
        blocks=[];current=[];last=None
        for lead,entries in sorted(leads.items()):
            if current and len(current)+len(entries)>maximum_rows:blocks.append((last,current));current=[]
            current.extend(entries);last=lead
        if current:blocks.append((context[4][1],current))
        lower=float(context[4][0])
        for upper,subset in blocks:
            descriptor=dict(method='contiguous_whole_native_leads_greedy_capacity/v1',parent_cohort_sha256=context[1],lower_exclusive_hours=lower,upper_inclusive_hours=float(upper))
            pin=identity(descriptor);descriptors[pin]=descriptor
            output.extend(_validate([replace(p,forecast=replace(p.forecast,cohort_sha256=pin)) for p in subset]));lower=float(upper)
    return output,descriptors

def retain_collection(rows,*,output,policy,metadata,maximum_rows=10000,guard=lambda:None):
    from marginal_calibration_experiment import immutable
    from .shadow import _directory
    from .probabilistic import _policy,_cohort
    _policy(policy);output=Path(output)
    if not output.is_absolute() or output.resolve()!=output or not isinstance(rows,list) or len(rows)>500000:raise ValueError('bounded complete cohort collection required')
    _directory(output);rows,partitions=partition_complete_population(rows,maximum_rows=maximum_rows);groups=defaultdict(list)
    for p in rows:groups[p.forecast.cohort_sha256].append(p)
    descriptors={};counts=Counter()
    for pin,values in sorted(groups.items()):
        guard()
        if len(values)>maximum_rows or len({_cohort(p.forecast) for p in values})!=1:raise ValueError('one coherent bounded cohort artifact required')
        values=sorted(values,key=lambda p:(p.forecast.origin,p.forecast.target_end,p.pair_sha256));f=values[0].forecast
        body=dict(schema='earthship-marginal-calibration-population/v1',policy_sha256=policy['policy_sha256'],rows=[asdict(p) for p in values],
            metadata=metadata,partitions={pin:partitions[pin]} if pin in partitions else {},source_scope='all_eligible_frozen_native_points_and_original_measured_targets')
        body['population_sha256']=identity(body);raw=canonical(body)
        if len(raw)>64*1024**2:raise ValueError('bounded individual marginal cohort object exceeded')
        name=body['population_sha256']+'.population.json.gz';immutable(output/name,gzip.compress(raw,compresslevel=3,mtime=0));guard()
        descriptors[pin]=dict(kind=f.kind,availability_basis=f.availability_basis,grid_sha256=f.grid_sha256,lead_scope_hours=list(_cohort(f)[4]),rows=len(values),
            population_sha256=body['population_sha256'],population_filename=name,partition=partitions.get(pin),pair_membership_sha256=identity([p.pair_sha256 for p in values]))
        counts[f.kind]+=len(values)
    if len(descriptors)>2000 or sum(c['rows'] for c in descriptors.values())!=len(rows):raise ValueError('complete bounded collection membership differs')
    result=dict(schema='earthship-native-marginal-population-collection/v1',policy_sha256=policy['policy_sha256'],metadata=metadata,rows=len(rows),counts=dict(counts),cohorts=descriptors,
        maximum_rows_per_coherent_experiment=maximum_rows,partitions=partitions,production_changed=False,local_coverage_qualified=False,automatic_actuation=False)
    result['collection_sha256']=identity(result);encoded=canonical(result)
    if len(encoded)>4*1024**2:raise ValueError('bounded marginal cohort collection descriptor exceeded')
    immutable(output/(result['collection_sha256']+'.collection.json'),encoded);return result


class FrozenInputs:
    """Resolve an immutable seed's original byte copies, never a newer source."""
    def __init__(self,path,*,read,guard=lambda:None):
        from .atmospheric_dataset import compressed_document
        self.path=Path(path);self._read=read;self.guard=guard;self.aliases={}
        body,_=compressed_document(self.path,read=read,maximum=64*1024**2)
        if (body.get('schema')!='earthship-marginal-calibration-population/v1' or body.get('population_sha256')!=identity({k:v for k,v in body.items() if k!='population_sha256'}) or
                self.path.name!=body['population_sha256']+'.population.json.gz' or not isinstance(body.get('source_inputs'),dict) or len(body['source_inputs'])>10000):raise ValueError('unchanged frozen seed identity required')
        self.seed=body;self.refs=json.loads(canonical(body['source_inputs']))

    def read(self,path,maximum,source=False):
        from hashlib import sha256
        import io
        self.guard();name=self.aliases.get(str(Path(path)),str(Path(path)));ref=self.refs.get(name)
        if ref is None:raise ValueError('original input absent from frozen seed')
        encoded=self._read(self.path.parent/'originals'/(ref['sha256']+'.bin.gz'),64*1024**2)
        with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:raw=stream.read(min(maximum,ref['maximum'])+1)
        if len(raw)>min(maximum,ref['maximum']) or sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('original retained input digest differs')
        return raw

    def stage_measurements(self,*,base,output):
        from marginal_calibration_experiment import immutable
        from .shadow import _directory
        base,output=Path(base),Path(output);_directory(output)
        allowed={'historical-measurements','historical-numeric','historical-weather-inventory'}
        for name,ref in sorted(self.refs.items()):
            self.guard();path=Path(name)
            if not path.is_relative_to(base):continue
            rel=path.relative_to(base)
            if not rel.parts or rel.parts[0] not in allowed:continue
            raw=self.read(path,ref['maximum']);target=output/rel;immutable(target,raw);self.aliases[str(target)]=name
        return output


def build_complete_population(frozen,*,base,stage,guard=lambda:None,progress=lambda **kw:None):
    from .atmospheric_dataset import read_dataset,temperature_receipts,numeric_measurements,wind_measurements
    from .probabilistic_retained import proxy_labels
    from .config import Site
    from .contracts import digest
    seed=frozen.seed;source_paths={}
    for name in frozen.refs:
        path=Path(name)
        if '/objects/' in name and path.suffix=='.json':
            pin=path.stem;digest(pin);source_paths[pin]=path
    wanted={r['snapshot_sha256'] for r in seed['original_forecasts']}
    if set(source_paths)!=wanted:raise ValueError('complete original forecast census differs from frozen seed')
    sample=json.loads(frozen.read(source_paths[min(wanted)],8*1024**2));site=Site(**sample['site']);assessed_at=instant(seed['assessed_at'])
    def dataset(pin):
        matches=[Path(p) for p in frozen.refs if Path(p).name==pin+'.dataset.json']
        if len(matches)!=1:raise ValueError('original parent dataset reference ambiguous')
        return read_dataset(matches[0].parent,pin,read=frozen.read,guard=guard)[0]
    tdata=dataset(seed['parents']['temperature']);wdata=dataset(seed['parents']['wind']);staged=frozen.stage_measurements(base=base,output=stage)
    receipts,rready=temperature_receipts(staged/'historical-measurements',tdata['measurement_manifest'],read=frozen.read,guard=guard)
    numeric,nready=numeric_measurements(staged/'historical-numeric',tdata['numeric_manifest'],receipts,site=site.__dict__,read=frozen.read,guard=guard)
    temperatures={**numeric,**receipts};ready={**nready,**rready};winds=wind_measurements(staged/'historical-weather-inventory',wdata['measurement_manifest'],read=frozen.read,guard=guard)
    originals=[]
    for name,ref in frozen.refs.items():
        if '/weather-outcomes/' not in name or not name.endswith('.json'):continue
        value=json.loads(frozen.read(Path(name),16*1024**2))
        if value.get('schema')=='earthship-qualified-solar-proxy-source/v1':originals.append(value)
    proxies=proxy_labels(originals,guard=guard);legacy={pair_key(p):p for p in seed['rows']}
    if len(legacy)!=len(seed['rows']):raise ValueError('unique legacy original source/target/cohort examples required')
    progress(phase='frozen_measurements_replayed',temperature_targets=len(temperatures),wind_hours=len(winds),proxy_hours=len(proxies))
    rows=[];contexts={};sources=[];withheld=Counter();counts=Counter();checked=exact=without=0
    for index,pin in enumerate(sorted(wanted)):
        guard();snapshot=json.loads(frozen.read(source_paths[pin],8*1024**2))
        value=pairs_for_source(snapshot,site=site,assessed_at=assessed_at,temperatures=temperatures,temperature_ready=ready,winds=winds,proxies=proxies,legacy=legacy,guard=guard)
        if value['source']['snapshot_sha256']!=pin:raise ValueError('frozen forecast original identity differs')
        rows.extend(value['pairs']);contexts.update(value['quality_contexts']);sources.append(value['source']);withheld.update(value['withheld']);checked+=value['legacy_checked'];exact+=value['legacy_exact'];without+=value['matched_without_origin_temperature']
        for p in value['pairs']:counts[p.forecast.kind]+=1
        if len(rows)>500000:raise ValueError('bounded complete native collection capacity exceeded')
        if (index+1)%50==0:progress(phase='complete_native_sources_replayed',sources=index+1,total=len(wanted),pairs=len(rows))
    if checked!=len(seed['rows']):raise ValueError('full native corpus did not replay every original legacy parent example')
    progress(phase='full_native_population_complete',pairs=len(rows),sources=len(sources),legacy_checked=checked,legacy_exact=exact)
    metadata=dict(frozen_seed_population_sha256=seed['population_sha256'],frozen_assessed_at=seed['assessed_at'],frozen_source_input_manifest_sha256=identity(seed['source_inputs']),
        source_origins=sources,parents=seed['parents'],quality_contexts=contexts,withheld=dict(withheld),counts=dict(counts),legacy_pairs_checked=checked,legacy_pairs_exact=exact,
        matched_without_origin_temperature=without,qualified_proxy_hours=len(proxies),complete_frozen_native_scope=True,
        cohort_assignment='retrospective_observed_measurement_strata_not_historical_as_issued_or_future_phase_availability',site_timezone=site.timezone)
    return rows,metadata
