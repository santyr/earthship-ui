"""Pure comparisons of original emitted metrics; unavailable policy rows remain."""
from collections import defaultdict
from dataclasses import asdict
from datetime import timedelta
from .contracts import canonical,digest,identity,instant,finite
from .probabilistic import ForecastInput,CalibrationPair,_policy,_support
from .probabilistic_evaluation import _comparison


def _rows(records):
    seen=set();result=[]
    for value in records:
        if (not isinstance(value,dict) or value.get('score_sha256')!=identity({k:v for k,v in value.items() if k!='score_sha256'}) or
                value.get('schema')!='earthship-original-emitted-marginal-score/v1' or value.get('issued') is not True or
                any(value.get(n) is not False for n in ('local_coverage_qualified','probability_claim','automatic_actuation'))):raise ValueError('unchanged original issued marginal score required')
        for field in ('model_set_sha256','scoring_producer_sha256','emission_sha256'):digest(value[field])
        if value['model_set_sha256']!=identity(value['configured_bundle_sha256s']):raise ValueError('original configured model set differs')
        if value['score_sha256'] in seen:raise ValueError('duplicate original marginal score record')
        seen.add(value['score_sha256']);args=dict(value['forecast']);args.pop('input_sha256');f=ForecastInput(**args);o=value['observation'];digest(o['observation_policy_sha256'])
        if (asdict(f)!=value['forecast'] or f.availability_basis!='recorded_ingestion_availability' or
                not instant(f.origin)<=instant(value['emitted_at'])<instant(f.target_end) or
                f.kind!='temperature' and instant(value['emitted_at'])>instant(f.target_start) or
                not instant(f.target_end)<=instant(o['available_at'])<=instant(f.target_end)+timedelta(days=7) or
                not finite(o['value'])):raise ValueError('original prospective forecast and timely observation required')
        pair=CalibrationPair(forecast=f,value=o['value'],outcome_ready_at=o['available_at'],actual_outcome_available_at=o['available_at'],receipt_sha256=o['observation_sha256'])
        result.append(dict(record=value,pair=pair))
    return result


def _comparisons(rows,policy,guard):
    kind=rows[0]['pair'].forecast.kind
    definitions=[('temperature_normal_vs_raw','temperature_normal','raw','interval_score_80'),('temperature_normal_vs_empirical','temperature_normal','empirical','interval_score_80'),('empirical_vs_raw','empirical','raw','interval_score_80'),('adaptive_vs_raw_point','adaptive','raw','mae')] if kind=='temperature' else [('nonnegative_vs_empirical','nonnegative','empirical','interval_score_80'),('nonnegative_point_vs_raw','nonnegative','raw','mae'),('empirical_point_vs_raw','empirical','raw','mae')]
    if kind=='temperature':definitions += [('empirical_median_point_vs_raw_mean','empirical','raw','mae'),('temperature_normal_mean_point_vs_raw_mean','temperature_normal','raw','mae')]
    result={}
    for name,candidate,baseline,primary in definitions:
        guard();scored=[]
        for entry in rows:
            v=entry['record'];base=v['raw'] if baseline=='raw' else v['local'].get(baseline);local=v['adaptive'] if candidate=='adaptive' else v['local'].get(candidate)
            base_ok=base is not None and (primary=='mae' or base.get('interval_score_80') is not None);both=base_ok and local is not None
            reason=(v['fallback_reason'] or 'candidate_unavailable') if local is None else 'baseline_unavailable' if not base_ok else None
            scored.append(dict(pair=entry['pair'],baseline=base if base_ok else v['raw'],candidate=local if both else base if base_ok else v['raw'],both=both,reason=reason))
        result[name]=_comparison(scored,primary=primary,policy=policy)
        if name in {'empirical_median_point_vs_raw_mean','temperature_normal_mean_point_vs_raw_mean','nonnegative_point_vs_raw','empirical_point_vs_raw'}:
            result[name].update(diagnostic_only=True,candidate_meets_score_gate=False,probability_review_support_only=False)
        # Preserve explicit absent groups without duplicating unavailable bodies.
        for groups in result[name]['by_subgroup'].values():
            for label,value in list(groups.items()):
                if not value['support']['pairs']:groups[label]=dict(support=value['support'],metrics_available=False)
    return result


def summarize_scores(records,*,policy,guard=lambda:None):
    policy=_policy(policy)
    if not isinstance(records,list) or len(records)>10000:raise ValueError('bounded original marginal score window required')
    rows=_rows(records);groups=defaultdict(list)
    for entry in rows:
        v=entry['record'];groups[(v['model_set_sha256'],entry['pair'].forecast.kind,v['observation']['observation_policy_sha256'],v['scoring_producer_sha256'])].append(entry)
    model_sets=[]
    for key,entries in sorted(groups.items()):
        guard();cohorts=defaultdict(list)
        for entry in entries:
            f=entry['pair'].forecast;o=entry['record']['observation'];cohorts[(f.cohort_sha256,f.grid_sha256,identity(o['quality']))].append(entry)
        detail=[]
        for (cohort,grid,quality),subset in sorted(cohorts.items()):
            detail.append(dict(forecast_cohort_sha256=cohort,grid_sha256=grid,observation_quality_sha256=quality,support=_support([e['pair'] for e in subset]),comparisons=_comparisons(subset,policy,guard)))
        model_sets.append(dict(model_set_sha256=key[0],kind=key[1],unit={'temperature':'degC','wind':'m_s','solar_proxy':'W_m2_reported_proxy'}[key[1]],observation_policy_sha256=key[2],scoring_producer_sha256=key[3],configured_bundle_sha256s=entries[0]['record']['configured_bundle_sha256s'],support=_support([e['pair'] for e in entries]),comparisons=_comparisons(entries,policy,guard),measurement_cohorts=detail))
    body=dict(schema='earthship-as-issued-marginal-comparisons/v1',records=len(records),model_sets=model_sets,population='confirmed_original_read_only_shadow_emissions_not_core_forecast_skill',weights='equal_local_target_dates_then_targets_then_original_forecast_origins_and_versions',unavailable_candidates='included_as_original_baseline_fallback_in_policy_comparisons',native_median_inferred=False,local_coverage_qualified=False,probability_claim=False,automatic_actuation=False)
    if len(canonical(body))>16*1024**2:raise ValueError('bounded complete marginal report exceeded')
    body['summary_sha256']=identity(body);return body
