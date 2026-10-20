"""Matched correction diagnostics; unidentified old procedures stay unidentified."""
from collections import defaultdict
from math import fsum
from zoneinfo import ZoneInfo
from .contracts import identity,instant,digest
from .weights import metrics as weighted_metrics

PROCEDURE_FIELDS={'schema','method_policy_sha256','training_policy_sha256','selection_policy_sha256','source_grid_sha256'}


def procedure(original):
    value=original['evidence'].get('procedure')
    if value is None:return dict.fromkeys(PROCEDURE_FIELDS-{'schema'})|{'schema':'earthship-correction-procedure/v1'}
    if not isinstance(value,dict) or set(value)!=PROCEDURE_FIELDS or value['schema']!='earthship-correction-procedure/v1':raise ValueError('closed original correction procedure required')
    for key in PROCEDURE_FIELDS-{'schema'}:
        if value[key] is not None:digest(value[key])
    return value


def _target(row):return (row['kind'],row['start'],row['end'],row['observation_policy_sha256'])


def summarize(rows):
    def weights_for(values):
        targets=defaultdict(list)
        for row in values:targets[_target(row)].append(row)
        dates=defaultdict(set)
        for key,group in targets.items():
            if len({r['outcome']['value'] for r in group})!=1:raise ValueError('conflicting correction observations for one target')
            dates[instant(group[0]['start']).astimezone(ZoneInfo(group[0]['timezone'])).date()].add(key)
        weights={}
        for keys in dates.values():
            for key in keys:
                for row in targets[key]:weights[row['evaluation_key']]=1/(len(dates)*len(keys)*len(targets[key]))
        return weights,len(targets),len(dates)
    _,target_count,date_count=weights_for(rows)
    paired=[r for r in rows if r['candidate'] is not None]
    def metric(values,mode):
        weights,_,_=weights_for(values)
        errors=[(r['raw'] if mode=='raw' or r['candidate'] is None else r['candidate'])-r['outcome']['value'] for r in values]
        mass=[weights[r['evaluation_key']] for r in values];result=weighted_metrics(errors,mass)
        threshold=.95*fsum(mass);accumulated=0.;tail=None
        for error,weight in sorted(zip(map(abs,errors),mass)):
            accumulated+=weight
            if accumulated>=threshold:tail=error;break
        return result|dict(weighted_absolute_error_p95=tail)
    raw_all=metric(rows,'raw');raw=metric(paired,'raw');candidate=metric(paired,'candidate');policy=metric(rows,'candidate')
    gain=lambda a,b:None if not a['mae'] else 1-b['mae']/a['mae']
    return dict(issued_pairs=len(rows),unique_targets=target_count,local_target_dates=date_count,
        raw_all=raw_all,raw=raw,candidate=candidate,policy=policy,fallback_pairs=len(rows)-len(paired),
        candidate_relative_mae_gain=gain(raw,candidate),policy_relative_mae_gain=gain(raw_all,policy),
        weighting='equal_local_target_dates_equal_targets_equal_original_forecasts')


def _lead(row):
    hours=(instant(row['end'])-instant(row['issued_at'])).total_seconds()/3600
    for limit,label in ((24,'0-24h'),(72,'24-72h'),(168,'72-168h'),(240,'168-240h'),(360,'240-360h')):
        if hours<=limit:return label
    raise ValueError('bounded original correction lead required')


def policy_reports(scores):
    cohorts=defaultdict(list)
    for row in scores:
        p=row['procedure'];key=(row['kind'],row['producer_sha256'],row['timezone'],row['observation_policy_sha256'],
            p['source_grid_sha256'],p['method_policy_sha256'],p['training_policy_sha256'],p['selection_policy_sha256'])
        cohorts[key].append(row)
    result=[]
    for key,rows in sorted(cohorts.items(),key=lambda pair:str(pair[0])):
        groups={}
        for name,select in (('by_horizon',_lead),('by_local_target_month',lambda r:instant(r['start']).astimezone(ZoneInfo(r['timezone'])).strftime('%Y-%m')),('by_regime',lambda r:r['regime'])):
            grouped=defaultdict(list)
            for row in rows:grouped[select(row)].append(row)
            groups[name]={label:summarize(values) for label,values in sorted(grouped.items())}
        status='complete' if all(value is not None for value in key[4:]) else 'method_training_selection_policy_unidentified' if all(value is None for value in key[4:]) else 'partial_original_procedure_training_or_grid_unidentified'
        result.append(dict(kind=key[0],producer_sha256=key[1],timezone=key[2],observation_policy_sha256=key[3],
            source_grid_sha256=key[4],method_policy_sha256=key[5],training_policy_sha256=key[6],selection_policy_sha256=key[7],
            provenance_status=status,scope='separate_procedure_diagnostic_never_newest_artifact_qualification',
            metrics=summarize(rows),**groups,calibration_qualified=False))
    return result
