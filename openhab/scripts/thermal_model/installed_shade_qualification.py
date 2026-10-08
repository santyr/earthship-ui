"""Source-replayed installed-domain qualification; cached reports grant no authority.

The existing statistical thresholds remain unchanged. Uncalibrated observations
remain visible for diagnostics but cannot pass a production release decision.
"""
from copy import deepcopy
from pathlib import Path

from .forcing_capture import _canonical
from .graduation_policy import _utc, validate_policy
from .graduation_decision import FORECAST_GATES as BASE_GATES, qualification_deadline
from .graduation_statistics import assess_current_predictive_skill as assess_predictive_skill
from .graduation_statistics import _sample, _metrics
from .installed_shade_artifact import read_candidate_bundle, _digest, SCHEMA as CANDIDATE_SCHEMA
from .installed_shade_origin import read_issued_capture, score_issued_capture
from .policy_registration import read_installed_shade_registered_policy, SOURCE_FIELDS
from .runtime_bundle import read_runtime_bundle
from .installed_shade_calibrated_artifact import read_calibrated_candidate, SCHEMA as CALIBRATED_CANDIDATE_SCHEMA
from .policy_registration import read_calibrated_installed_shade_registered_policy

SCHEMA='earthship-installed-shade-qualification-report/v1'
CALIBRATED_SCHEMA='earthship-installed-shade-qualification-report/v2'
FORECAST_GATES=BASE_GATES|{'calibrated_intervals'}
FIELDS={'schema','assessed_at','candidate_schema','candidate','candidate_bundle','policy',
    'registration_sha256','runtime','gates','scored_pairs','support','original_pair_bindings',
    'statistics','qualification_expires_at','source_errors','forecast_qualified',
    'advisory_qualified','recommended_stage','automatic_actuation_authorized','report_sha256'}


def _stage(gates):
    passed=all(gates.values())
    ready=all(gates[k] for k in FORECAST_GATES-{'predictive_skill'})
    return passed,'forecast_active' if passed else 'shadow' if ready else 'unavailable'


def _support(rows):
    result={}
    for hours in sorted({row['horizon_hours'] for row in rows}):
        subset=[row for row in rows if row['horizon_hours']==hours]
        independent,days=_sample(subset)
        result[str(hours)]=dict(raw_pairs=len(subset),independent_windows=len(independent),
            independent_days=len(days),metrics={name:_metrics(days,key) for name,key in
            (('model','model_error_f'),('persistence','persistence_error_f'),('recent_cycle','recent_cycle_error_f'))})
    return result


def _score_packets(packets,*,assessed_at,candidate=None,version=1):
    if not isinstance(packets,list) or not 1<=len(packets)<=10000:
        raise ValueError('bounded complete original score packets required')
    reader,scorer=read_issued_capture,score_issued_capture
    if version==2:
        from .installed_shade_calibrated_origin import read_calibrated_capture,score_calibrated_capture
        reader,scorer=read_calibrated_capture,score_calibrated_capture
    elif version!=1:raise ValueError('explicit installed-domain pair contract required')
    records={};rows=[];bindings=[];seen=set();bytes_used=0
    for packet in packets:
        if not isinstance(packet,dict) or set(packet)!=SOURCE_FIELDS or not isinstance(packet['origin_path'],str):
            raise ValueError('closed original source packet required')
        path=packet['origin_path']
        if path not in records:
            if len(records)>=256:raise ValueError('original capture count exceeds bound')
            records[path]=reader(Path(path));bytes_used+=len(_canonical(records[path]))
            if bytes_used>64000000:raise ValueError('original capture bytes exceed bound')
        result=scorer(records[path],**{k:v for k,v in packet.items() if k!='origin_path'},assessed_at=assessed_at)
        row=result['scored_pair'];identity=(row['issue_at'],row['target_at'],row['horizon_hours'])
        if identity in seen:raise ValueError('duplicate original scored window')
        seen.add(identity)
        if candidate is not None and any(row[key]!=candidate[key] for key in ('artifact_sha256','runtime_sha256','sensor_epochs')):
            raise ValueError('mixed frozen candidate/runtime/sensor phase evidence')
        rows.append(row);bindings.append({k:v for k,v in result.items() if k.endswith('sha256')})
    calibrated=bool(rows) and all(type(row['interval_covered']) is bool and
        type(row['interval_width_f']) in (int,float) and row['interval_width_f']>=0 for row in rows)
    return dict(rows=rows,bindings=bindings,calibrated_intervals=calibrated,support=_support(rows))


def qualify_installed_shade_candidate(**values):
    return _qualify_installed_shade_candidate(**values,version=1)


def qualify_calibrated_installed_shade_candidate(**values):
    return _qualify_installed_shade_candidate(**values,version=2)


def _qualify_installed_shade_candidate(*,registration_path,candidate_path,runtime_bundle_path,original_pairs,now,version):
    now=_utc(now);gates={name:False for name in sorted(FORECAST_GATES)};errors={}
    registration=None;policy=None;bundle=None;runtime=None;pairs=None;statistics=None;deadline=None
    registration_reader=read_calibrated_installed_shade_registered_policy if version==2 else read_installed_shade_registered_policy
    candidate_reader=read_calibrated_candidate if version==2 else read_candidate_bundle
    def attempt(name,operation):
        try:return operation()
        except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):
            errors[name]='missing, invalid or incompatible original evidence';return None
    if registration_path is not None:
        registration=attempt('preregistered_policy',lambda:registration_reader(registration_path))
        if registration is not None:policy=registration['policy'];gates['preregistered_policy']=True
    if policy is not None and candidate_path is not None:
        def candidate():
            loaded=candidate_reader(candidate_path,expected_runtime_revision=policy['candidate']['runtime_sha256'],assessed_at=now)
            artifact=loaded['artifact'];expected=policy['candidate']
            if (artifact['artifact_sha256']!=expected['artifact_sha256'] or
                _utc(artifact['trained_through'])!=_utc(expected['trained_through']) or
                _utc(artifact['created_at'])!=_utc(expected['created_at']) or
                artifact['sensor_epochs']!=expected['sensor_epochs'] or
                len((artifact['base_candidate'] if version==2 else artifact)['dynamics']['coefficients'])!=expected['active_parameter_count']):
                raise ValueError('frozen supported-domain candidate differs')
            return loaded
        bundle=attempt('frozen_candidate',candidate)
        gates['frozen_candidate']=bundle is not None
        # Loading the bundle has just replayed original native-v2 training input
        # receipts, exact cutoffs, source phases and numerical diagnostics.
        gates['qualified_training_sources']=bundle is not None
        gates['measured_fit']=bool(bundle and bundle['fit_evidence']['fit_gates_passed'])
    if policy is not None and runtime_bundle_path is not None:
        def runtime_source():
            value=read_runtime_bundle(runtime_bundle_path)
            if _digest(value['runtime'])!=policy['candidate']['runtime_sha256']:
                raise ValueError('frozen original runtime differs')
            return value
        runtime=attempt('frozen_runtime',runtime_source);gates['frozen_runtime']=runtime is not None
    if policy is not None and gates['frozen_candidate'] and gates['frozen_runtime']:
        pairs=attempt('original_source_pairs',lambda:_score_packets(original_pairs,assessed_at=now,candidate=policy['candidate'],version=version))
        gates['original_source_pairs']=pairs is not None
        gates['calibrated_intervals']=bool(pairs and pairs['calibrated_intervals'])
        if pairs is not None:
            deadline=qualification_deadline(policy,pairs['rows'])
            if not pairs['calibrated_intervals']:
                errors['calibrated_intervals']='original issued uncertainty is uncalibrated or unavailable'
            else:
                statistics=attempt('predictive_skill',lambda:assess_predictive_skill(policy,pairs['rows'],now=now))
                gates['predictive_skill']=bool(statistics and statistics['statistical_forecast_gates_passed'] and deadline is not None and now<deadline)
    forecast,stage=_stage(gates)
    body=dict(schema=CALIBRATED_SCHEMA if version==2 else SCHEMA,candidate_schema=CALIBRATED_CANDIDATE_SCHEMA if version==2 else CANDIDATE_SCHEMA,assessed_at=now.isoformat(),
        candidate=deepcopy(policy['candidate']) if policy else None,candidate_bundle=bundle,policy=deepcopy(policy),
        registration_sha256=registration['registration_sha256'] if registration else None,runtime=runtime,
        gates=gates,scored_pairs=pairs['rows'] if pairs else [],support=pairs['support'] if pairs else {},
        original_pair_bindings=pairs['bindings'] if pairs else [],statistics=statistics,
        qualification_expires_at=deadline.isoformat() if deadline else None,source_errors=errors,
        forecast_qualified=forecast,advisory_qualified=False,recommended_stage=stage,automatic_actuation_authorized=False)
    body['report_sha256']=_digest(body)
    return _validate_installed_shade_qualification_report(body,version=version)


def validate_installed_shade_qualification_report(record):
    return _validate_installed_shade_qualification_report(record,version=1)


def validate_calibrated_installed_shade_qualification_report(record):
    return _validate_installed_shade_qualification_report(record,version=2)


def _validate_installed_shade_qualification_report(record,*,version):
    if (not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=(CALIBRATED_SCHEMA if version==2 else SCHEMA) or
            record['candidate_schema']!=(CALIBRATED_CANDIDATE_SCHEMA if version==2 else CANDIDATE_SCHEMA) or
            _digest({k:v for k,v in record.items() if k!='report_sha256'})!=record['report_sha256']):
        raise ValueError('closed supported-domain qualification report required')
    gates=record['gates']
    if not isinstance(gates,dict) or set(gates)!=FORECAST_GATES or any(type(v) is not bool for v in gates.values()):
        raise ValueError('exact derived qualification gates required')
    forecast,stage=_stage(gates)
    if (record['forecast_qualified'] is not forecast or record['recommended_stage']!=stage or
            record['advisory_qualified'] is not False or record['automatic_actuation_authorized'] is not False):
        raise ValueError('stage differs from original qualification gates')
    _utc(record['assessed_at'])
    if record['policy'] is not None:
        validate_policy(record['policy'])
        if record['candidate']!=record['policy']['candidate']:raise ValueError('report frozen candidate differs from policy')
    for gate,field in (('preregistered_policy','registration_sha256'),('frozen_candidate','candidate_bundle'),('frozen_runtime','runtime')):
        if gates[gate] and record[field] is None:raise ValueError('passing gate lacks original component')
    if gates['qualified_training_sources'] and not gates['frozen_candidate']:
        raise ValueError('source gate lacks original verified candidate')
    if gates['measured_fit'] and (record['candidate_bundle'] is None or record['candidate_bundle']['fit_evidence']['fit_gates_passed'] is not True):
        raise ValueError('fit gate differs from source numerical proof')
    rows=record['scored_pairs']
    if not isinstance(rows,list) or len(rows)>10000 or _canonical(_support(rows))!=_canonical(record['support']):
        raise ValueError('reported support differs from source-scored rows')
    if gates['original_source_pairs'] and (not rows or len(record['original_pair_bindings'])!=len(rows)):
        raise ValueError('original source bindings missing')
    calibrated=bool(rows) and all(type(row['interval_covered']) is bool and type(row['interval_width_f']) in (int,float) and row['interval_width_f']>=0 for row in rows)
    if gates['calibrated_intervals'] is not calibrated:raise ValueError('interval gate differs from actually issued uncertainty')
    if gates['predictive_skill']:
        expected=assess_predictive_skill(record['policy'],rows,now=record['assessed_at'])
        deadline=qualification_deadline(record['policy'],rows)
        if (_canonical(expected)!=_canonical(record['statistics']) or not expected['statistical_forecast_gates_passed'] or
                deadline is None or _utc(record['assessed_at'])>=deadline or record['qualification_expires_at']!=deadline.isoformat()):
            raise ValueError('skill/freshness differs from source statistical assessment')
    return record


def render_installed_shade_qualification_report(record):
    return _render_installed_shade_qualification_report(record,version=1)


def render_calibrated_installed_shade_qualification_report(record):
    return _render_installed_shade_qualification_report(record,version=2)


def _render_installed_shade_qualification_report(record,*,version):
    _validate_installed_shade_qualification_report(record,version=version)
    lines=['# Installed-shade thermal qualification', '',
        'Recommended stage: '+record['recommended_stage'],
        'Assessed at: '+record['assessed_at'],
        'Forecast qualified: '+str(record['forecast_qualified']).lower(),
        'Advice: withheld', 'Automatic actuation: disabled', '',
        'Source and qualification gates:']
    lines.extend('- '+name+': '+('passed' if value else 'not passed')
                 for name,value in sorted(record['gates'].items()))
    lines.extend(['', 'Original independent evidence:'])
    for hours,value in record['support'].items():
        lines.append('- '+hours+'h: '+str(value['independent_windows'])+
            ' non-overlapping windows, '+str(value['independent_days'])+' local days')
    if not record['support']:lines.append('- No qualified original source pairs supplied.')
    if record['source_errors']:
        lines.extend(['', 'Missing or incompatible evidence:'])
        lines.extend('- '+name+': '+reason for name,reason in sorted(record['source_errors'].items()))
    if version==2:
        import json
        policy=record['policy'] or {};bundle=record['candidate_bundle'] or {}
        artifact=bundle.get('artifact') or {};fit=bundle.get('fit_evidence') or {}
        core=artifact.get('base_candidate') or {}
        audit=dict(frozen_candidate=record['candidate'],
            base_training_interval={key:core.get(key) for key in ('trained_from','trained_through')},
            evaluation_intervals=policy.get('intervals'),
            thresholds=policy.get('thresholds'),thresholds_by_regime=policy.get('thresholds_by_regime'),
            statistical_confidence=policy.get('confidence_level'),
            calibration=artifact.get('calibration'),
            fit={key:fit.get(key) for key in ('optimizer','conditioning','support','stability','fit_gates_passed')},
            independent_support=record['support'],statistics=record['statistics'],
            qualification_expires_at=record['qualification_expires_at'],
            original_pair_bindings=record['original_pair_bindings'])
        lines.extend(['','Frozen evidence, thresholds and measured results:','```json',
            json.dumps(audit,sort_keys=True,indent=2,allow_nan=False),'```'])
    lines.extend(['', 'This report is a diagnostic cache. Release must freshly replay the original sources.'])
    return '\n'.join(lines)+'\n'


def write_installed_shade_qualification_report(directory,record):
    return _write_installed_shade_qualification_report(directory,record,version=1)


def write_calibrated_installed_shade_qualification_report(directory,record):
    return _write_installed_shade_qualification_report(directory,record,version=2)


def _write_installed_shade_qualification_report(directory,record,*,version):
    from .forcing_capture import _private_directory
    from .runtime_bundle import _owned_bytes,_write_private,_sync_directory
    from .rollback import _rename_new
    from uuid import uuid4
    _validate_installed_shade_qualification_report(record,version=version)
    root=_private_directory(Path(directory));report=deepcopy(record)
    members=((root/(report['report_sha256']+'.installed-shade-qualification-v'+str(version)+'.json'),_canonical(report)),
        (root/(report['report_sha256']+'.installed-shade-qualification-v'+str(version)+'.md'),_render_installed_shade_qualification_report(report,version=version).encode()))
    for target,raw in members:
        if len(raw)>8000000:raise ValueError('bounded private qualification report required')
        if target.exists():
            if _owned_bytes(target,8000000)!=raw:raise ValueError('original qualification report differs')
            continue
        temporary=root/('.qualification-'+uuid4().hex)
        try:
            _write_private(temporary,raw);_rename_new(temporary,target);_sync_directory(root)
        finally:
            if temporary.exists():temporary.unlink()
    return tuple(path for path,_ in members)
