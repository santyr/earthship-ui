"""Source-replayed installed-domain qualification; cached reports grant no authority.

The existing statistical thresholds remain unchanged. Uncalibrated observations
remain visible for diagnostics but cannot pass a production release decision.
"""
from copy import deepcopy
from pathlib import Path
from time import monotonic as _replay_time
import os
import stat

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
from .policy_registration import (read_calibrated_installed_shade_registered_policy,
    read_raw_calibrated_installed_shade_registered_policy)
from .installed_shade_calibrated_artifact import (read_raw_calibrated_candidate,
    RAW_SCHEMA as RAW_CALIBRATED_CANDIDATE_SCHEMA)

SCHEMA='earthship-installed-shade-qualification-report/v1'
CALIBRATED_SCHEMA='earthship-installed-shade-qualification-report/v2'
PUBLISHED_SCHEMA='earthship-installed-shade-qualification-report/v3'
RAW_PUBLISHED_SCHEMA='earthship-installed-shade-qualification-report/v4'
COMPLETE_RAW_SCHEMA='earthship-installed-shade-qualification-report/v5'
REPORT_SCHEMAS={1:SCHEMA,2:CALIBRATED_SCHEMA,3:PUBLISHED_SCHEMA,4:RAW_PUBLISHED_SCHEMA,5:COMPLETE_RAW_SCHEMA}
RAW_FORECAST_GATES=BASE_GATES|{'calibrated_intervals','raw_native_score_sources'}
COMPLETE_RAW_FORECAST_GATES=RAW_FORECAST_GATES|{'raw_development_sources','raw_calibration_sources'}
FORECAST_GATES=BASE_GATES|{'calibrated_intervals'}
FIELDS={'schema','assessed_at','candidate_schema','candidate','candidate_bundle','policy',
    'registration_sha256','runtime','gates','scored_pairs','support','original_pair_bindings',
    'statistics','qualification_expires_at','source_errors','forecast_qualified',
    'advisory_qualified','recommended_stage','automatic_actuation_authorized','report_sha256'}

COMPLETE_RAW_FIELDS=FIELDS|{'registration_source_bindings'}


def _report_gates(version):
    return COMPLETE_RAW_FORECAST_GATES if version==5 else RAW_FORECAST_GATES if version==4 else FORECAST_GATES


def _report_candidate_schema(version):
    return RAW_CALIBRATED_CANDIDATE_SCHEMA if version==5 else CALIBRATED_CANDIDATE_SCHEMA if version in (2,3,4) else CANDIDATE_SCHEMA


def _raw_digest_bindings(values):
    from .graduation_policy import _sha
    if not isinstance(values,list) or not 1<=len(values)<=10000:
        raise ValueError('original raw digest bindings required')
    for binding in values:
        if not isinstance(binding,dict):raise ValueError('original raw digest binding required')
        for key in ('native_binding_sha256','raw_score_sources_sha256'):_sha(binding.get(key))


def _raw_calibration_binding(bundle):
    from .installed_shade_calibration import RAW_FIELDS,RAW_SCHEMA,RAW_SOURCE_CONTRACT
    from .installed_shade_calibrated_artifact import _metadata
    artifact=bundle['artifact'];calibration=bundle['calibration']
    if (artifact['schema']!=RAW_CALIBRATED_CANDIDATE_SCHEMA or not isinstance(calibration,dict) or
            set(calibration)!=RAW_FIELDS or calibration['schema']!=RAW_SCHEMA or
            calibration['source_contract']!=RAW_SOURCE_CONTRACT or calibration['release_authorized'] is not False or
            calibration['coverage_guaranteed'] is not False or
            _digest({k:v for k,v in calibration.items() if k!='calibration_sha256'})!=calibration['calibration_sha256'] or
            calibration['base_candidate_sha256']!=artifact['base_candidate']['artifact_sha256'] or
            calibration['runtime_sha256']!=_digest(artifact['base_runtime']) or calibration['sensor_epochs']!=artifact['sensor_epochs'] or
            _canonical(_metadata(calibration,_version=3))!=_canonical(artifact['calibration'])):
        raise ValueError('original raw calibration differs from frozen candidate')
    _raw_digest_bindings(calibration['source_pair_bindings'])


def _stage(gates):
    passed=all(gates.values())
    ready=all(value for name,value in gates.items() if name!='predictive_skill')
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
    if version in (4,5):return _score_raw_packets(packets,assessed_at=assessed_at,candidate=candidate,source_version=3 if version==5 else 2)
    reader,scorer=read_issued_capture,score_issued_capture
    if version in (2,3,4):
        from .installed_shade_calibrated_origin import read_calibrated_capture,score_calibrated_capture
        reader,scorer=read_calibrated_capture,score_calibrated_capture
    elif version!=1:raise ValueError('explicit installed-domain pair contract required')
    records={};rows=[];bindings=[];seen=set();bytes_used=0
    for packet in packets:
        if not isinstance(packet,dict) or set(packet)!=SOURCE_FIELDS or not isinstance(packet['origin_path'],str):
            raise ValueError('closed original source packet required')
        path=packet['origin_path']
        if version==3:
            name=Path(path).name
            if name.endswith('.installed-shade-origin-v3.json'):
                from .installed_shade_published_origin import read_publication_capture,score_publication_capture
                reader,scorer=read_publication_capture,score_publication_capture
            elif name.endswith('.installed-shade-origin-v2.json'):
                reader,scorer=read_calibrated_capture,score_calibrated_capture
            else:raise ValueError('explicit original numeric2 or published3 source packet required')
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


def _bound_source_size(path,maximum):
    from .forcing_capture import _private_directory
    path=Path(path)
    if not path.is_absolute() or path.resolve(strict=True)!=path:raise ValueError('resolved original replay source required')
    _private_directory(path.parent);info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or
            info.st_nlink!=1 or not 1<=info.st_size<=maximum):raise ValueError('owned bounded replay source required')
    return info.st_size


def _raw_replay_preflight(packets,check_budget,*,source_version=2):
    if type(source_version) is not int or source_version not in (2,3):raise ValueError('explicit raw replay source version required')
    from .installed_shade_calibration import _read_json
    headers=set();captures=set();queries=set();header_bytes=capture_bytes=query_bytes=0
    for reference in packets:
        check_budget()
        if (not isinstance(reference,dict) or set(reference)!={'raw_score_sources_path'} or
                not isinstance(reference['raw_score_sources_path'],str) or not 1<=len(reference['raw_score_sources_path'])<=1024):
            raise ValueError('explicit original raw score archive required')
        path=Path(reference['raw_score_sources_path'])
        if path in headers:raise ValueError('duplicate original raw score archive')
        headers.add(path);header_bytes+=_bound_source_size(path,4000000)
        if header_bytes>64000000:raise ValueError('aggregate raw score headers exceed bound')
        record=_read_json(path)
        if (not isinstance(record,dict) or set(record)!={'schema','score_sources','native_binding','release_authority'} or
                record['schema']!='earthship-installed-shade-score-sources/v'+str(source_version) or record['release_authority'] is not False or
                path.name!=_digest(record)+'.installed-shade-score-sources-v'+str(source_version)+'.json'):
            raise ValueError('original raw score header required')
        score=record['score_sources'];binding=record['native_binding']
        if (not isinstance(score,dict) or not isinstance(score.get('origin_path'),str) or not 1<=len(score['origin_path'])<=1024 or
                not isinstance(binding,dict) or not isinstance(binding.get('query_sources'),list) or
                not 1<=len(binding['query_sources'])<=24):raise ValueError('bounded raw replay references required')
        capture=Path(score['origin_path'])
        if capture not in captures:
            captures.add(capture);capture_bytes+=_bound_source_size(capture,2000000)
            if len(captures)>256 or capture_bytes>64000000:raise ValueError('aggregate original captures exceed bound')
        for name in binding['query_sources']:
            check_budget()
            if not isinstance(name,str) or not 1<=len(name)<=1024:raise ValueError('bounded raw query reference required')
            query=Path(name)
            if query not in queries:
                queries.add(query);query_bytes+=_bound_source_size(query,8*1024*1024)
                if len(queries)>8192 or query_bytes>128*1024*1024:raise ValueError('aggregate raw queries exceed bound')
    check_budget()


def _score_raw_packets(packets,*,assessed_at,candidate=None,source_version=2):
    from .installed_shade_raw_score_sources import read_raw_score_sources,read_calibrated_raw_score_sources
    reader=read_calibrated_raw_score_sources if source_version==3 else read_raw_score_sources
    deadline=_replay_time()+60
    def check_budget():
        if _replay_time()>deadline:raise ValueError('raw qualification replay time budget exceeded')
    check_budget();_raw_replay_preflight(packets,check_budget,source_version=source_version)
    rows=[];bindings=[];seen=set();paths=set()
    for reference in packets:
        check_budget()
        if (not isinstance(reference,dict) or set(reference)!={'raw_score_sources_path'} or
                not isinstance(reference['raw_score_sources_path'],str) or not 1<=len(reference['raw_score_sources_path'])<=1024):
            raise ValueError('explicit original raw score archive required')
        name=reference['raw_score_sources_path']
        if name in paths:raise ValueError('duplicate original raw score archive')
        paths.add(name);replayed=reader(Path(name),assessed_at=assessed_at,check_budget=check_budget)
        result=replayed['score'];row=result['scored_pair'];identity=(row['issue_at'],row['target_at'],row['horizon_hours'])
        if identity in seen:raise ValueError('duplicate original raw scored window')
        seen.add(identity)
        if candidate is not None and any(row[key]!=candidate[key] for key in ('artifact_sha256','runtime_sha256','sensor_epochs')):
            raise ValueError('mixed frozen raw candidate/runtime/sensor phase evidence')
        binding={k:v for k,v in result.items() if k.endswith('sha256')}
        binding.update({k:replayed[k] for k in ('native_binding_sha256','raw_score_sources_sha256')})
        rows.append(row);bindings.append(binding)
    check_budget()
    calibrated=bool(rows) and all(type(row['interval_covered']) is bool and
        type(row['interval_width_f']) in (int,float) and row['interval_width_f']>=0 for row in rows)
    return dict(rows=rows,bindings=bindings,calibrated_intervals=calibrated,support=_support(rows),raw_native_score_sources=True)


def qualify_raw_published_installed_shade_candidate(**values):
    return _qualify_installed_shade_candidate(**values,version=4)


def qualify_installed_shade_candidate(**values):
    return _qualify_installed_shade_candidate(**values,version=1)


def qualify_calibrated_installed_shade_candidate(**values):
    return _qualify_installed_shade_candidate(**values,version=2)


def qualify_published_installed_shade_candidate(**values):
    return _qualify_installed_shade_candidate(**values,version=3)


def _qualify_installed_shade_candidate(*,registration_path,candidate_path,runtime_bundle_path,original_pairs,now,version):
    now=_utc(now);gates={name:False for name in sorted(_report_gates(version))};errors={}
    registration=None;policy=None;bundle=None;runtime=None;pairs=None;statistics=None;deadline=None
    registration_reader=read_raw_calibrated_installed_shade_registered_policy if version==5 else (read_calibrated_installed_shade_registered_policy if version in (2,3,4) else read_installed_shade_registered_policy)
    candidate_reader=read_raw_calibrated_candidate if version==5 else (read_calibrated_candidate if version in (2,3,4) else read_candidate_bundle)
    def attempt(name,operation):
        try:return operation()
        except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):
            errors[name]='missing, invalid or incompatible original evidence';return None
    if registration_path is not None:
        def registered_source():
            value=registration_reader(registration_path)
            if version==5:
                if (value['schema']!='earthship-installed-shade-policy-registration/v3' or
                        value['candidate_schema']!=RAW_CALIBRATED_CANDIDATE_SCHEMA or
                        value['source_contract']!='earthship-installed-shade-score-sources/v2'):
                    raise ValueError('original raw development registration required')
                _raw_digest_bindings(value['development_source_bindings'])
                if len(value['development_source_bindings'])!=len(value['policy']['development']):
                    raise ValueError('complete original raw development bindings required')
            return value
        registration=attempt('preregistered_policy',registered_source)
        if registration is not None:policy=registration['policy'];gates['preregistered_policy']=True
    if version==5:gates['raw_development_sources']=registration is not None
    if policy is not None and candidate_path is not None:
        def candidate():
            loaded=candidate_reader(candidate_path,expected_runtime_revision=policy['candidate']['runtime_sha256'],assessed_at=now)
            artifact=loaded['artifact'];expected=policy['candidate']
            if (artifact['artifact_sha256']!=expected['artifact_sha256'] or
                _utc(artifact['trained_through'])!=_utc(expected['trained_through']) or
                _utc(artifact['created_at'])!=_utc(expected['created_at']) or
                artifact['sensor_epochs']!=expected['sensor_epochs'] or
                len((artifact['base_candidate'] if version in (2,3,4,5) else artifact)['dynamics']['coefficients'])!=expected['active_parameter_count']):
                raise ValueError('frozen supported-domain candidate differs')
            if version==5:_raw_calibration_binding(loaded)
            return loaded
        bundle=attempt('frozen_candidate',candidate)
        gates['frozen_candidate']=bundle is not None
        if version==5:gates['raw_calibration_sources']=bundle is not None
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
        if version in (4,5):gates['raw_native_score_sources']=bool(pairs and pairs['raw_native_score_sources'])
        gates['calibrated_intervals']=bool(pairs and pairs['calibrated_intervals'])
        if pairs is not None:
            deadline=qualification_deadline(policy,pairs['rows'])
            if not pairs['calibrated_intervals']:
                errors['calibrated_intervals']='original issued uncertainty is uncalibrated or unavailable'
            else:
                statistics=attempt('predictive_skill',lambda:assess_predictive_skill(policy,pairs['rows'],now=now))
                gates['predictive_skill']=bool(statistics and statistics['statistical_forecast_gates_passed'] and deadline is not None and now<deadline)
    forecast,stage=_stage(gates)
    body=dict(schema=REPORT_SCHEMAS[version],candidate_schema=_report_candidate_schema(version),assessed_at=now.isoformat(),
        candidate=deepcopy(policy['candidate']) if policy else None,candidate_bundle=bundle,policy=deepcopy(policy),
        registration_sha256=registration['registration_sha256'] if registration else None,runtime=runtime,
        gates=gates,scored_pairs=pairs['rows'] if pairs else [],support=pairs['support'] if pairs else {},
        original_pair_bindings=pairs['bindings'] if pairs else [],statistics=statistics,
        qualification_expires_at=deadline.isoformat() if deadline else None,source_errors=errors,
        forecast_qualified=forecast,advisory_qualified=False,recommended_stage=stage,automatic_actuation_authorized=False)
    if version==5:body['registration_source_bindings']=deepcopy(registration['development_source_bindings']) if registration else []
    body['report_sha256']=_digest(body)
    return _validate_installed_shade_qualification_report(body,version=version)


def validate_installed_shade_qualification_report(record):
    return _validate_installed_shade_qualification_report(record,version=1)


def validate_calibrated_installed_shade_qualification_report(record):
    return _validate_installed_shade_qualification_report(record,version=2)


def validate_published_installed_shade_qualification_report(record):
    return _validate_installed_shade_qualification_report(record,version=3)


def _validate_installed_shade_qualification_report(record,*,version):
    if (not isinstance(record,dict) or set(record)!=(COMPLETE_RAW_FIELDS if version==5 else FIELDS) or record['schema']!=REPORT_SCHEMAS[version] or
            record['candidate_schema']!=_report_candidate_schema(version) or
            _digest({k:v for k,v in record.items() if k!='report_sha256'})!=record['report_sha256']):
        raise ValueError('closed supported-domain qualification report required')
    gates=record['gates']
    if not isinstance(gates,dict) or set(gates)!=_report_gates(version) or any(type(v) is not bool for v in gates.values()):
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
    if version in (4,5):
        from .graduation_policy import _sha
        if gates['raw_native_score_sources'] is not gates['original_source_pairs']:
            raise ValueError('raw source gate lacks original independently replayed pairs')
        if gates['raw_native_score_sources']:
            for binding in record['original_pair_bindings']:
                if not isinstance(binding,dict):raise ValueError('raw source digest bindings required')
                for name in ('native_binding_sha256','raw_score_sources_sha256'):_sha(binding.get(name))
    if version==5:
        if (gates['raw_development_sources'] is not gates['preregistered_policy'] or
                gates['raw_calibration_sources'] is not gates['frozen_candidate']):
            raise ValueError('raw phase gates differ from original source components')
        if gates['raw_development_sources']:
            _raw_digest_bindings(record['registration_source_bindings'])
            if len(record['registration_source_bindings'])!=len(record['policy']['development']):
                raise ValueError('complete sealed raw development bindings required')
        elif record['registration_source_bindings']!=[]:raise ValueError('missing development cannot claim raw bindings')
        if gates['raw_calibration_sources']:_raw_calibration_binding(record['candidate_bundle'])
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


def render_published_installed_shade_qualification_report(record):
    return _render_installed_shade_qualification_report(record,version=3)


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
    if version in (2,3,4,5):
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
        if version==5:audit.update(raw_development_bindings=record['registration_source_bindings'],
            raw_calibration_bindings=(bundle.get('calibration') or {}).get('source_pair_bindings'))
        lines.extend(['','Frozen evidence, thresholds and measured results:','```json',
            json.dumps(audit,sort_keys=True,indent=2,allow_nan=False),'```'])
    lines.extend(['', 'This report is a diagnostic cache. Release must freshly replay the original sources.'])
    return '\n'.join(lines)+'\n'


def write_installed_shade_qualification_report(directory,record):
    return _write_installed_shade_qualification_report(directory,record,version=1)


def write_calibrated_installed_shade_qualification_report(directory,record):
    return _write_installed_shade_qualification_report(directory,record,version=2)


def write_published_installed_shade_qualification_report(directory,record):
    return _write_installed_shade_qualification_report(directory,record,version=3)


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


def validate_raw_published_installed_shade_qualification_report(record):
    return _validate_installed_shade_qualification_report(record,version=4)


def render_raw_published_installed_shade_qualification_report(record):
    return _render_installed_shade_qualification_report(record,version=4)


def write_raw_published_installed_shade_qualification_report(directory,record):
    return _write_installed_shade_qualification_report(directory,record,version=4)



def qualify_complete_raw_installed_shade_candidate(**values):
    return _qualify_installed_shade_candidate(**values,version=5)


def validate_complete_raw_installed_shade_qualification_report(record):
    return _validate_installed_shade_qualification_report(record,version=5)


def render_complete_raw_installed_shade_qualification_report(record):
    return _render_installed_shade_qualification_report(record,version=5)


def write_complete_raw_installed_shade_qualification_report(directory,record):
    return _write_installed_shade_qualification_report(directory,record,version=5)
