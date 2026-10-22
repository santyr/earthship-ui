"""Forecast-only original shadow issues; no selector, fitting or Item writes."""
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
from .contracts import canonical,identity,instant,finite
from .evidence import utc
from . import probabilistic as k
from .probabilistic_artifacts import CandidateBundle,load_candidate_bundle,predict_candidates,candidate_frame
from .probabilistic_retained import prepare_marginal_source

PRODUCT_OFFSETS=(*range(1,25),48,72,120,168,240,336)
SCORE_OFFSETS=(1,3,6,12,24,48,72,120,168,240,336)
CONTRACT=dict(schema='earthship-prospective-marginal-issue-contract/v1',display_offsets=PRODUCT_OFFSETS,score_offsets=SCORE_OFFSETS,
    maturity_seconds=120,arrival_allowance_days=7,maximum_rows=96,maximum_label_attempts=8,
    population='original_emitted_read_only_shadow_issues_not_core_forecast_skill',automatic_actuation=False)
CONTRACT_SHA256=identity(CONTRACT)


class OriginContext(k._Frozen):
    __slots__=()
    def quality_at(self,decision):
        from datetime import timedelta
        body=self.to_dict();decision=utc(decision);sampled,acquired=map(instant,(body['sampled_at'],body['acquired_at']))
        if not sampled<=acquired<=decision<=sampled+timedelta(seconds=120):raise ValueError('origin context not available or expired at decision')
        if body['kind']=='temperature':
            from weather_temperature_reader import validate_temperature_metadata_v2
            from weather_temperature_evidence import TemperaturePolicy
            from daily_temperature_runtime import SOURCE_POLICY
            metadata=body['original'];validate_temperature_metadata_v2(metadata,decision,policy=TemperaturePolicy(**SOURCE_POLICY),sensor_epoch=body['sensor_epoch'])
            quality={key:None for key in ('provenance','measurement_health_qualified','sourceItem','unit','unit_basis')}
            quality.update(receiptVersion=2,sensorEpoch=body['sensor_epoch'],sourceModel=SOURCE_POLICY['model'],sourceSensorId=SOURCE_POLICY['sensor_id'],
                receipt_validity_seconds=(instant(metadata['validUntil'])-instant(metadata['receivedAt'])).total_seconds())
            return quality
        if body['kind']=='wind':return dict(provenance='numeric_mph_without_sensor_health_receipts',measurement_health_qualified=False,unit='m_s',target='complete_one_hour_mean_scalar')
        from weather_radiation_reader import select_radiation_at
        from weather_radiation_evidence import RadiationPolicy
        policy=RadiationPolicy(**body['policy']);rows=[(instant(at),raw) for at,raw in body['original']]
        value=select_radiation_at(rows,target=decision,assessed_at=decision,history_start=sampled-timedelta(seconds=policy.validity_seconds),cutover=instant(body['cutover']),policy=policy)
        if value is None or value['fault_visibility']!='verified':raise ValueError('qualified origin proxy epoch unavailable')
        return dict(provenance='source_qualified_lux_to_solar_proxy',stream_epoch=value['streamEpoch'],policy=body['policy'],source_item='Weather_Radiation_Evidence_JSON',physical_irradiance_calibration_qualified=False)


def temperature_context(metadata,*,sampled_at,acquired_at,sensor_epoch):
    from weather_temperature_reader import validate_temperature_metadata_v2
    from weather_temperature_evidence import TemperaturePolicy,sensor_epoch_id
    from daily_temperature_runtime import SOURCE_POLICY
    sampled,acquired=map(utc,(sampled_at,acquired_at));validate_temperature_metadata_v2(metadata,sampled,policy=TemperaturePolicy(**SOURCE_POLICY),sensor_epoch=sensor_epoch)
    if not instant(metadata['storedAt'].isoformat() if hasattr(metadata['storedAt'],'isoformat') else metadata['storedAt'])<=acquired or not sampled<=acquired:
        raise ValueError('actual origin acquisition precedes persisted metadata')
    from .features import _jsonable
    body=dict(kind='temperature',sampled_at=sampled.isoformat(),acquired_at=acquired.isoformat(),sensor_epoch=sensor_epoch_id(sensor_epoch),original=_jsonable(metadata))
    return k._freeze(OriginContext,body,'context_sha256')


def wind_context(*,decision):
    at=utc(decision).isoformat();return k._freeze(OriginContext,dict(kind='wind',sampled_at=at,acquired_at=at,original='fixed_existing_numeric_mph_reader_no_health_claim'),'context_sha256')


def proxy_context(rows,*,sampled_at,acquired_at,policy,cutover):
    from .features import _jsonable
    sampled,acquired=map(utc,(sampled_at,acquired_at))
    if not sampled<=acquired or not isinstance(rows,(tuple,list)) or len(rows)>10000:raise ValueError('bounded actually acquired origin proxy context required')
    body=dict(kind='solar_proxy',sampled_at=sampled.isoformat(),acquired_at=acquired.isoformat(),policy=asdict(policy),cutover=utc(cutover).isoformat(),original=[[utc(at).isoformat(),raw] for at,raw in rows])
    value=k._freeze(OriginContext,body,'context_sha256');value.quality_at(acquired);return value


class MarginalIssue(k._Frozen):
    __slots__=()


def _context(value):
    if not isinstance(value,dict) or value.get('context_sha256')!=identity({n:v for n,v in value.items() if n!='context_sha256'}) or value.get('kind') not in k.KINDS:raise ValueError('original marginal origin context required')
    obj=object.__new__(OriginContext);object.__setattr__(obj,'_raw',canonical(value));return obj


def _fallback(frame,reason,policy):
    families=('empirical','temperature_normal') if frame.kind=='temperature' else ('empirical','nonnegative')
    return dict(status='raw_fallback',reason=reason,bundle_sha256=None,raw=dict(mean=frame.baseline,p10=frame.p10,p50=frame.p50,p90=frame.p90),
        marginals={name:None for name in families},adaptive=k.adaptive_point(None,frame,policy=policy) if frame.kind=='temperature' else None,
        local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)


def prepare_marginal_issue(*,snapshots,decision,site,contexts,bundles,policy,guard=lambda:None):
    from .config import Site
    decision=utc(decision);policy=k._policy(policy)
    if (not isinstance(site,Site) or not isinstance(snapshots,list) or len(snapshots)>8 or not isinstance(contexts,dict) or not set(contexts)<=set(k.KINDS) or
            any(not isinstance(v,OriginContext) or v.to_dict()['kind']!=kind for kind,v in contexts.items()) or
            not isinstance(bundles,list) or len(bundles)>12 or any(not isinstance(v,CandidateBundle) for v in bundles)):raise ValueError('bounded source-bound optional marginal issue inputs required')
    compiled=[];source_originals={};withheld={};original_bundles={};qualities={};working_bundles=[]
    for kind,context in contexts.items():
        try:qualities[kind]=context.quality_at(decision)
        except (ValueError,KeyError,TypeError):withheld[kind]='origin_measurement_context_unavailable'
    for snapshot in snapshots:
        guard()
        try:
            if snapshot['historical'] or instant(snapshot['ingestion_completed_at'])>decision or decision-instant(snapshot['initialized_at'])>timedelta(hours=24):continue
            if snapshot['site']!=site.__dict__:raise ValueError('original marginal source site differs')
            source=prepare_marginal_source(snapshot,assessed_at=decision);compiled.append(source);source_originals[source.snapshot_sha256]=snapshot
        except (ValueError,KeyError,TypeError):withheld['source']='native_source_unavailable'
    for bundle in bundles:
        body=bundle.to_dict();pin=body['bundle_sha256']
        if pin in original_bundles:raise ValueError('unique original marginal candidate bundles required')
        original_bundles[pin]=body
        try:load_candidate_bundle(body,expected_sha256=pin,policy=policy)
        except ValueError:
            withheld['candidate_'+body['kind']]='candidate_numeric_runtime_changed';continue
        working_bundles.append(bundle)
    first=decision.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1);rows=[]
    for offset in PRODUCT_OFFSETS:
        at=first+timedelta(hours=offset-1)
        if at>decision+timedelta(hours=336):continue
        for kind in k.KINDS:
            guard()
            if kind!='temperature' and at-timedelta(hours=1)<decision:continue
            quality=qualities.get(kind,dict(origin_context_status='unavailable_no_candidate_cohort'))
            choices=[]
            for source in compiled:
                if at>instant(source.initialized_at)+timedelta(hours=360):continue
                frame=source.forecast(kind,target=at,quality=quality,origin=decision)
                if frame is not None:choices.append((source.initialized_at,source.actual_available_at,source.snapshot_sha256,frame))
            if not choices:continue
            frame=max(choices,key=lambda c:c[:3])[3];candidates=[b for b in working_bundles if candidate_frame(b,frame) is not None]
            if len(candidates)>1:raise ValueError('ambiguous marginal candidate bundle; no automatic selection')
            if kind not in qualities:value=_fallback(frame,'origin_measurement_context_unavailable',policy)
            elif not candidates:value=_fallback(frame,withheld.get('candidate_'+kind,'candidate_bundle_unavailable'),policy)
            else:
                frame=candidate_frame(candidates[0],frame);value=predict_candidates(candidates[0],frame,policy=policy)
            raw=dict(mean=frame.baseline,p10=frame.p10,p50=frame.p50,p90=frame.p90)
            row=dict(offset=offset,forecast=asdict(frame),raw=raw,candidates=value);row['row_sha256']=identity(row);rows.append(row)
    active=any(r['candidates']['status']=='read_only_shadow_candidates' for r in rows)
    body=dict(schema='earthship-original-marginal-shadow-issue/v1',decision_at=decision.isoformat(),site=site.__dict__,status='read_only_shadow_candidates' if active else 'raw_fallback' if rows else 'raw_unavailable',
        rows=rows,source_originals=source_originals,bundle_originals=original_bundles,origin_context_originals={kind:v.to_dict() for kind,v in contexts.items()},
        withheld=withheld,contract_sha256=CONTRACT_SHA256,policy_sha256=policy['policy_sha256'],issued=False,core_forecast_modified=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    if len(canonical(body))>16*1024**2:raise ValueError('bounded original marginal issue required')
    return k._freeze(MarginalIssue,body,'issue_sha256')


def validate_marginal_issue(value,*,policy,replay=False):
    from .config import Site
    from .probabilistic_evaluation import score_retained_prediction
    policy=k._policy(policy)
    fields={'schema','decision_at','site','status','rows','source_originals','bundle_originals','origin_context_originals','withheld','contract_sha256','policy_sha256','issued','core_forecast_modified','local_coverage_qualified','probability_claim','automatic_actuation','issue_sha256'}
    if (not isinstance(value,dict) or set(value)!=fields or value['schema']!='earthship-original-marginal-shadow-issue/v1' or value['issue_sha256']!=identity({n:v for n,v in value.items() if n!='issue_sha256'}) or
            value['contract_sha256']!=CONTRACT_SHA256 or value['policy_sha256']!=policy['policy_sha256'] or not isinstance(value['rows'],list) or len(value['rows'])>96 or
            any(value[n] is not False for n in ('issued','core_forecast_modified','local_coverage_qualified','probability_claim','automatic_actuation'))):raise ValueError('unchanged original marginal issue required')
    for row in value['rows']:
        if row['row_sha256']!=identity({n:v for n,v in row.items() if n!='row_sha256'}):raise ValueError('original marginal row differs')
        raw=dict(row['forecast']);raw.pop('input_sha256');frame=k.ForecastInput(**raw)
        if asdict(frame)!=row['forecast'] or frame.origin!=value['decision_at'] or frame.availability_basis!='recorded_ingestion_availability':raise ValueError('original prospective marginal forecast differs')
        for prediction in row['candidates']['marginals'].values():
            if prediction is not None:score_retained_prediction(prediction,frame.baseline)
    if replay:
        contexts={kind:_context(v) for kind,v in value['origin_context_originals'].items()};bundles=[load_candidate_bundle(v,expected_sha256=pin,policy=policy,require_current=False) for pin,v in value['bundle_originals'].items()]
        rebuilt=prepare_marginal_issue(snapshots=list(value['source_originals'].values()),decision=instant(value['decision_at']),site=Site(**value['site']),contexts=contexts,bundles=bundles,policy=policy).to_dict()
        if rebuilt!=value:raise ValueError('original marginal prediction/source/model replay differs')
    return value


def scoring_rows(value):return [r for r in value['rows'] if r['offset'] in SCORE_OFFSETS]
