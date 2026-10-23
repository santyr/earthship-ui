"""Assemble original-bound retained atmospheric ablation populations, read-only."""
from collections import Counter,defaultdict
from datetime import timedelta
from hashlib import sha256
from math import ceil,log1p
from pathlib import Path
from .contracts import canonical,identity,instant
from .config import Site
from .archive import Archive
from .atmospheric_features import prepare_atmospheric_features
from .atmospheric_dataset import document,compressed_document,read_dataset,temperature_receipts,numeric_measurements,wind_measurements
from .historical_pairs import _row as historical_row,_validate_label,_c
from .solar_experiment import BASES,make_retrospective_forcing
from .thermal_solar_experiment import eligible_window,build_trajectory,_response_rows
from .weather_response import _pair as validate_wind
from .pv_training_sources import forecast_origin


def verify_parent_replay(parent,replayed):
    if parent!=replayed:raise ValueError('parent pair differs from original forecast/measurement replay')
    return parent


def verify_temperature_parent(parent,snapshot,measurements,*,forecast_sha256=None,hours=None):
    """Check an old pair against a source already replayed by the native adapter.

    Uses the unchanged serving feature function and original historical row/
    label contracts; avoids normalizing the same provider capsule twice.
    """
    from types import SimpleNamespace
    from .historical_serving import temperature_features
    pin=forecast_sha256 or identity({k:v for k,v in snapshot.items() if k!='snapshot_sha256'})
    if hours is None:
        hours={}
        for p in snapshot['points']:
            if p['statistic']=='mean':hours.setdefault(p['valid_at'],{})[p['variable']]=p['value']
    origin,target=map(instant,(parent['origin'],parent['target_at']))
    if origin!=forecast_origin(snapshot,recorded=not snapshot['historical']):raise ValueError('original temperature origin differs from source readiness')
    outside=measurements.get(parent['origin'],{}).get('outdoor');label=measurements.get(parent['target_at'],{}).get('outdoor')
    if outside is None or label is None:raise ValueError('original origin and future measured temperature required')
    _validate_label(outside,origin)
    if instant(outside['storedAt'])>origin:raise ValueError('origin temperature was recorded after origin')
    current=hours.get(parent['origin'],{}).get('station_head_temperature_2m');future=hours.get(parent['target_at'],{}).get('station_head_temperature_2m')
    if current is None or future is None:raise ValueError('complete original station temperature support required')
    features=temperature_features(SimpleNamespace(target_at=target,mean_c=future),origin=origin,origin_bias_c=_c(outside)-current,timezone_name=snapshot['site']['timezone'])
    replayed=historical_row('outdoor_temperature_c',source=pin,origin=origin,target=target,label=label,features=features,baseline=future,
        origin_labels={'outdoor':outside},availability_basis=BASES[snapshot['historical']])
    return verify_parent_replay(parent,replayed)


def origin_inputs_available(row,availability,*,source_class):
    if source_class=='historical_assumed_availability':return True
    at=row['origin'];actual=availability.get((at,'outdoor'))
    return actual is not None and instant(actual)<=instant(at)


def _grids(adapter):return sorted({p.grid_sha256 for name,rows in adapter.series for p in rows})


def _row(parent,*,kind,baseline,outcome,base_features,features,measurement_sha256,available_at,quality,adapter,contexts=None):
    lead=(instant(features['target_at'])-instant(features['origin'])).total_seconds()/3600
    stratum=str(lead) if kind=='thermal' or lead>24 else '1-24h'
    context=dict(kind=kind,source_class=features['source_class'],measurement_quality=quality,native_grids=_grids(adapter),lead_stratum=stratum);cohort=identity(context)
    if contexts is not None:contexts[cohort]=context
    value=dict(schema='earthship-atmospheric-ablation-pair/v1',kind=kind,origin=features['origin'],target_at=features['target_at'],lead_hours=lead,
        baseline=baseline,outcome=outcome,base_features=base_features,groups=features['groups'],feature_sha256=features['feature_sha256'],forecast_sha256=features['source_sha256s'][0],
        measurement_sha256=measurement_sha256,outcome_available_at=available_at,source_ready_at=features['source_ready_at'],source_available_at=features['actual_source_available_at'],
        source_class=features['source_class'],cohort_sha256=cohort,parent_pair_sha256=parent['pair_sha256'],automatic_actuation=False)
    value['pair_sha256']=identity(value);return value


def thermal_context(parent,*,root,read,guard):
    from astro_geometry_series import replay_series
    from native_thermal_inputs import replay_native_development
    from thermal_model.training_inputs import read_training_inputs_v2
    parent=Path(parent);receipt=document(parent,'experiment_sha256',read=read,maximum=32*1024**2)
    if receipt['schema']!='earthship-retained-thermal-solar-experiment/v1' or receipt['production_changed'] is not False:raise ValueError('original Task4 thermal experiment required')
    manifest=receipt['source_runtime']
    if identity(manifest)!=receipt['source_package_sha256'] or len(manifest)>1000:raise ValueError('original thermal numerical source package differs')
    package=parent.parent/('sources-'+receipt['source_package_sha256'])/'sources'
    allowed={'openhab/scripts/weather_learning/capability_publish.py','openhab/scripts/weather_learning/capability_worker.py'}
    for name,pin in manifest.items():
        guard()
        if sha256(read(package/name,1024**2)).hexdigest()!=pin:raise ValueError('retained Task4 numerical source bytes differ')
        current=root/name
        if current.is_file() and name not in allowed and sha256(current.read_bytes()).hexdigest()!=pin:raise ValueError('numerical Task4 dependency changed before feature replay')
    refs=receipt['measurement_originals']['originals'];originals={}
    for role in ('dataset','geometry','snapshot'):
        raw=read(Path(refs[role]['path']),32*1024**2)
        if sha256(raw).hexdigest()!=refs[role]['sha256']:raise ValueError('sealed thermal original bytes differ')
        originals[role]=raw
    g=__import__('json').loads(originals['geometry']);geometry=replay_series(originals['geometry'],request=g['request'],expected_series_sha256=g['series_sha256'],expected_native_runtime=g['native_runtime'])
    record=read_training_inputs_v2(Path(refs['snapshot']['path']));saved=__import__('json').loads(originals['dataset']);phases={role:info['sensor_epoch'] for role,info in record['temperature_evidence']['roles'].items()}
    data=replay_native_development(originals['dataset'],record=record,expected_dataset_sha256=saved['dataset_sha256'],expected_snapshot_sha256=record['snapshot_sha256'],sensor_epochs=phases,geometry=geometry,expected_series_sha256=geometry.sha256)
    policy=__import__('json').loads(read(root/'docs/operations/weathernext3-capabilities/thermal-solar-protocol.json',65536,source=True))
    horizon=__import__('json').loads(read(root/'openhab/household-solar-horizon.json',16384,source=True))['profile']
    if identity(policy)!=receipt['feature_policy_sha256']:raise ValueError('original thermal feature policy differs')
    candidates=[]
    for path in parent.parent.glob('*.pairs.json.gz'):
        value,_=compressed_document(path,read=read)
        if value['dataset_sha256']!=identity({k:v for k,v in value.items() if k!='dataset_sha256'}):raise ValueError('original thermal feature dataset differs')
        if value['measurement_snapshot_sha256']==record['snapshot_sha256'] and value['feature_policy_sha256']==identity(policy):candidates.append(value)
    if len(candidates)!=1:raise ValueError('one exact Task4 comparable thermal pair dataset required')
    rows=_response_rows(candidates[0]['pairs'],policy)
    if len(rows)!=receipt['matched_feature_pairs']:raise ValueError('complete comparable thermal population required')
    samples={r['at']:r for r in data.to_dict()['samples']};positions={p['at']:p for cache in geometry.to_dict()['caches'] for p in cache['positions']}
    return dict(receipt=receipt,pairs=rows,samples=samples,positions=positions,data=data,record=record,phases=phases,site=Site(**dict(g['request']['site'],timezone=g['request']['timezone'])),policy=policy,horizon=horizon)


def build_retained_rows(*,base,temperature_parent,wind_parent,thermal_parent,root,assessed_at,read,guard,progress=lambda **kwargs:None):
    from datetime import timezone
    base,root=Path(base),Path(root);rows=[];feature_packets=[];excluded=[];parents={};counts=Counter();weather={};cohort_contexts={}
    thermal=thermal_context(thermal_parent,root=root,read=read,guard=guard);site=thermal['site'];progress(phase='sealed_thermal_replayed',samples=len(thermal['samples']))
    temp_receipt=document(Path(temperature_parent)/'experiment.json','receipt_sha256',read=read)
    temp_data,temp_rows=read_dataset(temperature_parent,temp_receipt['datasets']['outdoor_temperature_c'],read=read,guard=guard)
    temp_rows=[r for r in temp_rows if r['lead_hours']<=24];counts['temperature_parent_near_pairs']=len(temp_rows)
    wind_receipt=document(Path(wind_parent)/'experiment.json','receipt_sha256',read=read)
    wind_data,wind_rows=read_dataset(wind_parent,wind_receipt['dataset_sha256'],read=read,guard=guard)
    wind_rows=[r for r in wind_rows if r['kind']=='wind_m_s'];counts['wind_parent_pairs']=len(wind_rows);counts['thermal_parent_pairs']=len(thermal['pairs'])
    if sum(counts.values())>10000:raise ValueError('frozen total original population exceeds10000pairs')
    parents.update(temperature=temp_data['dataset_sha256'],wind=wind_data['dataset_sha256'],thermal=thermal['receipt']['experiment_sha256'])
    receipts,receipt_availability=temperature_receipts(base/'historical-measurements',temp_data['measurement_manifest'],read=read,guard=guard)
    numeric,numeric_availability=numeric_measurements(base/'historical-numeric',temp_data['numeric_manifest'],receipts,site=site.__dict__,read=read,guard=guard)
    measurements={**numeric,**receipts};availability={**numeric_availability,**receipt_availability};progress(phase='temperature_originals_replayed',targets=len(measurements))
    winds=wind_measurements(base/'historical-weather-inventory',wind_data['measurement_manifest'],read=read,guard=guard);progress(phase='wind_originals_replayed',hours=len(winds))
    archives=[Archive.open_readonly(str(base/name)) for name in ('historical-2026','archive')];compiled={}
    temp_by_source=defaultdict(list);wind_by_source=defaultdict(list);thermal_by_source=defaultdict(list)
    for r in temp_rows:temp_by_source[r['forecast_sha256']].append(r)
    for r in wind_rows:wind_by_source[r['source_sha256']].append(r)
    for r in thermal['pairs']:thermal_by_source[r['forecast_sha256']].append(r)
    all_sources=sorted(set(temp_by_source)|set(wind_by_source)|set(thermal_by_source))
    def source(pin):
        guard();archive=next((a for a in archives if (a.objects/(pin+'.json')).is_file()),None)
        if archive is None:raise ValueError('exact parent forecast original missing')
        read(archive.objects/(pin+'.json'),8*1024**2);snapshot=archive.read(pin)
        adapter=prepare_atmospheric_features(snapshots=[snapshot],site=site,assessed_at=assessed_at,availability_basis=BASES[snapshot['historical']],guard=guard)
        if list(adapter.source_sha256s)!=[pin]:raise ValueError('forecast parent digest differs')
        weather[pin]=dict(snapshot_sha256=pin,initialized_at=snapshot['initialized_at'],first_seen_at=snapshot['first_seen_at'],ingestion_completed_at=snapshot['ingestion_completed_at'],historical=snapshot['historical'],site_sha256=identity(site.__dict__))
        return snapshot,adapter
    for index,pin in enumerate(all_sources):
        snapshot,adapter=source(pin)
        hourly={}
        for p in snapshot['points']:
            if p['statistic']=='mean':hourly.setdefault(p['valid_at'],{})[p['variable']]=p['value']
        wanted=temp_by_source[pin]
        if wanted:
            for parent in wanted:
                verify_temperature_parent(parent,snapshot,measurements,forecast_sha256=pin,hours=hourly)
                if not origin_inputs_available(parent,availability,source_class=adapter.source_class):
                    excluded.append(dict(kind='temperature',parent_pair_sha256=parent['pair_sha256'],source_class=adapter.source_class,reason='origin_observation_not_available_at_recorded_decision'));continue
                features=adapter.features(kind='temperature',origin=instant(parent['origin']),target=instant(parent['target_at']));label=parent['label'];quality={k:label.get(k) for k in ('provenance','measurement_health_qualified','receiptVersion','sensorEpoch','sourceModel','sourceSensorId','sourceItem','unit','unit_basis')}
                if label['receivedAt'] is not None:quality['receipt_validity_seconds']=(instant(label['validUntil'])-instant(label['receivedAt'])).total_seconds()
                expected_names=['google_c','hour_cos','hour_sin','lead_days','origin_bias_decay_c','season_cos','season_sin']
                if sorted(parent['features'])!=expected_names:raise ValueError('original seven-feature temperature base differs')
                rows.append(_row(parent,kind='temperature',baseline=parent['baseline'],outcome=parent['outcome'],base_features=[parent['features'][k] for k in expected_names],features=features,
                    measurement_sha256=identity(label),available_at=availability[(parent['target_at'],'outdoor')],quality=quality,adapter=adapter,contexts=cohort_contexts));feature_packets.append(features)
        for parent in wind_by_source[pin]:
            validate_wind(parent);label=winds.get(parent['target_end']);left=hourly.get(parent['target_start'],{}).get('wind_speed_10m');right=hourly.get(parent['target_end'],{}).get('wind_speed_10m')
            if label is None or left is None or right is None or abs(parent['baseline']-(left+right)/2)>1e-9 or abs(parent['outcome']-label['mean_m_s'])>1e-9 or parent['measurement_sha256']!=label['source_sha256']:
                raise ValueError('wind parent differs from exact native boundary means or measured hour')
            if instant(parent['origin'])!=forecast_origin(snapshot,recorded=not snapshot['historical']):raise ValueError('wind parent origin differs from source readiness')
            features=adapter.features(kind='wind',origin=instant(parent['origin']),target=instant(parent['target_end']))
            rows.append(_row(parent,kind='wind',baseline=parent['baseline'],outcome=parent['outcome'],base_features=[log1p(parent['baseline'])],features=features,
                measurement_sha256=parent['measurement_sha256'],available_at=label['actual_available_at'],quality=dict(measurement_quality=parent['measurement_quality'],measurement_health_qualified=False),adapter=adapter,contexts=cohort_contexts));feature_packets.append(features)
        windows=thermal_by_source[pin]
        if windows:
            first=min(instant(r['origin']) for r in windows);end=max(instant(r['target_at']) for r in windows);source_origin=forecast_origin(snapshot,recorded=not snapshot['historical'])
            forcing=make_retrospective_forcing(snapshot,origin=source_origin,horizon_hours=ceil((end-source_origin).total_seconds()/3600),site=site,assessed_at=assessed_at,availability_basis=BASES[snapshot['historical']])
            floor=first.replace(minute=0,second=0,microsecond=0);ceiling=end.replace(minute=0,second=0,microsecond=0)
            if ceiling<end:ceiling+=timedelta(hours=1)
            positions=[p for at,p in thermal['positions'].items() if floor<instant(at)<=ceiling];positions.sort(key=lambda p:p['at'])
            trajectory=build_trajectory(forcing=forcing,positions=positions,start=first,end=end,horizon_profile=thermal['horizon'],policy=thermal['policy'],force_total_only=True)
            expected_cohort=identity(dict(sensor_epochs=thermal['phases'],temperature_policy=thermal['record']['temperature_evidence'],solar_grid=forcing['rows'][0]['solar']['grid_sha256'],horizon_sha256=identity(thermal['horizon'])))
            for parent in windows:
                guard();origin,target=map(instant,(parent['origin'],parent['target_at']));initial=thermal['samples'][parent['origin']];outcome=thermal['samples'][parent['target_at']]
                ok,reason=eligible_window(thermal['samples'],origin=origin,target=target,barriers=thermal['data'].development.ineligible_action_times,late_intervals=thermal['data'].development.unavailable_origin_intervals)
                actual=trajectory.features(origin_state=initial,start=origin,end=target)['features']
                expected_measurement=identity(dict(snapshot=thermal['record']['snapshot_sha256'],target_at=parent['target_at'],role='air',sensor_epoch=thermal['phases']['air']))
                if (not ok or parent['cohort_sha256']!=expected_cohort or parent['measurement_sha256']!=expected_measurement or parent['origin_air_f']!=initial['air_f'] or parent['outcome_f']!=outcome['air_f'] or
                        any(abs(a-b)>1e-9*max(1.,abs(a),abs(b)) for a,b in zip(actual,parent['total_features']))):raise ValueError('comparable thermal source/state/action/feature replay differs')
                features=adapter.features(kind='thermal',origin=origin,target=target)
                rows.append(_row(parent,kind='thermal',baseline=parent['origin_air_f'],outcome=parent['outcome_f'],base_features=actual,features=features,
                    measurement_sha256=parent['measurement_sha256'],available_at=parent['available_at'],quality=dict(parent_cohort_sha256=parent['cohort_sha256'],measurement_health='original_sealed_air_north_wall_state',action_trajectory='complete_unchanged_passive'),adapter=adapter,contexts=cohort_contexts));feature_packets.append(features)
        if (index+1)%25==0:progress(phase='forecast_originals_replayed',sources=index+1,total=len(all_sources),pairs=len(rows))
    progress(phase='originals_complete',sources=len(all_sources),pairs=len(rows),excluded=len(excluded))
    from .atmospheric_ablation import validate_rows
    validate_rows(rows)
    return dict(rows=rows,feature_packets=feature_packets,cohort_contexts=cohort_contexts,excluded=excluded,parents=parents,parent_counts=dict(counts),weather_originals=[weather[k] for k in sorted(weather)],timezone=site.timezone)
