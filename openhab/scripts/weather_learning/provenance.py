"""Closed as-issued procedure declarations, independent of fitted artifact IDs.

An old model retains its known numerical recipe. Its unretained training-window
policy stays unknown; current configuration never fills that historical gap.
"""
from hashlib import sha256
from pathlib import Path
from .contracts import canonical,digest,finite,identity

SCHEMA='earthship-weather-issue-provenance/v1'
METHOD_FIELDS={'schema','family','algorithm','artifact_schema','feature_names','ridge','maximum_correction','weighting_rule','numerical_sources'}
TRAIN_FIELDS={'schema','family','history_days','algorithm','cutoff_rule','sampling_rule','native_hour_offsets','weighting_rule','ridge','maximum_correction','numerical_sources'}
SELECT_FIELDS={'schema','family','rule','maximum_model_age_days','requirements','fallback'}
FIELDS={'schema','status','method','method_policy','method_policy_sha256','training_policy','training_policy_sha256','selection_policy','selection_policy_sha256','selection_original_sha256'}


def _text(value,limit=128):
    if not isinstance(value,str) or not 1<=len(value)<=limit:raise ValueError('bounded procedure declaration required')


def _strings(values):
    if not isinstance(values,list) or len(values)>32 or len(set(values))!=len(values):raise ValueError('bounded unique procedure fields required')
    for value in values:_text(value)


def _source_map(sources,*,empty=False):
    if not isinstance(sources,dict) or not (0 if empty else 1)<=len(sources)<=8:raise ValueError('numerical source identity required')
    for name,value_hash in sources.items():
        if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.py'):raise ValueError('closed numerical source filename required')
        digest(value_hash)


def validate_training_policy(value):
    if not isinstance(value,dict) or set(value)!=TRAIN_FIELDS or value['schema']!='earthship-weather-training-policy/v1':raise ValueError('closed training policy required')
    if value['family'] not in ('native_daily_shadow','not_applicable'):raise ValueError('known retained training family required')
    if type(value['history_days']) is not int or not 0<=value['history_days']<=366:raise ValueError('actual bounded training history required')
    for key in ('algorithm','cutoff_rule','sampling_rule','weighting_rule'):_text(value[key])
    offsets=value['native_hour_offsets']
    if not isinstance(offsets,list) or len(offsets)>40 or any(type(v) is not int or not 1<=v<=360 for v in offsets) or offsets!=sorted(set(offsets)):raise ValueError('explicit sparse native training population required')
    if not finite(value['ridge']) or value['ridge']<0 or not finite(value['maximum_correction']) or not 0<=value['maximum_correction']<=20:raise ValueError('finite fixed recipe parameters required')
    _source_map(value['numerical_sources'],empty=value['family']=='not_applicable')
    if value['family']=='not_applicable' and (value['history_days'] or offsets or value['algorithm']!='none'):raise ValueError('raw forecast has no fitted training policy')
    if value['family']=='native_daily_shadow' and (not value['history_days'] or not offsets or value['algorithm'] not in ('bounded_bias','ridge_residual')):raise ValueError('actual native training request required')
    return value


def validate_provenance(value):
    if not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=SCHEMA or value['status'] not in ('complete','training_policy_unretained'):raise ValueError('closed original procedure provenance required')
    method=value['method_policy'];selection=value['selection_policy']
    if not isinstance(method,dict) or set(method)!=METHOD_FIELDS or method['schema']!='earthship-weather-method-policy/v1' or method['family'] not in ('original_raw','native_temperature','historical_outdoor'):raise ValueError('closed numerical method policy required')
    for key in ('algorithm','artifact_schema','weighting_rule'):_text(method[key])
    _strings(method['feature_names'])
    if not finite(method['ridge']) or method['ridge']<0 or not finite(method['maximum_correction']) or not 0<=method['maximum_correction']<=20:raise ValueError('finite numerical recipe required')
    sources=method['numerical_sources']
    _source_map(sources)
    if not isinstance(selection,dict) or set(selection)!=SELECT_FIELDS or selection['schema']!='earthship-weather-selection-policy/v1' or selection['family'] not in ('original_raw','native_current_pointer','historical_explicit_selection'):raise ValueError('closed selection strategy required')
    for key in ('rule','fallback'):_text(selection[key])
    _strings(selection['requirements'])
    age=selection['maximum_model_age_days']
    if age is not None and (type(age) is not int or not 1<=age<=366):raise ValueError('bounded actual selection expiry required')
    for name in ('method_policy','selection_policy'):
        if digest(value[name+'_sha256'])!=identity(value[name]):raise ValueError('procedure declaration digest differs')
    _text(value['method'])
    if value['method']!=method['algorithm']+'@'+value['method_policy_sha256']:raise ValueError('method identity differs from recipe')
    if value['selection_original_sha256'] is not None:digest(value['selection_original_sha256'])
    if value['status']=='complete':
        validate_training_policy(value['training_policy'])
        if digest(value['training_policy_sha256'])!=identity(value['training_policy']):raise ValueError('training policy digest differs')
    elif value['training_policy'] is not None or value['training_policy_sha256'] is not None:raise ValueError('unretained training policy must remain explicitly unknown')
    if value['training_policy'] is not None:
        policy=value['training_policy']
        if (policy['algorithm'],policy['ridge'],policy['maximum_correction'],policy['weighting_rule'])!=(method['algorithm'],method['ridge'],method['maximum_correction'],method['weighting_rule']):raise ValueError('training policy differs from numerical recipe')
    if len(canonical(value))>16384:raise ValueError('bounded original procedure metadata required')
    return value


def numerical_sources(names):
    return {name:sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in names}


def method_policy(model=None,*,historical=False):
    if model is None:
        return dict(schema='earthship-weather-method-policy/v1',family='original_raw',algorithm='none',artifact_schema='native_weathernext_station_temperature',feature_names=[],ridge=0,maximum_correction=0,weighting_rule='not_applicable',numerical_sources=numerical_sources(('features.py','contracts.py')))
    return dict(schema='earthship-weather-method-policy/v1',family='historical_outdoor' if historical else 'native_temperature',
        algorithm=model['rule'] if historical else model['algorithm'],artifact_schema=model['schema'],feature_names=model['feature_names'],
        ridge=model['ridge'],maximum_correction=model['correction_limit' if historical else 'max_correction_c'],
        weighting_rule=model.get('support',{}).get('weighting_rule','uniform_forecast_pairs_v1'),
        numerical_sources=numerical_sources(('site_calibration.py','historical_pairs.py','historical_serving.py','contracts.py','weights.py') if historical else ('training.py','features.py','contracts.py','weights.py')))


def native_training_policy(model,*,days,offsets):
    return validate_training_policy(dict(schema='earthship-weather-training-policy/v1',family='native_daily_shadow',history_days=days,
        algorithm=model['algorithm'],cutoff_rule='qualified_outcomes_and_original_issues_available_as_of_cutoff',
        sampling_rule='first_original_per_local_issue_date_sparse_native_hours',native_hour_offsets=sorted(offsets),
        weighting_rule=model.get('support',{}).get('weighting_rule','uniform_forecast_pairs_v1'),ridge=model['ridge'],maximum_correction=model['max_correction_c'],
        numerical_sources=numerical_sources(('training.py','features.py','contracts.py','weights.py'))))


def selection_policy(family):
    historical=family=='historical_explicit_selection'
    requirements=(['unchanged_original_experiment_and_model','improved_original_holdout','sensor_epoch_matches','bounded_correction_six_c','frozen_feature_contract','original_training_runtime_matches','available_before_issue'] if historical else
        ['immutable_model_receipt','fitted_before_issue','native_grid_and_sensor_epoch_match'] if family=='native_current_pointer' else ['eligible_original_weathernext_source'])
    return dict(schema='earthship-weather-selection-policy/v1',family=family,
        rule='explicit_selected_historical_candidate' if historical else 'explicit_current_model_pointer' if family=='native_current_pointer' else 'original_raw_when_no_usable_model',
        maximum_model_age_days=14 if historical else None,requirements=requirements,fallback='original_raw_when_unavailable')


def issue_provenance(model=None,*,training_policy=None,historical=False,selection_original_sha256=None):
    method=method_policy(model,historical=historical)
    if model is None:
        training_policy=dict(schema='earthship-weather-training-policy/v1',family='not_applicable',history_days=0,algorithm='none',cutoff_rule='not_applicable',sampling_rule='none',native_hour_offsets=[],weighting_rule='not_applicable',ridge=0,maximum_correction=0,numerical_sources={})
    selection=selection_policy('original_raw' if model is None else 'historical_explicit_selection' if historical else 'native_current_pointer')
    method_hash=identity(method)
    return validate_provenance(dict(schema=SCHEMA,status='complete' if training_policy is not None else 'training_policy_unretained',
        method=method['algorithm']+'@'+method_hash,method_policy=method,method_policy_sha256=method_hash,
        training_policy=training_policy,training_policy_sha256=None if training_policy is None else identity(training_policy),
        selection_policy=selection,selection_policy_sha256=identity(selection),selection_original_sha256=selection_original_sha256))


def validate_issue_provenance(value,payload):
    validate_provenance(value)
    raw=value['method_policy']['family']=='original_raw'
    if raw!=(payload['model']['status']!='SHADOW_ONLY') or raw and any(row['localC'] is not None for row in payload['hours']):raise ValueError('procedure differs from original model selection')
    return value


def validate_model_training_policy(model,policy):
    validate_training_policy(policy)
    if (policy['algorithm'],policy['ridge'],policy['maximum_correction'],policy['weighting_rule'])!=(model['algorithm'],model['ridge'],model['max_correction_c'],model.get('support',{}).get('weighting_rule','uniform_forecast_pairs_v1')):raise ValueError('training declaration differs from actual recipe')
    return policy
