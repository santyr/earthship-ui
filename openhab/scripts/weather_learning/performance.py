"""Versioned matched scores from immutable issued predictions, never refitting.

Legacy issues lack a retained method/training/selection policy declaration. They
remain useful original-prediction diagnostics, explicitly unidentified, and may
never be presented as qualification of today's model or training procedure.
"""
from datetime import timedelta
from math import fsum,sqrt
from zoneinfo import ZoneInfo

from .contracts import digest,finite,identity,instant
from .features import training_pair
from .publish import validate_payload

EVALUATION_VERSION='earthship-weather-evaluation/v2'
EVALUATION_CONTRACT=dict(schema=EVALUATION_VERSION,
    population='first_original_per_local_issue_date_predeclared_sparse_native_hours',
    observation_arrival_allowance_days=7,report_target_window_days=7,
    scoring_unit='equal_local_target_dates_equal_observed_targets_equal_issued_origins',
    comparison='identical_issue_target_grid_observation_population',
    policy='original_issued_shadow_correction_else_original_raw',
    attribution='separate_policy_and_fitted_artifact',missing='withheld_never_zero',
    authority='diagnostic_no_release_or_actuation')
EVALUATION_CONTRACT_SHA256=identity(EVALUATION_CONTRACT)
SCORE_SCHEMA='earthship-weather-temperature-score/v2'
FIELDS={'schema','evaluation_version','evaluation_contract_sha256','evaluation_key','issue_sha256','issue_generation',
    'snapshot_sha256','grid_sha256','source_run_id','provider','variable','period_seconds','timezone',
    'issued_at','target_at','outcome_sha256','outcome_available_at','sensor_epoch','observation_policy_sha256',
    'numerical_producer','method','training_policy_sha256','selection_policy_sha256','provenance_status',
    'model_sha256','raw_c','issued_local_c','policy_c','observed_c','score_sha256'}


def temperature_evaluation_key(*,issue_sha256,target_at,source_grid,sensor_epoch,
        observation_policy_sha256,evaluation_version=EVALUATION_VERSION,
        evaluation_contract_sha256=EVALUATION_CONTRACT_SHA256):
    return identity(dict(evaluation_version=evaluation_version,evaluation_contract_sha256=evaluation_contract_sha256,
        issue_sha256=issue_sha256,target_at=instant(target_at).isoformat(),source_grid=source_grid,
        sensor_epoch=sensor_epoch,observation_policy_sha256=observation_policy_sha256))


def score_temperature(*,original,target,row,outcome,observation_policy_sha256):
    pair=training_pair(target,outcome);payload=validate_payload(original['payload'])
    if (original['sensor_epoch']!=outcome.sensor_epoch or payload['generation'] is None or
        payload['source']['snapshotSha256']!=target.snapshot_digest or
        instant(payload['decisionAt'])!=target.issued_at or row not in payload['hours'] or
        instant(row['at'])!=target.target_at or abs(row['rawC']-target.mean_c)>1e-9):
        raise ValueError('exact original issue/target/outcome binding required')
    provenance=original.get('provenance')
    if provenance is None:
        provenance=dict(method='legacy_unidentified',training_policy_sha256=None,selection_policy_sha256=None)
        status='original_prediction_retained_method_policy_unidentified'
    else:
        from .provenance import validate_provenance
        validate_provenance(provenance)
        status=('original_prediction_and_policy_retained' if provenance['status']=='complete' else
            'original_prediction_and_selection_retained_training_policy_unidentified')
    issue=identity(original)
    value=dict(schema=SCORE_SCHEMA,evaluation_version=EVALUATION_VERSION,evaluation_contract_sha256=EVALUATION_CONTRACT_SHA256,
        evaluation_key=temperature_evaluation_key(issue_sha256=issue,target_at=row['at'],source_grid=target.grid_digest,
            sensor_epoch=outcome.sensor_epoch,observation_policy_sha256=observation_policy_sha256),
        issue_sha256=issue,issue_generation=payload['generation'],snapshot_sha256=target.snapshot_digest,
        grid_sha256=target.grid_digest,source_run_id=payload['source']['runId'],provider=target.provider,
        variable='station_head_temperature_2m',period_seconds=0,timezone=target.site_timezone,
        issued_at=target.issued_at.isoformat(),target_at=target.target_at.isoformat(),
        outcome_sha256=outcome.receipt_digest,outcome_available_at=outcome.available_at.isoformat(),
        sensor_epoch=outcome.sensor_epoch,observation_policy_sha256=observation_policy_sha256,
        numerical_producer=original['code_revision'],method=provenance['method'],
        training_policy_sha256=provenance['training_policy_sha256'],selection_policy_sha256=provenance['selection_policy_sha256'],
        provenance_status=status,model_sha256=payload['model']['sha256'],raw_c=target.mean_c,
        issued_local_c=row['localC'],policy_c=target.mean_c if row['localC'] is None else row['localC'],observed_c=outcome.value_c)
    value['score_sha256']=identity(value)
    return validate_temperature_score(value)


def validate_temperature_score(value):
    import re
    from weather_temperature_evidence import sensor_epoch_id
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCORE_SCHEMA or
        value['evaluation_version']!=EVALUATION_VERSION or value['evaluation_contract_sha256']!=EVALUATION_CONTRACT_SHA256 or
        value['score_sha256']!=identity({k:v for k,v in value.items() if k!='score_sha256'})):
        raise ValueError('closed immutable versioned temperature score required')
    for name in ('issue_sha256','issue_generation','snapshot_sha256','grid_sha256','outcome_sha256','observation_policy_sha256'):
        digest(value[name])
    for name in ('model_sha256','training_policy_sha256','selection_policy_sha256'):
        if value[name] is not None:digest(value[name])
    if (value['provider']!='weathernext3' or value['variable']!='station_head_temperature_2m' or value['period_seconds']!=0 or
        not isinstance(value['source_run_id'],str) or not 1<=len(value['source_run_id'])<=128 or
        not isinstance(value['method'],str) or not 1<=len(value['method'])<=128 or
        not re.fullmatch('[0-9a-f]{40}',value['numerical_producer'])):
        raise ValueError('original source/product/numerical identity required')
    sensor_epoch_id(value['sensor_epoch']);ZoneInfo(value['timezone'])
    issued,target,available=map(instant,(value['issued_at'],value['target_at'],value['outcome_available_at']))
    if not issued<target<=issued+timedelta(hours=360) or not target<=available<=target+timedelta(days=7):
        raise ValueError('original issue/outcome clocks and arrival allowance required')
    if (any(not finite(value[k]) for k in ('raw_c','policy_c','observed_c')) or
        value['issued_local_c'] is not None and (not finite(value['issued_local_c']) or value['model_sha256'] is None) or
        value['policy_c']!=(value['raw_c'] if value['issued_local_c'] is None else value['issued_local_c'])):
        raise ValueError('finite original correction or explicit raw fallback required')
    retained=value['provenance_status']=='original_prediction_and_policy_retained'
    partial=value['provenance_status']=='original_prediction_and_selection_retained_training_policy_unidentified'
    legacy=value['provenance_status']=='original_prediction_retained_method_policy_unidentified'
    if not (retained and all(value[k] is not None for k in ('training_policy_sha256','selection_policy_sha256')) or
        partial and value['method']!='legacy_unidentified' and value['selection_policy_sha256'] is not None and value['training_policy_sha256'] is None or
        legacy and value['method']=='legacy_unidentified' and all(value[k] is None for k in ('training_policy_sha256','selection_policy_sha256'))):
        raise ValueError('explicit retained or unidentified policy provenance required')
    expected=temperature_evaluation_key(issue_sha256=value['issue_sha256'],target_at=value['target_at'],source_grid=value['grid_sha256'],
        sensor_epoch=value['sensor_epoch'],observation_policy_sha256=value['observation_policy_sha256'])
    if value['evaluation_key']!=expected:raise ValueError('temperature evaluation identity differs')
    return value


def _target(row):return row['sensor_epoch'],row['target_at'],row['outcome_sha256']


def _metrics(rows,prediction):
    if not rows:return None
    dates={}
    for row in rows:
        day=instant(row['target_at']).astimezone(ZoneInfo(row['timezone'])).date().isoformat()
        dates.setdefault(day,{}).setdefault(_target(row),[]).append(row[prediction]-row['observed_c'])
    weighted=[]
    for targets in dates.values():
        for errors in targets.values():
            weight=1/len(dates)/len(targets)/len(errors)
            weighted.extend((error,weight) for error in errors)
    tail=sorted((abs(error),weight) for error,weight in weighted);total=0.;p95=tail[-1][0]
    for error,weight in tail:
        total+=weight
        if total>=.95-1e-12:p95=error;break
    return dict(pairs=len(rows),unique_measured_targets=len({_target(r) for r in rows}),target_dates=len(dates),
        mae_c=fsum(abs(e)*w for e,w in weighted),rmse_c=sqrt(fsum(e*e*w for e,w in weighted)),
        bias_c=fsum(e*w for e,w in weighted),weighted_absolute_error_p95_c=p95)


def _comparison(rows):
    corrected=[r for r in rows if r['issued_local_c'] is not None]
    raw=_metrics(rows,'raw_c');candidate=_metrics(corrected,'issued_local_c');paired=_metrics(corrected,'raw_c');policy=_metrics(rows,'policy_c')
    def gain(a,b):return None if a is None or b is None or b['mae_c']==0 else 1-a['mae_c']/b['mae_c']
    return dict(raw=raw,candidate=candidate,candidate_paired_raw=paired,policy=policy,
        candidate_relative_mae_gain=gain(candidate,paired),policy_relative_mae_gain=gain(policy,raw),
        coverage=dict(qualified=len(rows),corrected=len(corrected),fallback=len(rows)-len(corrected)))


def summarize_temperature_scores(records,*,withheld=0):
    if type(withheld) is not int or withheld<0:raise ValueError('explicit nonnegative withheld count required')
    unique={};observations={}
    for raw in records:
        row=validate_temperature_score(raw);key=row['evaluation_key']
        if key in unique and unique[key]!=row:raise ValueError('conflicting immutable evaluation result')
        if len(unique)>=20000 and key not in unique:raise ValueError('bounded temperature score report required')
        target=(row['sensor_epoch'],row['observation_policy_sha256'],row['target_at'])
        prior=observations.setdefault(target,(row['outcome_sha256'],row['observed_c']))
        if prior!=(row['outcome_sha256'],row['observed_c']):raise ValueError('conflicting shared measured target')
        unique[key]=row
    rows=sorted(unique.values(),key=lambda r:(r['target_at'],r['issued_at'],r['evaluation_key']))
    horizons={};seasons={};artifacts={};policies={}
    cohort_fields=('provider','variable','period_seconds','timezone','grid_sha256','sensor_epoch','observation_policy_sha256',
        'numerical_producer','method','training_policy_sha256','selection_policy_sha256','provenance_status')
    for row in rows:
        hours=(instant(row['target_at'])-instant(row['issued_at'])).total_seconds()/3600
        horizon=next(label for end,label in ((24,'0-24h'),(72,'24-72h'),(168,'72-168h'),(360,'168-360h')) if hours<=end)
        horizons.setdefault(horizon,[]).append(row)
        month=instant(row['target_at']).astimezone(ZoneInfo(row['timezone'])).strftime('%Y-%m');seasons.setdefault(month,[]).append(row)
        cohort={k:row[k] for k in cohort_fields}
        for group,description in ((policies,cohort),(artifacts,cohort|dict(model_sha256=row['model_sha256']))):
            item=group.setdefault(identity(description),dict(cohort=description,rows=[]));item['rows'].append(row)
    def groups(values):return {key:dict(cohort=value['cohort'],comparison=_comparison(value['rows']),
        model_sha256s=sorted({r['model_sha256'] for r in value['rows'] if r['model_sha256'] is not None})) for key,value in sorted(values.items())}
    return dict(**_comparison(rows),withheld=withheld,evaluation_version=EVALUATION_VERSION,
        evaluation_contract_sha256=EVALUATION_CONTRACT_SHA256,
        evaluation_scope='versioned_sampled_forecasting_policy_and_separate_artifact_diagnostics',
        scoring_unit=EVALUATION_CONTRACT['scoring_unit'],aggregate_role='cross_cohort_diagnostic_never_current_artifact_qualification',
        by_horizon={key:_comparison(value) for key,value in sorted(horizons.items())},
        by_local_target_month={key:_comparison(value) for key,value in sorted(seasons.items())},
        policy_cohorts=groups(policies),artifact_cohorts=groups(artifacts),
        pair_manifest=[{k:r[k] for k in ('evaluation_key','score_sha256','issue_sha256','issued_at','target_at','outcome_sha256','model_sha256')} for r in rows],
        score_record_scope='private_immutable_records_referenced_by_evaluation_key_and_score_sha256',calibration_qualified=False,release_authorized=False,automatic_actuation=False)
