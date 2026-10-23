"""Explicit selected production points, distinct from native physical forcing.

Compilation grants no installation or publication authority. Original provider,
source, current measurement context and selected-model identities are retained;
actual successful emission is a separate durable receipt owned by the publisher.
"""
import json
from dataclasses import asdict
from datetime import datetime,timedelta,time,timezone
from zoneinfo import ZoneInfo
from .contracts import canonical,identity,instant
from .evidence import utc
from .provider import ProviderSnapshot,forecast_payloads
from .probabilistic import _Frozen,_freeze
from .probabilistic_issue import OriginContext
from .probabilistic_retained import prepare_marginal_source
from .production_training import ProductionBundle,production_frame
from .production_model_admission import predict_production

SCHEMA='earthship-selected-production-weather/v1'
MPH=3600/1609.344


class ProductionForecast(_Frozen):
    __slots__=()


def prepare_production_forecast(*,provider,read_source,contexts,models,policy,authorize,guard=lambda:None):
    """Use one registered fitted method per matching target; never fit or rank."""
    if (not isinstance(provider,ProviderSnapshot) or not callable(read_source) or not callable(authorize) or
            not isinstance(contexts,dict) or not set(contexts)<={'temperature','wind'} or
            any(not isinstance(c,OriginContext) or c.to_dict()['kind']!=kind for kind,c in contexts.items()) or
            not isinstance(models,list) or len(models)>12):raise ValueError('explicit source/context/model/production owner required')
    value=provider.to_dict();decision=instant(value['decision_at']);registered={};qualities={};withheld={}
    def owner(receipt):
        original=canonical(receipt)
        if authorize(receipt) is not True or canonical(receipt)!=original:
            raise PermissionError('unchanged current production owner admission required')
        return True
    for bundle,admission in models:
        if not isinstance(bundle,ProductionBundle) or bundle.to_dict()['kind'] not in ('temperature','wind'):
            raise ValueError('explicit actually fitted weather production bundle required')
        pin=bundle.to_dict()['bundle_sha256']
        if pin in registered:raise ValueError('unique explicit production models required')
        copied=json.loads(canonical(admission))
        if authorize(copied) is not True or copied!=admission:raise ValueError('unchanged current production owner admission required')
        registered[pin]=(bundle,admission)
    for kind,context in contexts.items():
        try:qualities[kind]=context.quality_at(decision)
        except (ValueError,KeyError,TypeError):withheld[kind]='origin_measurement_context_unavailable'
    profiles=[('extended',value,value.get('extended_status',value['status']))]
    if 'near_term' in value:profiles.append(('nearTerm',value['near_term'],value['near_term']['status']))
    rows=[];sources={}
    for profile,body,status in profiles:
        if status!='AVAILABLE':continue
        pin=body['source']['snapshot_sha256'];guard()
        if pin not in sources:
            original=read_source(pin);source=prepare_marginal_source(original,assessed_at=decision)
            if source.snapshot_sha256!=pin or source.historical or decision-instant(source.initialized_at)>timedelta(hours=24):
                raise ValueError('original actually available production source required')
            sources[pin]=(source,original)
        source=sources[pin][0]
        for hour in body['hours']:
            at=instant(hour['at'])
            for kind in ('temperature','wind'):
                guard();prediction=None;frame=None;reason=None
                raw=hour['temp_f'] if kind=='temperature' else hour['wind_mph']
                if kind not in qualities:reason='origin_measurement_context_unavailable'
                elif at>decision+timedelta(hours=336):reason='target_outside_registered_lead_scope'
                elif kind=='wind' and at-timedelta(hours=1)<decision:reason='hour_interval_already_in_progress'
                else:
                    frame=source.forecast(kind,target=at,quality=qualities[kind],origin=decision)
                    if frame is None:reason='native_target_inputs_unavailable'
                    else:
                        if kind=='temperature' and raw is not None and abs(frame.baseline*9/5+32-raw)>1e-8:
                            raise ValueError('original provider temperature differs from native source')
                        matching=[(b,a) for b,a in registered.values() if production_frame(b,frame) is not None]
                        if len(matching)>1:raise ValueError('ambiguous production models for one target')
                        if not matching:reason='registered_model_cohort_unavailable'
                        else:
                            b,a=matching[0]
                            # Owner refusal is not an optional-domain fallback.
                            check=json.loads(canonical(a))
                            if authorize(check) is not True or check!=a:raise ValueError('current production owner refused')
                            try:prediction=predict_production(b,a,frame,policy=policy,authorize=owner)
                            except ValueError:reason='registered_model_invalid_expired_or_missing_statistics'
                rows.append(dict(profile=profile,kind=kind,at=hour['at'],source_sha256=pin,raw_presentation_value=raw,
                    forecast=None if frame is None else asdict(frame),prediction=prediction,reason=reason))
    if len(rows)>1344:raise ValueError('bounded full production forecast required')
    result=dict(schema=SCHEMA,decision_at=value['decision_at'],provider_snapshot_sha256=value['provider_snapshot_sha256'],
        rows=rows,source_originals={p:original for p,(_,original) in sources.items()},
        model_originals={p:b.to_dict() for p,(b,_) in registered.items()},admissions={p:a for p,(_,a) in registered.items()},
        origin_contexts={k:c.to_dict() for k,c in contexts.items()},withheld=withheld,
        issued=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    return _freeze(ProductionForecast,result,'issue_sha256')


def _original(product,provider,now):
    if not isinstance(product,ProductionForecast) or not isinstance(provider,ProviderSnapshot):raise ValueError('original prepared production product required')
    body=product.to_dict();value=provider.to_dict()
    if body['decision_at']!=utc(now).isoformat() or body['provider_snapshot_sha256']!=value['provider_snapshot_sha256']:
        raise ValueError('exact original provider and decision required')
    return body


def production_payloads(product,*,provider,now):
    body=_original(product,provider,now);hourly,daily,detail=forecast_payloads(provider,now=now)
    rows={(r['profile'],r['kind'],instant(r['at'])):r for r in body['rows']};zone=ZoneInfo(detail['timezone']);decision=utc(now)
    def point(profile,kind,at):
        row=rows.get((profile,kind,at));p=None if row is None else row['prediction']
        if p is not None:return p['point_estimate']*9/5+32 if kind=='temperature' else p['point_estimate']*MPH
        return None if row is None else row['raw_presentation_value']
    def selected(profile,kind,at):
        row=rows.get((profile,kind,at));return row is not None and row['prediction'] is not None
    for day in detail['days']:
        for h in day['hours']:
            at=instant(h['at']);profile=h.get('forecastProfile','extended')
            h['tempF']=point(profile,'temperature',at)
            if selected(profile,'wind',at):h['windMeanMph']=point(profile,'wind',at)
            # V3 omits unsupported optional nulls to keep the ten-day Item bounded.
            h.pop('precipPct');h.pop('weatherCode')
        summary=day['summary'];profile=summary.get('forecastProfile','extended')
        start=datetime.combine(datetime.fromisoformat(day['date']).date(),time.min,zone).astimezone(timezone.utc)
        end=datetime.combine(datetime.fromisoformat(day['date']).date()+timedelta(days=1),time.min,zone).astimezone(timezone.utc)
        scope='remaining' if start<=decision<end else 'full_day'
        at=start
        if scope=='remaining':
            at=decision.replace(minute=0,second=0,microsecond=0)
            if at<=decision:at+=timedelta(hours=1)
        values=[]
        while at<end:
            v=point(profile,'temperature',at)
            if v is None:values=[];break
            values.append(v);at+=timedelta(hours=1)
        summary.update(highF=max(values) if values else None,lowF=min(values) if values else None,
            temperatureScope=scope,temperatureStatistic='extrema_of_hourly_point_forecasts')
    by_at={instant(h['at']):h for d in detail['days'] for h in d['hours']}
    for h in hourly:
        shown=by_at.get(instant(h['at']))
        if shown is not None:h['t']=None if shown['tempF'] is None else round(shown['tempF'])
    for short,day in zip(daily,detail['days']):
        for key,full in [('hi','highF'),('lo','lowF')]:
            v=day['summary'][full];short[key]=None if v is None else round(v)
    used=sum(r['prediction'] is not None for r in body['rows'])
    detail.pop('model',None)
    detail['learningNamespace']='weathernext3-selected-production-v1'
    detail.update(version=3,productionModel=dict(issueSha256=body['issue_sha256'],
        status='ACTIVE' if used==len(body['rows']) and used else 'MIXED_WITH_RAW_FALLBACK' if used else 'RAW_FALLBACK',
        localCoverageQualified=False,probabilityClaim=False,temperatureStatistic='model_point_with_declared_raw_fallback',
        windStatistic='native_instantaneous_with_separate_local_hour_mean'))
    return hourly,daily,detail
