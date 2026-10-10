"""Explicit installed-domain publication selected from freshly replayed sources.

A prepared qualification is invocation-local. Public preparation reads raw
references and never accepts a cached report/active switch. The original numeric
forecast stays intact for its separate persisted evidence receipt.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path

from .forcing_capture import _canonical
from .graduation_policy import _utc,_sha,_finite
from .installed_shade_artifact import _digest,read_candidate_bundle
from .installed_shade_calibrated_artifact import read_calibrated_candidate,read_raw_calibrated_candidate
from .installed_shade_qualification import (qualify_installed_shade_candidate,
    qualify_published_installed_shade_candidate,validate_installed_shade_qualification_report,
    validate_calibrated_installed_shade_qualification_report,validate_published_installed_shade_qualification_report,
    qualify_raw_published_installed_shade_candidate,validate_raw_published_installed_shade_qualification_report,
    qualify_complete_raw_installed_shade_candidate,validate_complete_raw_installed_shade_qualification_report)
from .origin_capture import build_runtime_binding
from .policy_registration import _read_private
from .runtime_bundle import read_runtime_bundle
from .temperature_history import _sensor_bindings

# Pin the publication and its local Python dependency closure, including gates.
RUNTIME_PATHS=frozenset({
    'thermal_model/replay_budget.py',
    'thermal_model/airflow_migration.py',
    'thermal_model/journal.py',
    'weather_temperature_receiver.py',
    'thermal_installed_intel.py',
    'thermal_model/installed_shade_live.py',
    'thermal_model/installed_shade_live_inputs.py',
    'thermal_model/action_history.py',
    'thermal_model/capture_readers.py',
    'thermal_model/capture_guard.py',
    'thermal_temperature_runtime.py',
    'hourly_temperature_runtime.py',
    'weather_temperature_history.py',
    'weather_temperature_config.py',
    'thermal_model/installed_shade_published_origin.py',
    'weather_temperature_evidence.py',
    'weather_temperature_reader.py',
    'thermal_model/__init__.py',
    'thermal_intel.py',
    'thermal_model/actions.py',
    'thermal_model/artifacts.py',
    'thermal_model/behavior.py',
    'thermal_model/dataset.py',
    'thermal_model/dynamics.py',
    'thermal_model/environment_bundle.py',
    'thermal_model/evaluation.py',
    'thermal_model/fit_evidence.py',
    'thermal_model/forcing_capture.py',
    'thermal_model/forecast_history.py',
    'thermal_model/graduation_decision.py',
    'thermal_model/graduation_evidence.py',
    'thermal_model/graduation_policy.py',
    'thermal_model/graduation_statistics.py',
    'thermal_model/installed_shade_artifact.py',
    'thermal_model/installed_shade_calibrated_artifact.py',
    'thermal_model/installed_shade_calibrated_origin.py',
    'thermal_model/installed_shade_calibration.py',
    'thermal_model/installed_shade_dynamics.py',
    'thermal_model/installed_shade_fit.py',
    'thermal_model/installed_shade_inputs.py',
    'thermal_model/installed_shade_origin.py',
    'thermal_model/installed_shade_publication.py',
    'thermal_model/installed_shade_qualification.py',
    'thermal_model/offline_training.py',
    'thermal_model/operational_origin.py',
    'thermal_model/origin_capture.py',
    'thermal_model/pipeline.py',
    'thermal_model/policy_registration.py',
    'thermal_model/recent_cycles.py',
    'thermal_model/release.py',
    'thermal_model/rollback.py',
    'thermal_model/runtime_bundle.py',
    'thermal_model/schema.py',
    'thermal_model/solar.py',
    'thermal_model/temperature_history.py',
    'thermal_model/training_assembly.py',
    'thermal_model/training_inputs.py',
    'thermal_model/training_sources.py',
})

SCHEMA='earthship-installed-shade-publication/v1'
RELEASE_SCHEMA='earthship-installed-shade-release/v1'
CALIBRATED_RAW_SCHEMA='earthship-installed-shade-publication/v2'
CALIBRATED_RAW_RELEASE_SCHEMA='earthship-installed-shade-release/v2'
RAW_RUNTIME_PATHS=RUNTIME_PATHS|frozenset({
    'weather_temperature_sources.py','forecast_input_capture.py','forecast_temperature_origin.py',
    'thermal_model/installed_shade_raw_score_sources.py',
    'thermal_model/installed_shade_score_inputs.py','thermal_model/installed_shade_score_collection.py',
})
RAW_REFERENCE_SCHEMA='earthship-installed-shade-release-inputs/v2'
COMPLETE_RAW_REFERENCE_SCHEMA='earthship-installed-shade-release-inputs/v3'
REFERENCE_SCHEMA='earthship-installed-shade-release-inputs/v1'
REFERENCE_FIELDS={'schema','registration_path','candidate_path','runtime_bundle_path','original_pairs_path'}
FIELDS={'schema','version','status','generatedAt','validUntil','model','forecast','confidence','release','reasons'}
RELEASE_FIELDS={'schema','qualifiedAt','expiresAt','artifactSha256','runtimeSha256','policySha256',
    'reportSha256','originCaptureSha256','calibrationSha256','sensorEpochs','sensorEpochSemantics',
    'forecastQualified','advisoryQualified','automaticActuation'}
NUMERIC_FIELDS={'schema','status','generated_at','artifact_sha256','runtime_sha256','horizon_hours',
    'initial','origin_actions','trajectory','confidence','prediction_intervals','advice','release_authorized','automatic_actuation'}
MAX_BYTES=16384
MAX_PUBLICATION_AGE=timedelta(minutes=10)
ERRORS=(OSError,RuntimeError,ValueError,TypeError,KeyError,AttributeError,OverflowError)


def _clock():return datetime.now(timezone.utc)


@dataclass(frozen=True)
class PreparedInstalledQualification:
    report_json:bytes|None
    candidate_json:bytes|None
    source_ready:bool
    registration_absent:bool=False
    runtime_paths:tuple[str,...]=()
    require_raw_sources:bool=False


@dataclass(frozen=True)
class PreparedRawInstalledQualification:
    report_json:bytes|None
    candidate_json:bytes|None
    source_ready:bool
    registration_absent:bool=False
    runtime_paths:tuple[str,...]=()
    require_raw_sources:bool=True


def _check_profile(version):
    if type(version) is not int or version not in (1,2):
        raise ValueError('explicit installed publication profile required')


def _validator(report, *, _version=1):
    _check_profile(_version)
    if _version==2:return validate_complete_raw_installed_shade_qualification_report(report)
    if report.get('schema')=='earthship-installed-shade-qualification-report/v4':
        return validate_raw_published_installed_shade_qualification_report(report)
    if report.get('schema')=='earthship-installed-shade-qualification-report/v3':
        return validate_published_installed_shade_qualification_report(report)
    if report.get('schema')=='earthship-installed-shade-qualification-report/v2':
        return validate_calibrated_installed_shade_qualification_report(report)
    return validate_installed_shade_qualification_report(report)


def _prepare_installed_qualification(reference_path, *, _version=1):
    """Recompute gates before acquiring short-lived current origin inputs."""
    _check_profile(_version)
    prepared_type=PreparedRawInstalledQualification if _version==2 else PreparedInstalledQualification
    try:
        at=_utc(_clock());path=Path(reference_path);refs=_read_private(path)
        if not isinstance(refs,dict) or set(refs)!=REFERENCE_FIELDS or refs['schema'] not in ((COMPLETE_RAW_REFERENCE_SCHEMA,) if _version==2 else (REFERENCE_SCHEMA,RAW_REFERENCE_SCHEMA)):
            raise ValueError('closed original installed release references required')
        raw_required=_version==2 or refs['schema']==RAW_REFERENCE_SCHEMA
        values={}
        for key in REFERENCE_FIELDS-{'schema'}:
            value=refs[key]
            if value is None and key in ('registration_path','original_pairs_path'):values[key]=None;continue
            if not isinstance(value,str) or not value:raise ValueError('private original source path required')
            target=Path(value);values[key]=target if target.is_absolute() else path.parent/target
        archived=read_runtime_bundle(values['runtime_bundle_path']);revision=_digest(archived['runtime'])
        required_paths=RAW_RUNTIME_PATHS if raw_required else RUNTIME_PATHS
        if not required_paths <= set(archived['runtime']['source_manifest']):
            raise ValueError('publication/gate code missing from runtime closure')
        paths=tuple(archived['revision_paths'])
        if _canonical(build_runtime_binding(Path(__file__).resolve().parents[1],paths))!=_canonical(archived['runtime']):
            raise ValueError('executing runtime differs from archived release runtime')
        if _version==2 and not values['candidate_path'].name.endswith('.installed-shade-candidate-v3.json'):
            raise ValueError('original raw calibrated candidate v3 required')
        calibrated=_version==2 or values['candidate_path'].name.endswith('.installed-shade-candidate-v2.json')
        reader=read_raw_calibrated_candidate if _version==2 else (read_calibrated_candidate if calibrated else read_candidate_bundle)
        loaded=reader(values['candidate_path'],expected_runtime_revision=revision,assessed_at=at)
        pairs=[] if values['original_pairs_path'] is None else _read_private(values['original_pairs_path'])
        qualify=qualify_complete_raw_installed_shade_candidate if _version==2 else (qualify_raw_published_installed_shade_candidate if raw_required else (qualify_published_installed_shade_candidate if calibrated else qualify_installed_shade_candidate))
        report=qualify(registration_path=values['registration_path'],candidate_path=values['candidate_path'],
            runtime_bundle_path=values['runtime_bundle_path'],original_pairs=pairs,now=at)
        _validator(report,_version=_version)
        if raw_required and report['schema']!=('earthship-installed-shade-qualification-report/v5' if _version==2 else 'earthship-installed-shade-qualification-report/v4'):
            raise ValueError('raw source qualification contract required')
        absent=values['registration_path'] is None
        if not absent and report['policy'] is None:
            raise ValueError('configured registration failed; bootstrap refused')
        ready=loaded['fit_evidence']['fit_gates_passed'] is True and (not calibrated or loaded['calibration']['summary']['complete'] is True)
        return prepared_type(_canonical(report),_canonical(loaded['artifact']),ready,absent,paths,raw_required)
    except ERRORS:return prepared_type(None,None,False)


def _unavailable_installed_publication(now, *, _version=1):
    _check_profile(_version)
    now=_utc(now)
    value=dict(schema=CALIBRATED_RAW_SCHEMA if _version==2 else SCHEMA,version=5 if _version==2 else 4,status='unavailable',generatedAt=now.isoformat(),
        validUntil=(now+MAX_PUBLICATION_AGE).isoformat(),model={},forecast=None,
        confidence=dict(grade='unavailable',actionLabels='withheld'),reasons=['Thermal forecast evidence unavailable'],
        release=dict(schema=CALIBRATED_RAW_RELEASE_SCHEMA if _version==2 else RELEASE_SCHEMA,qualifiedAt=None,expiresAt=None,artifactSha256=None,runtimeSha256=None,
            policySha256=None,reportSha256=None,originCaptureSha256=None,calibrationSha256=None,sensorEpochs={},
            sensorEpochSemantics='declared_hardware_phase',forecastQualified=False,advisoryQualified=False,automaticActuation=False))
    return _validate_installed_publication(value,_version=_version)


def _read_origin(path, *, _version=1):
    _check_profile(_version)
    from .installed_shade_origin import read_issued_capture,_prediction
    from .installed_shade_calibrated_origin import read_calibrated_capture,_prediction as calibrated_prediction
    path=Path(path)
    if _version==2:
        from .installed_shade_calibrated_origin import read_raw_calibrated_capture
        if not path.name.endswith('.installed-shade-origin-v4.json'):
            raise ValueError('original raw-calibrated numeric capture v4 required')
        return read_raw_calibrated_capture(path),lambda record:calibrated_prediction(record,_version=4)
    if path.name.endswith('.installed-shade-origin-v2.json'):return read_calibrated_capture(path),calibrated_prediction
    if path.name.endswith('.installed-shade-origin-v1.json'):return read_issued_capture(path),_prediction
    raise ValueError('typed original installed forecast required')


def _build_installed_publication(original_path,prepared, *, _version=1):
    """Bind fresh original inputs to an invocation's source-replayed decision."""
    _check_profile(_version)
    now=_utc(_clock())
    try:
        if not isinstance(prepared,PreparedRawInstalledQualification if _version==2 else PreparedInstalledQualification) or prepared.source_ready is not True:
            raise ValueError('source-prepared qualification required')
        report=json.loads(prepared.report_json);artifact=json.loads(prepared.candidate_json);_validator(report,_version=_version)
        if (type(prepared.require_raw_sources) is not bool or (_version==2 and prepared.require_raw_sources is not True) or
                (prepared.require_raw_sources and report['schema']!=('earthship-installed-shade-qualification-report/v5' if _version==2 else 'earthship-installed-shade-qualification-report/v4'))):
            raise ValueError('prepared raw-source profile lacks v4 qualification')
        original,predict=_read_origin(original_path,_version=_version)
        if not prepared.runtime_paths or _canonical(build_runtime_binding(Path(__file__).resolve().parents[1],prepared.runtime_paths))!=_canonical(original['runtime']):
            raise ValueError('executing runtime changed before delivery')
        if _canonical(artifact)!=_canonical(original['candidate']):raise ValueError('current original candidate differs')
        issue=_utc(original['issued_at']);assessed=_utc(report['assessed_at'])
        if not issue<=now<issue+MAX_PUBLICATION_AGE or not assessed<=now<assessed+timedelta(minutes=20):
            raise ValueError('original forecast or source assessment is stale/future')
        # Recheck original native expiry at delivery time without pretending this
        # mathematical replay view is a newly persisted original publication.
        current=deepcopy(original);current['published_at']=now.isoformat()
        output,phases=predict(current)
        if _canonical(output)!=_canonical(original['output']):raise ValueError('original numeric forecast changed')
        policy=report['policy'];forecast=False;expires=None
        if policy is None and prepared.registration_absent is not True:
            raise ValueError('only explicit absence permits shadow bootstrap')
        if policy is not None:
            expected=policy['candidate']
            if (expected['artifact_sha256']!=artifact['artifact_sha256'] or expected['runtime_sha256']!=_digest(original['runtime']) or
                    expected['sensor_epochs']!=phases or report['candidate']!=expected):raise ValueError('frozen release binding differs')
            if report['recommended_stage']=='unavailable':raise ValueError('current source/numerical release gate failed')
            forecast=all(report['gates'].values())
            if report['forecast_qualified'] is not forecast:raise ValueError('release pass differs from actual gates')
            if forecast:
                if output['schema']!=('earthship-installed-shade-forecast/v3' if _version==2 else 'earthship-installed-shade-forecast/v2'):raise ValueError('uncalibrated forecast cannot activate')
                expires=_utc(report['qualification_expires_at'])
                if not assessed<=now<expires:raise ValueError('current qualification expired')
                for band in output['prediction_intervals']:
                    hours=str(band['horizon_hours']);regime=band['regime'];width=band['upper_air_f']-band['lower_air_f']
                    if (regime not in policy['regimes'] or width>min(policy['thresholds'][hours]['max_mean_interval_width_f'],
                            policy['thresholds_by_regime'][hours][regime]['max_mean_interval_width_f'])):
                        raise ValueError('current calibrated regime/width is unqualified')
        valid=min(issue+MAX_PUBLICATION_AGE,expires) if expires is not None else issue+MAX_PUBLICATION_AGE
        value=dict(schema=CALIBRATED_RAW_SCHEMA if _version==2 else SCHEMA,version=5 if _version==2 else 4,status='forecast_active' if forecast else 'shadow',generatedAt=issue.isoformat(),
            validUntil=valid.isoformat(),model=dict(createdAt=artifact['created_at'],trainedThrough=artifact['trained_through'],codeRevision=artifact['code_revision']),
            forecast=deepcopy(output),confidence=dict(grade='high' if forecast else 'low',actionLabels='withheld'),
            reasons=['Forecast qualified; action advice withheld'] if forecast else ['Predictive qualification incomplete; action advice withheld'],
            release=dict(schema=CALIBRATED_RAW_RELEASE_SCHEMA if _version==2 else RELEASE_SCHEMA,qualifiedAt=assessed.isoformat(),expiresAt=expires.isoformat() if expires else None,
                artifactSha256=artifact['artifact_sha256'],runtimeSha256=_digest(original['runtime']),
                policySha256=policy['policy_sha256'] if policy else None,reportSha256=report['report_sha256'],originCaptureSha256=original['capture_sha256'],
                calibrationSha256=artifact['calibration']['calibration_sha256'] if 'calibration' in artifact else None,
                sensorEpochs=phases,sensorEpochSemantics='declared_hardware_phase',forecastQualified=forecast,advisoryQualified=False,automaticActuation=False))
        return _validate_installed_publication(value,_version=_version)
    except ERRORS:return _unavailable_installed_publication(now,_version=_version)


def _validate_installed_publication(value, *, _version=1):
    if type(_version) is not int or _version not in (1,2):
        raise ValueError('explicit installed publication version required')
    if (not isinstance(value,dict) or set(value)!=FIELDS or value['schema']!=(CALIBRATED_RAW_SCHEMA if _version==2 else SCHEMA) or type(value['version']) is not int or value['version']!=(5 if _version==2 else 4) or
            value['status'] not in ('unavailable','shadow','forecast_active') or len(_canonical(value))>=MAX_BYTES):
        raise ValueError('closed bounded installed publication required')
    issue,valid=map(_utc,(value['generatedAt'],value['validUntil']))
    if not issue<valid<=issue+MAX_PUBLICATION_AGE:raise ValueError('bounded publication freshness required')
    release=value['release'];confidence=value['confidence'];mode=value['status']
    if (not isinstance(release,dict) or set(release)!=RELEASE_FIELDS or release['schema']!=(CALIBRATED_RAW_RELEASE_SCHEMA if _version==2 else RELEASE_SCHEMA) or
            release['sensorEpochSemantics']!='declared_hardware_phase' or release['advisoryQualified'] is not False or release['automaticActuation'] is not False or
            type(release['forecastQualified']) is not bool or not isinstance(confidence,dict) or set(confidence)!={'grade','actionLabels'} or
            confidence['actionLabels']!='withheld' or confidence['grade']!={'unavailable':'unavailable','shadow':'low','forecast_active':'high'}[mode] or
            release['forecastQualified'] is not (mode=='forecast_active')):
        raise ValueError('mode/confidence/authority differs')
    if not isinstance(value['reasons'],list) or not 1<=len(value['reasons'])<=8 or any(not isinstance(r,str) or not 1<=len(r.encode())<=256 for r in value['reasons']):
        raise ValueError('bounded publication reasons required')
    for key in ('artifactSha256','runtimeSha256','policySha256','reportSha256','originCaptureSha256','calibrationSha256'):
        if release[key] is not None:_sha(release[key])
    if mode=='unavailable':
        if value['forecast'] is not None or value['model']!={} or release['sensorEpochs']!={} or any(release[k] is not None for k in RELEASE_FIELDS-{'schema','sensorEpochs','sensorEpochSemantics','forecastQualified','advisoryQualified','automaticActuation'}):
            raise ValueError('unavailable output must carry no fabricated evidence')
        return value
    _sensor_bindings(release['sensorEpochs'])
    assessed=_utc(release['qualifiedAt'])
    if any(release[k] is None for k in ('artifactSha256','runtimeSha256','reportSha256','originCaptureSha256')):
        raise ValueError('original source identity required')
    if mode=='forecast_active':
        expires=_utc(release['expiresAt'])
        if (release['policySha256'] is None or release['calibrationSha256'] is None or not assessed<expires or valid>expires or
                expires-assessed>timedelta(hours=24)):raise ValueError('active qualification identity/expiry required')
    elif release['expiresAt'] is not None:raise ValueError('shadow cannot claim active qualification expiry')
    model=value['model']
    if (not isinstance(model,dict) or set(model)!={'createdAt','trainedThrough','codeRevision'} or
            not _utc(model['trainedThrough'])<=_utc(model['createdAt'])<=issue):raise ValueError('frozen model chronology required')
    _sha(model['codeRevision'])
    forecast=value['forecast']
    if (not isinstance(forecast,dict) or set(forecast)!=NUMERIC_FIELDS or forecast['schema'] not in
            (('earthship-installed-shade-forecast/v3',) if _version==2 else
             ('earthship-installed-shade-forecast/v1','earthship-installed-shade-forecast/v2')) or forecast['status']!='shadow' or
            forecast['confidence']!='unqualified' or forecast['advice']!=[] or forecast['release_authorized'] is not False or forecast['automatic_actuation'] is not False or
            _utc(forecast['generated_at'])!=issue or forecast['artifact_sha256']!=release['artifactSha256'] or forecast['runtime_sha256']!=release['runtimeSha256']):
        raise ValueError('unaltered original numerical forecast required')
    hours=forecast['horizon_hours'];points=forecast['trajectory']
    if type(hours) is not int or not 1<=hours<=72 or not isinstance(points,list) or len(points)!=hours:raise ValueError('complete original hourly trajectory required')
    for index,point in enumerate(points,1):
        if not isinstance(point,dict) or set(point)!={'at','air_f','mass_f'} or _utc(point['at'])!=issue+timedelta(hours=index):raise ValueError('exact original trajectory clock required')
        if any(not -40<=_finite(point[k])<=140 for k in ('air_f','mass_f')):raise ValueError('trajectory violates physical bounds')
    initial=forecast['initial'];actions=forecast['origin_actions']
    if not isinstance(initial,dict) or set(initial)!={'air_f','mass_f','outdoor_f'} or any(not -40<=_finite(x)<=140 for x in initial.values()):raise ValueError('original initial state required')
    if (not isinstance(actions,dict) or set(actions)!={'indoor_shade_closed','outdoor_shade_present','vent_open','vent_provenance','mode','action_knowledge'} or
            _finite(actions['outdoor_shade_present'])!=1 or actions['action_knowledge']!='as_of_snapshot_not_outcome_confirmation' or
            actions['mode'] not in ('warm','spring','fall_charge','winter','unknown') or
            not isinstance(actions['vent_provenance'],str) or not 1<=len(actions['vent_provenance'])<=80 or
            any(_finite(actions[k]) not in (0.,1.) for k in ('indoor_shade_closed','vent_open'))):raise ValueError('original installed-domain action knowledge required')
    if forecast['schema'].endswith('/v1'):
        if forecast['prediction_intervals'] is not None or mode=='forecast_active' or release['calibrationSha256'] is not None:raise ValueError('uncalibrated forecast cannot claim uncertainty/release')
    else:
        bands=forecast['prediction_intervals']
        if not isinstance(bands,list) or len(bands)!=4 or release['calibrationSha256'] is None:raise ValueError('four original calibrated targets required')
        for h,band in zip((1,6,12,24),bands):
            if (not isinstance(band,dict) or set(band)!={'at','horizon_hours','lower_air_f','upper_air_f','nominal_coverage','regime','calibration_sha256'} or
                    type(band['horizon_hours']) is not int or band['horizon_hours']!=h or h>hours or _utc(band['at'])!=issue+timedelta(hours=h) or
                    band['nominal_coverage']!=.90 or band['calibration_sha256']!=release['calibrationSha256'] or
                    band['regime']!={'warm':'warm','winter':'winter','spring':'shoulder','fall_charge':'shoulder'}.get(actions['mode']) or not _finite(band['lower_air_f'])<=points[h-1]['air_f']<=_finite(band['upper_air_f'])):
                raise ValueError('exact original calibrated interval required')
            _finite(band['upper_air_f']-band['lower_air_f'])
    return value



def validate_installed_publication(value):
    return _validate_installed_publication(value,_version=1)


def validate_raw_installed_publication(value):
    """Validate the raw-calibrated output shape; this grants no release authority."""
    return _validate_installed_publication(value,_version=2)



def prepare_installed_qualification(reference_path):
    return _prepare_installed_qualification(reference_path,_version=1)


def prepare_raw_installed_qualification(reference_path):
    """Freshly replay all raw evidence phases from closed release-inputs/v3."""
    return _prepare_installed_qualification(reference_path,_version=2)


def unavailable_installed_publication(now):
    return _unavailable_installed_publication(now,_version=1)


def unavailable_raw_installed_publication(now):
    return _unavailable_installed_publication(now,_version=2)


def build_installed_publication(original_path,prepared):
    return _build_installed_publication(original_path,prepared,_version=1)


def build_raw_installed_publication(original_path,prepared):
    """Publish only the decision from the complete raw qualification profile."""
    return _build_installed_publication(original_path,prepared,_version=2)
