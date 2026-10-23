"""Matched publication-policy diagnostics; no daily benchmark mutation or fitting.

Actual served forecasts and known-at-decision policy replays are distinguished.
Near endpoints are complete; declared long leads bound durable verification work.
Original publication capsules continue to retain the complete extended product.
"""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from math import fsum,sqrt
from pathlib import Path
from random import Random
from zoneinfo import ZoneInfo

from .contracts import digest,finite,identity,instant
from .evidence import utc
from .features import TemperatureOutcome
from .near_term_correction import PROFILE
from .refresh_evaluation import RefreshRecord,_checked,_freeze,publication_decision,refresh_profiles

LONG_OFFSETS=(48,72,120,168,240,336)
POLICIES=('actual_serving','latest_48h_collection','latest_360h_collection',PROFILE)
PAIRS=(('latest_48h_collection','latest_360h_collection'),('actual_serving','latest_48h_collection'),
       ('actual_serving','latest_360h_collection'),(PROFILE,'actual_serving'))
CONTRACT=dict(schema='earthship-refresh-score-contract/v1',population='actual_successful_retained_publication_decisions',
    near='all native endpoints through ceil(decision+24h)',long_offsets=LONG_OFFSETS,
    maturity_seconds=120,arrival_allowance_days=7,
    weighting='equal_local_target_dates_then_equal_measured_targets_then_equal_forecast_origins',
    candidate_basis='known_at_original_decision_replay_not_claimed_issued',maximum_rows=10000,
    minimum_targets=24,minimum_local_dates=3,minimum_gain=.03,minimum_subgroup_targets=12,maximum_subgroup_regression=.05,
    bootstrap_repetitions=128,bootstrap_seed=20261021,probability_claim=False,automatic_actuation=False)
CONTRACT_SHA256=identity(CONTRACT)


def _producer():
    root=Path(__file__).parent
    return identity({name:sha256((root/name).read_bytes()).hexdigest() for name in
        ('refresh_scoring.py','refresh_evaluation.py','near_term_correction.py','historical_serving.py','site_calibration.py','contracts.py')})


def _record(value,schema):
    if not isinstance(value,RefreshRecord):raise ValueError('original prepared refresh record required')
    body=_checked(value.to_dict(),'record_sha256')
    if body['schema']!=schema or body['automatic_actuation'] is not False:raise ValueError('original read-only refresh record required')
    return body


def _forecast(value,source,*,published=False,reason=None,local=None,model=None):
    return dict(value_c=value,raw_c=value if local is None else local['raw_c'],local_c=None if local is None else local['local_c'],
        source=source,actually_published=published,
        availability_basis='recorded_published' if published else 'known_at_decision_policy_replay',
        reason=reason,model_sha256=model,revision_c=None,previous_decision_sha256=None)


def compile_refresh_decision(attempt,result,*,archive,site,near=None,previous=None,clock=lambda:datetime.now(timezone.utc)):
    """Reconstruct actual publication and alternative selections without outcomes."""
    published=publication_decision(attempt,result,archive=archive,site=site).to_dict()
    decision=instant(published['decision_at']);confirmed=instant(published['publication_completed_at'])
    compiled=utc(clock())
    if compiled<confirmed:raise ValueError('compilation precedes original publication')
    refresh=refresh_profiles(archive,decision_at=decision,site=site).to_dict()
    prior=None;previous_rows={}
    if previous is not None:
        prior=_record(previous,'earthship-refresh-decision/v1')
        if not instant(prior['decision_at'])<decision or instant(prior['publication_completed_at'])>decision:
            raise ValueError('earlier confirmed original decision required for revision')
        previous_rows={row['target_at']:row['forecasts'] for row in prior['targets']}
        # Long-lead revision uses the retained complete published product, even
        # when that target was not in the earlier bounded verification sample.
        for row in prior['publication']['hours']:
            previous_rows.setdefault(row['at'],{})['actual_serving']={'value_c':row['raw_c']}
    corrected=None;near_index={}
    if near is not None:
        corrected=_record(near,'earthship-near-term-local-correction/v1')
        if corrected['decision_at']!=decision.isoformat() or corrected['profile']!=PROFILE or corrected['issued'] is not False:
            raise ValueError('same-decision independent prepared near24 profile required')
        near_index={row['at']:row for row in corrected['hours']}
    candidate_index={key:{row['at']:row for row in value['hours']} for key,value in refresh['profiles'].items()}
    first=decision.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
    near_end=(decision+timedelta(hours=24)).replace(minute=0,second=0,microsecond=0)
    if near_end<decision+timedelta(hours=24):near_end+=timedelta(hours=1)
    targets=[];elapsed=0
    for row in published['hours']:
        at=instant(row['at']);offset=int((at-first).total_seconds()/3600)+1
        if at>near_end and offset not in LONG_OFFSETS:continue
        if at<=confirmed:elapsed+=1;continue
        source=published['profiles'][row['profile']]['source']
        forecasts={'actual_serving':_forecast(row['raw_c'],source,published=True)}
        for key in ('latest_48h_collection','latest_360h_collection'):
            match=candidate_index[key].get(row['at']);profile=refresh['profiles'][key]
            forecasts[key]=_forecast(None if match is None else match['raw_c'],None if match is None else profile['source'],
                reason=profile['reason'] if match is None else None)
            if match is None and forecasts[key]['reason'] is None:forecasts[key]['reason']='OUTSIDE_COMPARISON_HORIZON'
        if at<=near_end:
            local=near_index.get(row['at']);model=None
            if local is not None:
                if corrected['source']['snapshot_sha256']!=source['snapshot_sha256'] or abs(local['raw_c']-row['raw_c'])>1e-9:
                    raise ValueError('near24 correction must use original published near source')
                model=None if corrected['model'] is None else corrected['model']['model_sha256']
            forecasts[PROFILE]=_forecast(row['raw_c'] if local is None else local['selected_c'],source,
                reason='NEAR24_NOT_PREPARED' if corrected is None else corrected['reason'],local=local,model=model)
        else:forecasts[PROFILE]=_forecast(None,None,reason='OUTSIDE_CORRECTION_HORIZON')
        for policy,forecast in forecasts.items():
            old=previous_rows.get(row['at'],{}).get(policy)
            if old is not None and old['value_c'] is not None and forecast['value_c'] is not None:
                forecast.update(revision_c=forecast['value_c']-old['value_c'],previous_decision_sha256=prior['record_sha256'])
        targets.append(dict(target_at=row['at'],offset_from_first_hour=offset,local_issue_age_hours=(at-decision).total_seconds()/3600,
            forecasts=forecasts))
    return _freeze(dict(schema='earthship-refresh-decision/v1',population='actual_publication_decisions_v1',contract_sha256=CONTRACT_SHA256,
        decision_at=decision.isoformat(),publication_completed_at=confirmed.isoformat(),compiled_at=compiled.isoformat(),
        attempt_sha256=published['attempt_sha256'],result_sha256=published['result_sha256'],producer_sha256=_producer(),
        timezone=site.timezone,publication=published,refresh=refresh,near=corrected,
        sampling=dict(near=CONTRACT['near'],long_offsets=list(LONG_OFFSETS),complete_extended_original_retained=True,
            claim='bounded predeclared target sample; not exhaustive all-hour scoring'),targets=targets,
        withheld=dict(elapsed_before_confirmed_publication=elapsed),probability_claim=False,automatic_actuation=False))


def score_refresh_target(record,*,target_at,outcome,observation_policy_sha256,measurement_quality):
    """Use one qualified original observation for all methods on an exact target."""
    from weather_temperature_evidence import sensor_epoch_id
    body=_record(record,'earthship-refresh-decision/v1');at=utc(target_at);policy=digest(observation_policy_sha256)
    row=next((r for r in body['targets'] if instant(r['target_at'])==at),None)
    if row is None:raise ValueError('predeclared original target required')
    if (not isinstance(outcome,TemperatureOutcome) or utc(outcome.target_at)!=at or not finite(outcome.value_c) or
            not at<=utc(outcome.available_at)<=min(utc(outcome.assessed_at),at+timedelta(days=7))):
        raise ValueError('qualified matching original outcome availability required')
    sensor_epoch_id(outcome.sensor_epoch);digest(outcome.receipt_digest)
    if measurement_quality not in ('qualified_receipt_v2','qualified_receipt_v1'):
        raise ValueError('explicit qualified measurement quality required')
    key=identity(dict(attempt=body['attempt_sha256'],result=body['result_sha256'],target=at.isoformat(),
        epoch=outcome.sensor_epoch,policy=policy,quality=measurement_quality,contract=CONTRACT_SHA256,producer=body['producer_sha256']))
    value=dict(schema='earthship-refresh-temperature-score/v1',contract_sha256=CONTRACT_SHA256,evaluation_key=key,
        decision_sha256=body['record_sha256'],attempt_sha256=body['attempt_sha256'],producer_sha256=body['producer_sha256'],
        decision_at=body['decision_at'],publication_completed_at=body['publication_completed_at'],target_at=at.isoformat(),timezone=body['timezone'],
        local_issue_age_hours=row['local_issue_age_hours'],offset_from_first_hour=row['offset_from_first_hour'],
        observation=dict(value_c=outcome.value_c,available_at=utc(outcome.available_at).isoformat(),receipt_sha256=outcome.receipt_digest,
            sensor_epoch=outcome.sensor_epoch,policy_sha256=policy,quality=measurement_quality),
        forecasts=row['forecasts'],prospective_basis='recorded_published_actual_and_known_at_decision_replay_candidates',
        probability_claim=False,automatic_actuation=False)
    value['score_sha256']=identity(value);return validate_refresh_score(value)


def validate_refresh_score(value):
    _checked(value,'score_sha256')
    if (value['schema']!='earthship-refresh-temperature-score/v1' or value['contract_sha256']!=CONTRACT_SHA256
            or value['probability_claim'] is not False or value['automatic_actuation'] is not False
            or set(value['forecasts'])!=set(POLICIES)):raise ValueError('original closed read-only refresh score required')
    observation=value['observation'];at=instant(value['target_at']);decision=instant(value['decision_at'])
    if not decision<=instant(value['publication_completed_at'])<at or not at<=instant(observation['available_at'])<=at+timedelta(days=7):
        raise ValueError('original publication and observation clocks required')
    if not finite(observation['value_c']):raise ValueError('finite qualified original observation required')
    for name,forecast in value['forecasts'].items():
        if forecast['value_c'] is None:
            if forecast['source'] is not None or forecast['reason'] is None:raise ValueError('explicit missing refresh policy required')
            continue
        source=forecast['source']
        if (not finite(forecast['value_c']) or not finite(forecast['raw_c']) or
                not instant(source['initialized_at'])<=instant(source['first_seen_at'])<=instant(source['ingestion_completed_at'])<=decision
                or at>instant(source['initialized_at'])+timedelta(hours=360)
                or forecast['actually_published']!=(name=='actual_serving')):raise ValueError('original known-at-decision forecast required')
        digest(source['grid_sha256']);digest(source['snapshot_sha256'])
        if forecast['local_c'] is not None and (not finite(forecast['local_c']) or forecast['model_sha256'] is None or forecast['value_c']!=forecast['local_c']):
            raise ValueError('source-bound original local correction required')
    return value


def _weights(rows,zone):
    dates=defaultdict(set);counts=Counter(r['target_at'] for r in rows)
    for r in rows:dates[instant(r['target_at']).astimezone(zone).date()].add(r['target_at'])
    return [1/len(dates)/len(dates[instant(r['target_at']).astimezone(zone).date()])/counts[r['target_at']] for r in rows]


def _support(rows,zone):
    return dict(pairs=len(rows),targets=len({r['target_at'] for r in rows}),local_dates=len({instant(r['target_at']).astimezone(zone).date() for r in rows}))


def _metric(rows,policy,zone):
    if not rows:return dict(mae_c=None,rmse_c=None,bias_c=None)
    w=_weights(rows,zone);e=[r['forecasts'][policy]['value_c']-r['observation']['value_c'] for r in rows]
    return dict(mae_c=fsum(a*abs(b) for a,b in zip(w,e)),rmse_c=sqrt(fsum(a*b*b for a,b in zip(w,e))),bias_c=fsum(a*b for a,b in zip(w,e)))


def _paired(rows,left,right,zone):
    return dict(support=_support(rows,zone),left=_metric(rows,left,zone),right=_metric(rows,right,zone))


def _gain(compare):
    a,b=compare['left']['mae_c'],compare['right']['mae_c']
    return None if a is None or b is None or b==0 else 1-a/b


def _subgroups(rows,left,right,zone):
    groups=defaultdict(list)
    for row in rows:
        lead=row['local_issue_age_hours'];hour=instant(row['target_at']).astimezone(zone).hour
        groups['lead:'+('0-6h' if lead<=6 else '6-24h' if lead<=24 else '24-72h' if lead<=72 else '72-168h' if lead<=168 else '168-336h')].append(row)
        groups['local_hour:'+str(hour)].append(row)
    output={}
    for key,values in sorted(groups.items()):
        c=_paired(values,left,right,zone);a,b=c['left']['mae_c'],c['right']['mae_c']
        c['supported']=c['support']['targets']>=CONTRACT['minimum_subgroup_targets']
        c['regression_exceeds_limit']=bool(c['supported'] and a is not None and b is not None and a>b*(1+CONTRACT['maximum_subgroup_regression'])+1e-12)
        output[key]=c
    return output


def _day_blocks(rows,left,right,zone):
    days=defaultdict(list)
    for row in rows:days[instant(row['target_at']).astimezone(zone).date().isoformat()].append(row)
    differences=[_metric(v,left,zone)['mae_c']-_metric(v,right,zone)['mae_c'] for _,v in sorted(days.items())]
    draws=[];rng=Random(CONTRACT['bootstrap_seed'])
    if differences:
        for _ in range(CONTRACT['bootstrap_repetitions']):draws.append(fsum(rng.choice(differences) for _ in differences)/len(differences))
        draws.sort()
    return dict(local_date_blocks=len(days),descriptive_mean_mae_difference_c=None if not differences else fsum(differences)/len(differences),
        descriptive_interval_c=None if not draws else [draws[int(.025*(len(draws)-1))],draws[int(.975*(len(draws)-1))]],
        independence_qualified=False,probability_claim=False)


def summarize_refresh_scores(scores):
    if not isinstance(scores,list) or len(scores)>10000:raise ValueError('bounded original refresh score population required')
    unique={};truth={}
    for raw in scores:
        row=validate_refresh_score(raw);key=row['evaluation_key'];o=row['observation']
        if key in unique:
            if unique[key]!=row:raise ValueError('conflicting original refresh evaluation')
            continue
        target=(row['timezone'],o['sensor_epoch'],o['policy_sha256'],o['quality'],row['target_at'])
        observed=(o['value_c'],o['available_at'],o['receipt_sha256'])
        if target in truth and truth[target]!=observed:raise ValueError('conflicting measured target cannot inflate support')
        truth[target]=observed;unique[key]=row
    rows=list(unique.values());comparisons=[]
    for left,right in PAIRS:
        cohorts=defaultdict(list)
        for row in rows:
            o=row['observation'];a,b=row['forecasts'][left],row['forecasts'][right]
            # Different quality, epochs, grids and fitted artifacts stay separate.
            fallback_source=row['forecasts']['actual_serving']['source']
            grids=tuple((p['source'] or fallback_source)['grid_sha256'] for p in (a,b))
            descriptor=dict(sensor_epoch=o['sensor_epoch'],observation_policy_sha256=o['policy_sha256'],measurement_quality=o['quality'],
                timezone=row['timezone'],native_grids=grids,producer_sha256=row['producer_sha256'],
                left_model_sha256=a['model_sha256'],right_model_sha256=b['model_sha256'])
            pin=identity(descriptor);cohorts[pin].append((row,descriptor))
        for pin,values in sorted(cohorts.items()):
            group=[r for r,_ in values];descriptor=values[0][1];zone=ZoneInfo(descriptor['timezone'])
            matched=[r for r in group if r['forecasts'][left]['value_c'] is not None and r['forecasts'][right]['value_c'] is not None
                and r['forecasts'][left]['source']['grid_sha256']==r['forecasts'][right]['source']['grid_sha256']]
            corrected=[r for r in matched if r['forecasts'][left]['local_c'] is not None]
            candidate_rows=corrected if left==PROFILE else matched
            paired=_paired(candidate_rows,left,right,zone);fallback=_paired(matched,left,right,zone)
            subgroups=_subgroups(candidate_rows,left,right,zone);fallback_subgroups=_subgroups(matched,left,right,zone)
            support=paired['support'];gain=_gain(paired)
            enough=support['targets']>=CONTRACT['minimum_targets'] and support['local_dates']>=CONTRACT['minimum_local_dates']
            regressions=[k for k,v in subgroups.items() if v['regression_exceeds_limit']]
            regressions+=['fallback:'+k for k,v in fallback_subgroups.items() if v['regression_exceeds_limit']] if left==PROFILE else []
            fallback_gain=_gain(fallback)
            passed=bool(enough and gain is not None and gain>=CONTRACT['minimum_gain'] and not regressions
                and (left!=PROFILE or fallback_gain is not None and fallback_gain>=CONTRACT['minimum_gain']))
            comparisons.append(dict(comparison=left+'_vs_'+right,cohort_sha256=pin,cohort=descriptor,matched=paired,
                fallback_inclusive=fallback,corrected_only=_paired(corrected,left,right,zone),
                coverage=dict(qualified=len(group),matched=len(matched),corrected=len(corrected),fallback=len(matched)-len(corrected) if left==PROFILE else 0,
                    left_unavailable=sum(r['forecasts'][left]['value_c'] is None for r in group),right_unavailable=sum(r['forecasts'][right]['value_c'] is None for r in group),
                    grid_mismatch=sum(r['forecasts'][left]['source'] is not None and r['forecasts'][right]['source'] is not None and r['forecasts'][left]['source']['grid_sha256']!=r['forecasts'][right]['source']['grid_sha256'] for r in group)),
                relative_mae_gain=gain,fallback_relative_mae_gain=fallback_gain,by_subgroup=subgroups,fallback_by_subgroup=fallback_subgroups,
                fallback_reasons=dict(Counter(r['forecasts'][left]['reason'] for r in matched if left==PROFILE and r['forecasts'][left]['local_c'] is None)),
                supported_regressions=regressions,paired_local_date_blocks=_day_blocks(candidate_rows,left,right,zone),fallback_local_date_blocks=_day_blocks(matched,left,right,zone),
                candidate_meets_score_gate=passed,disposition='insufficient_evidence' if not enough else 'retain_incumbent_pending_review' if passed else 'retain_incumbent',
                revision=dict(left_mean_absolute_c=None if not (rev:=[abs(r['forecasts'][left]['revision_c']) for r in matched if r['forecasts'][left]['revision_c'] is not None]) else fsum(rev)/len(rev),
                    left_same_target_pairs=len(rev)),release_authorized=False))
    value=dict(schema='earthship-refresh-comparison/v1',contract_sha256=CONTRACT_SHA256,unique_scores=len(rows),
        comparisons=comparisons,population='retained_actual_publication_targets_and_known_at_decision_policy_replays',
        forecast_basis='only actual_serving is an original published forecast; comparative policies are explicitly replayed',
        benchmark='first_original_per_local_day_unchanged',probability_claim=False,automatic_actuation=False,release_authorized=False)
    value['report_sha256']=identity(value);return value
