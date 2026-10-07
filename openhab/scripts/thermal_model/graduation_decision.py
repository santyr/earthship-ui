"""Recompute thermal release gates from original source and measured evidence.

Reports are review caches. Production must rerun qualification from these raw
references; a serialized active flag or report digest is never an authority.
"""
from copy import deepcopy
from dataclasses import fields,asdict
from datetime import datetime,timedelta
from hashlib import sha256
import json
import math
from pathlib import Path

from thermal_model.artifacts import validate_artifact
from thermal_model.schema import ThermalSample
from thermal_model.dataset import _observe_latent_mass
from thermal_model.forcing_capture import _canonical
from thermal_model.origin_capture import read_observed_origin_capture as read_origin_capture
from thermal_model.runtime_bundle import read_runtime_bundle
from thermal_model.fit_evidence import read_fit_evidence
from thermal_model.graduation_policy import _utc,validate_policy
from thermal_model.graduation_statistics import assess_predictive_skill
from thermal_model.temperature_history import (STREAMS,STEP,_ceil,_validate_receipt,
                                               validate_evidence_manifest)
from thermal_model.pipeline import _normalize_hourly_rows
from thermal_model.policy_registration import read_registered_policy,SOURCE_FIELDS
from thermal_model.graduation_evidence import _score_origin_record

SCHEMA='earthship-thermal-qualification-report/v2'
FORECAST_GATES={'preregistered_policy','frozen_candidate','frozen_runtime',
    'qualified_training_sources','original_source_pairs','measured_fit','predictive_skill'}
FIELDS={'schema','assessed_at','candidate','intervals','policy_sha256','registration_sha256',
    'policy','runtime','qualification_expires_at','gates','fit','training_sources','statistics','original_pair_bindings','source_errors',
    'forecast_qualified','advisory_qualified','recommended_stage',
    'automatic_actuation_authorized','report_sha256'}


def _digest(value):return sha256(_canonical(value)).hexdigest()


def verify_training_sources(value,artifact,epochs):
    """Verify raw canonical samples and complete native grids against the artifact."""
    if not isinstance(value,dict) or set(value)!={'schema','samples','temperature_grids'} or value['schema']!='earthship-thermal-training-sources/v1':
        raise ValueError('complete raw training samples and native grids required')
    manifest=artifact.data_manifest;temperature=manifest.get('temperature_evidence')
    validate_evidence_manifest(temperature,start=artifact.trained_from,end=artifact.trained_through)
    start,end=map(_utc,(artifact.trained_from,artifact.trained_through))
    if start<_utc(temperature['cutover']):raise ValueError('legacy training rows are not receipt-qualified')
    rows=value['samples']
    if (not isinstance(rows,list) or len(rows)!=manifest['sample_count'] or not 1<=len(rows)<=120000 or
            len(_canonical(value))>64000000):raise ValueError('bounded complete raw training sample set required')
    # Preserve dataset_manifest canonical row encoding exactly.
    if sha256(json.dumps(rows,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()!=manifest['canonical_rows_sha256']:
        raise ValueError('raw training samples differ from artifact digest')
    grids=value['temperature_grids']
    if not isinstance(grids,dict) or set(grids)!=set(STREAMS):raise ValueError('all required native training roles required')
    native={};support={}
    for role in STREAMS:
        info=temperature['roles'][role];grid=grids[role]
        if info['legacy_points'] or not isinstance(grid,list) or len(grid)!=info['targets']:
            raise ValueError('training grid differs from native-only source manifest')
        cursor=_ceil(start);digest=sha256();mapping={};qualified=missing=0
        for pair in grid:
            if not isinstance(pair,list) or len(pair)!=2 or _utc(pair[0])!=cursor or cursor>=end:
                raise ValueError('native training target order/coverage differs')
            receipt=pair[1]
            if receipt is not None:
                _validate_receipt(receipt,cursor)
                if receipt['streamEpoch']!=epochs[role]:raise ValueError('training hardware epoch differs')
                qualified+=1
            else:missing+=1
            digest.update((json.dumps([cursor.isoformat(),receipt],sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode())
            mapping[cursor]=receipt;cursor+=STEP
        if (cursor<end or digest.hexdigest()!=info['grid_sha256'] or
                qualified!=info['qualified'] or missing!=info['missing']):
            raise ValueError('raw native training receipts differ from source summary')
        native[role]=mapping;support[role]=dict(qualified=qualified,missing=missing,epoch=epochs[role])
    sample_fields={entry.name for entry in fields(ThermalSample)}
    parsed=[];previous=None
    for row in rows:
        if not isinstance(row,dict) or set(row)!=sample_fields|{'_radiation_provenance'}:
            raise ValueError('exact canonical thermal training row required')
        at=_utc(row['at'])
        if not start<=at<end or previous is not None and at<=previous:raise ValueError('training row order/interval differs')
        previous=at
        for role,field in (('air','air_f'),('mass','north_wall_f'),('outdoor','outdoor_f')):
            receipt=native[role].get(at)
            if receipt is None or type(row[field]) not in (int,float) or row[field]!=receipt['temperatureF']:
                raise ValueError('training sample differs from qualified original temperature')
        item={key:row[key] for key in sample_fields};item['at']=at
        item['mass_f']=row['north_wall_f'];parsed.append(ThermalSample(**item))
    observed=_observe_latent_mass(parsed)
    if any(not math.isclose(expected.mass_f,row['mass_f'],rel_tol=0,abs_tol=1e-10) for expected,row in zip(observed,rows)):
        raise ValueError('training latent mass differs from original causal observer')
    return dict(schema='earthship-thermal-training-source-assessment/v1',
        training_inputs_sha256=manifest['canonical_rows_sha256'],source_sha256=_digest(value),
        sample_count=len(rows),roles=support)


def _forcing(record):
    snapshot=record['raw_forecast']
    if not isinstance(snapshot,dict) or not isinstance(snapshot.get('hourly'),dict) or not snapshot['hourly']:
        raise ValueError('original Open-Meteo weather snapshot unavailable')
    hourly=snapshot['hourly'];times=hourly.get('time')
    if not isinstance(times,list) or not 2<=len(times)<=800:raise ValueError('bounded original hourly weather times required')
    for value in times:
        if not isinstance(value,str):raise ValueError('original weather timestamp invalid')
        try:datetime.fromisoformat(value)
        except ValueError:raise ValueError('original weather timestamp invalid') from None
    for field in ('temperature_2m','shortwave_radiation','wind_speed_10m','weather_code'):
        values=hourly.get(field)
        if not isinstance(values,list) or len(values)!=len(times) or any(type(value) not in (int,float) or not math.isfinite(value) for value in values):
            raise ValueError('original weather field invalid or incomplete')
    rows=_normalize_hourly_rows(record['forecast_rows']);issue=_utc(record['issued_at'])
    required_end=max(_utc(point['at']) for point in record['output']['forecast']['trajectory'])
    if not rows[0]['at']<=issue or rows[-1]['at']<required_end:
        raise ValueError('original weather forcing does not cover issued trajectory')
    return _digest(snapshot)


def _stage(gates):
    forecast=all(gates[name] for name in FORECAST_GATES)
    structurally_ready=all(gates[name] for name in FORECAST_GATES-{'predictive_skill'})
    return forecast,('forecast_active' if forecast else 'shadow' if structurally_ready else 'unavailable')



def qualification_deadline(policy, rows):
    """Earliest expiry of the latest qualified prospective outcome per horizon."""
    intervals = policy['intervals']; latest = []
    for horizon in policy['horizons']:
        targets = [_utc(row['target_at']) for row in rows if row['horizon_hours'] == horizon
            and _utc(row['issue_at']) >= _utc(intervals['prospective_start'])
            and (intervals['prospective_end'] is None or _utc(row['target_at']) <= _utc(intervals['prospective_end']))]
        if not targets:
            return None
        latest.append(max(targets))
    return min(latest)+timedelta(hours=policy['max_qualification_age_hours'])


def qualify_candidate(*,registration_path,artifact,fit_evidence_path,training_sources,
                      runtime_bundle_path,original_pairs,now):
    """Assess genuine source-bound evidence; missing inputs close their exact gates."""
    now=_utc(now);gates={name:False for name in sorted(FORECAST_GATES)};errors={}
    policy=None;registration=None;fit=None;training=None;statistics=None;bundle=None;bindings=[];scored=[]
    def attempt(name,operation):
        try:return operation()
        except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):
            errors[name]='missing, invalid or incompatible original evidence';return None
    if registration_path is not None:
        registration=attempt('preregistered_policy',lambda:read_registered_policy(registration_path))
        if registration is not None:
            policy=registration['policy'];gates['preregistered_policy']=True
    if artifact is not None and policy is not None:
        def candidate():
            validate_artifact(artifact)
            expected=policy['candidate']
            if (_digest(asdict(artifact))!=expected['artifact_sha256'] or
                    _utc(artifact.trained_through)!=_utc(expected['trained_through']) or
                    _utc(artifact.created_at)!=_utc(expected['created_at'])):raise ValueError('frozen candidate differs')
            return artifact
        gates['frozen_candidate']=attempt('frozen_candidate',candidate) is not None
    if runtime_bundle_path is not None and policy is not None:
        def runtime():
            bundle=read_runtime_bundle(runtime_bundle_path)
            if _digest(bundle['runtime'])!=policy['candidate']['runtime_sha256']:raise ValueError('frozen runtime differs')
            return bundle
        bundle=attempt('frozen_runtime',runtime)
        gates['frozen_runtime']=bundle is not None
    if gates['frozen_candidate']:
        training=attempt('qualified_training_sources',lambda:verify_training_sources(training_sources,artifact,policy['candidate']['sensor_epochs']))
        gates['qualified_training_sources']=training is not None
        if fit_evidence_path is not None:
            fit=attempt('measured_fit',lambda:read_fit_evidence(fit_evidence_path,artifact))
            gates['measured_fit']=bool(fit and fit['fit_gates_passed'] and fit['active_parameter_count']==policy['candidate']['active_parameter_count'])
    if policy is not None and gates['frozen_candidate'] and gates['frozen_runtime']:
        def pairs():
            if not isinstance(original_pairs,list) or not 1<=len(original_pairs)<=10000:raise ValueError('bounded original pairs required')
            records={};total=0
            for packet in original_pairs:
                if not isinstance(packet,dict) or set(packet)!=SOURCE_FIELDS:raise ValueError('complete original score packet required')
                path=packet['origin_path']
                if not isinstance(path,str):raise ValueError('original capture path required')
                if path not in records:
                    if len(records)>=256:raise ValueError('original capture count exceeds bound')
                    records[path]=read_origin_capture(Path(path));total+=len(_canonical(records[path]))
                    if total>64000000:raise ValueError('original capture bytes exceed bound')
                record=records[path]
                result=_score_origin_record(record,**{key:packet[key] for key in SOURCE_FIELDS-{'origin_path'}},assessed_at=now)
                row=result['scored_pair'];candidate=policy['candidate']
                if (row['artifact_sha256']!=candidate['artifact_sha256'] or row['runtime_sha256']!=candidate['runtime_sha256'] or
                        row['sensor_epochs']!=candidate['sensor_epochs']):raise ValueError('mixed candidate/runtime/epochs')
                forcing_sha256=_forcing(record)
                scored.append(row);bindings.append({key:value for key,value in result.items() if key.endswith('sha256')}|{'forcing_sha256':forcing_sha256})
            return True
        gates['original_source_pairs']=attempt('original_source_pairs',pairs) is True
        if not gates['original_source_pairs']:scored=[];bindings=[]
        statistics=attempt('predictive_skill',lambda:assess_predictive_skill(policy,scored,now=now))
        gates['predictive_skill']=bool(statistics and statistics['statistical_forecast_gates_passed'])
    deadline = (qualification_deadline(policy, scored) if policy is not None and gates['original_source_pairs'] else None)
    if gates['predictive_skill'] and (deadline is None or not now < deadline):
        gates['predictive_skill'] = False
        errors['predictive_skill'] = 'qualified prospective outcomes expired or incomplete'
    forecast,stage=_stage(gates)
    body=dict(schema=SCHEMA,assessed_at=now.isoformat(),qualification_expires_at=deadline.isoformat() if deadline else None,candidate=deepcopy(policy['candidate']) if policy else None,
        intervals=deepcopy(policy['intervals']) if policy else None,policy_sha256=policy['policy_sha256'] if policy else None,
        registration_sha256=registration['registration_sha256'] if registration else None,
        policy=deepcopy(policy),runtime=bundle,gates=gates,
        fit=fit,training_sources=training,statistics=statistics,original_pair_bindings=bindings,source_errors=errors,
        forecast_qualified=forecast,advisory_qualified=False,recommended_stage=stage,automatic_actuation_authorized=False)
    body['report_sha256']=_digest(body)
    return validate_qualification_report(body)


def validate_qualification_report(record):
    if not isinstance(record,dict) or set(record)!=FIELDS or record['schema']!=SCHEMA:
        raise ValueError('closed qualification report required')
    if _digest({key:value for key,value in record.items() if key!='report_sha256'})!=record['report_sha256']:
        raise ValueError('qualification report digest differs')
    gates=record['gates']
    if not isinstance(gates,dict) or set(gates)!=FORECAST_GATES or any(type(value) is not bool for value in gates.values()):
        raise ValueError('exact derived qualification gates required')
    forecast,stage=_stage(gates)
    if (record['forecast_qualified'] is not forecast or record['recommended_stage']!=stage or
            record['advisory_qualified'] is not False or record['automatic_actuation_authorized'] is not False):
        raise ValueError('stage differs from qualification gates')
    for gate,field in (('preregistered_policy','registration_sha256'),('frozen_candidate','candidate'),
            ('qualified_training_sources','training_sources'),('measured_fit','fit'),('predictive_skill','statistics')):
        if gates[gate] and record[field] is None:raise ValueError('passing gate lacks underlying evidence')
    if gates['original_source_pairs'] and not record['original_pair_bindings']:raise ValueError('original source bindings missing')
    if gates['measured_fit'] and record['fit']['fit_gates_passed'] is not True:raise ValueError('fit gate differs from measured proof')
    if gates['predictive_skill'] and record['statistics']['statistical_forecast_gates_passed'] is not True:raise ValueError('skill gate differs from actual statistics')
    if record['policy'] is not None:
        validate_policy(record['policy'])
        if record['policy']['candidate']!=record['candidate'] or record['policy']['intervals']!=record['intervals'] or record['policy']['policy_sha256']!=record['policy_sha256']:
            raise ValueError('qualification report differs from frozen policy')
    if gates['frozen_runtime'] and (record['runtime'] is None or _digest(record['runtime']['runtime'])!=record['candidate']['runtime_sha256']):
        raise ValueError('runtime gate differs from frozen bundle')
    assessed = _utc(record['assessed_at'])
    if record['qualification_expires_at'] is not None:
        expires = _utc(record['qualification_expires_at'])
        if record['policy'] is None or expires > assessed+timedelta(hours=record['policy']['max_qualification_age_hours']):
            raise ValueError('source qualification deadline exceeds declared freshness')
    if forecast and (record['qualification_expires_at'] is None or not assessed < _utc(record['qualification_expires_at'])):
        raise ValueError('active qualification lacks unexpired original outcomes')
    return record


def render_qualification_report(record):
    validate_qualification_report(record)
    lines=['# Thermal qualification decision','',f"Recommended stage: {record['recommended_stage']}",
        'Automatic actuation: disabled','',f"Candidate: {record['candidate']}",
        f"Intervals: {record['intervals']}",f"Original outcome qualification expires: {record['qualification_expires_at']}",'','| Gate | Result |','| --- | --- |']
    lines.extend(f"| {name} | {'pass' if value else 'fail'} |" for name,value in record['gates'].items())
    if record['policy']:
        lines.extend(['','## Declared thresholds','',json.dumps(record['policy'],indent=2,sort_keys=True)])
    if record['statistics']:
        lines.extend(['','## Predictive evidence','',json.dumps(record['statistics'],indent=2,sort_keys=True)])
    if record['fit']:
        lines.extend(['','## Measured fit','',json.dumps(record['fit'],indent=2,sort_keys=True)])
    lines.extend(['','Action advice: withheld; separate confirmed-action qualification remains required.'])
    return '\n'.join(lines)+'\n'


RELEASE_INPUT_FIELDS={'schema','registration_path','artifact_path','fit_evidence_path',
    'training_sources_path','runtime_bundle_path','pairs_path'}


def load_qualification_inputs(path):
    """Create a trusted evaluator from private source references, never pass flags."""
    from thermal_model.policy_registration import _read_private
    from thermal_model.training_sources import _read_private as read_source_bytes
    from thermal_model.origin_capture import _object
    from thermal_model.artifacts import _artifact_from_payload
    references=_read_private(Path(path))
    if (not isinstance(references,dict) or set(references)!=RELEASE_INPUT_FIELDS or
            references['schema']!='earthship-thermal-release-inputs/v1'):
        raise ValueError('closed original release input references required')
    for name,value in references.items():
        if name=='schema':continue
        if not isinstance(value,str) or not Path(value).is_absolute():raise ValueError('absolute original evidence paths required')
    def read_json(file):
        def reject(_):raise ValueError('nonfinite original qualification input')
        try:return json.loads(read_source_bytes(Path(file)),object_pairs_hook=_object,parse_constant=reject)
        except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('original qualification input JSON invalid') from None
    def evaluate(now):
        # Every call rereads the exact artifact/table/pairs; no report or clock override.
        artifact=_artifact_from_payload(read_json(references['artifact_path']))
        training=read_json(references['training_sources_path'])
        pairs=read_json(references['pairs_path'])
        return qualify_candidate(registration_path=references['registration_path'],artifact=artifact,
            fit_evidence_path=references['fit_evidence_path'],training_sources=training,
            runtime_bundle_path=references['runtime_bundle_path'],original_pairs=pairs,now=_utc(now))
    return evaluate
