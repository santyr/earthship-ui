"""Explicit v2 thermal publication, selected by fresh qualification only.

A trusted qualification_loader(now) recomputes source-backed gates. Serialized
report dictionaries and caller-supplied active switches are not accepted inputs.
"""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from uuid import UUID

from .schema import SHADOW_OUTPUT_FIELDS,ShadowOutput,validate_shadow_output
from .forcing_capture import _canonical
from .graduation_policy import _utc,_sha,validate_policy

SCHEMA='earthship-thermal-release/v1'
RELEASE_FIELDS={'schema','qualifiedAt','expiresAt','artifactSha256','runtimeSha256',
    'policySha256','reportSha256','sensorEpochs','forecastQualified','advisoryQualified','automaticActuation'}
FORECAST_GATES={'preregistered_policy','frozen_candidate','frozen_runtime',
    'qualified_training_sources','original_source_pairs','measured_fit','predictive_skill'}
MODES={'shadow','forecast_active','advisory_active','unavailable'}


def _epochs(value,*,optional=False):
    if optional and value=={}:return
    if not isinstance(value,dict) or set(value)!={'air','mass','outdoor'}:raise ValueError('exact frozen sensor epochs required')
    for epoch in value.values():
        if not isinstance(epoch,str) or str(UUID(epoch))!=epoch:raise ValueError('sensor epoch invalid')


def validate_release_output(payload):
    if not isinstance(payload,dict) or set(payload)!=SHADOW_OUTPUT_FIELDS|{'release'} or type(payload['version']) is not int or payload['version']!=2 or payload['status'] not in MODES:
        raise ValueError('exact version 2 thermal publication required')
    release=payload['release']
    if not isinstance(release,dict) or set(release)!=RELEASE_FIELDS or release['schema']!=SCHEMA:
        raise ValueError('closed versioned release metadata required')
    for name in ('forecastQualified','advisoryQualified','automaticActuation'):
        if type(release[name]) is not bool:raise ValueError('exact release qualification flags required')
    if release['automaticActuation']:raise ValueError('automatic thermal actuation prohibited')
    for field in ('artifactSha256','runtimeSha256','policySha256','reportSha256'):
        if release[field] is not None:_sha(release[field])
    mode=payload['status'];available=payload['confidence']['grade']!='unavailable'
    if mode=='unavailable' and (available or release['forecastQualified'] or release['advisoryQualified']):raise ValueError('unavailable release cannot claim qualification')
    if mode=='shadow' and (not available or release['forecastQualified'] or release['advisoryQualified'] or payload['confidence']['grade']!='low'):
        raise ValueError('shadow release qualification differs')
    if mode in {'forecast_active','advisory_active'}:
        if (not available or release['forecastQualified'] is not True or payload['confidence']['grade']!='high' or
                any(release[field] is None for field in ('artifactSha256','runtimeSha256','policySha256','reportSha256'))):
            raise ValueError('active release lacks verified qualification metadata')
        _epochs(release['sensorEpochs'])
        assessed,expires=map(_utc,(release['qualifiedAt'],release['expiresAt']))
        issue=_utc(payload['generatedAt'])
        if not issue<expires or assessed>issue+timedelta(minutes=20) or not assessed<expires or expires-assessed>timedelta(hours=24):raise ValueError('active qualification expired or future')
    else:_epochs(release['sensorEpochs'],optional=True)
    if mode=='forecast_active' and release['advisoryQualified']:raise ValueError('forecast-only mode cannot claim action advice')
    if mode=='advisory_active' and (not release['advisoryQualified'] or payload['confidence']['actionLabels']!='confirmed'):
        raise ValueError('advisory mode requires confirmed action qualification')
    if not release['advisoryQualified']:
        if payload['schedule'] and (payload['schedule']['candidate'] is not None or any(value!=0 for value in payload['schedule']['effect'].values())):
            raise ValueError('unqualified action recommendation cannot be published')
        if any(point['actions'] for point in payload['forecast']['trajectory']):raise ValueError('unqualified trajectory actions cannot be published')
    # Reuse exact shared numeric/provenance validation without changing v1 semantics.
    base={key:deepcopy(value) for key,value in payload.items() if key!='release'}
    base['version']=1;base['status']='shadow'
    if base['confidence']['grade']=='high':base['confidence']['grade']='low'
    validate_shadow_output(base)
    if len(_canonical(payload))>=16384:raise ValueError('thermal release publication exceeds 16 KiB')
    return payload


def unavailable_release(now,reason='thermal release qualification unavailable'):
    output=ShadowOutput.empty(_utc(now)).to_dict();output['version']=2;output['status']='unavailable'
    output['reasons']=[reason]
    output['release']=dict(schema=SCHEMA,qualifiedAt=None,expiresAt=None,artifactSha256=None,
        runtimeSha256=None,policySha256=None,reportSha256=None,sensorEpochs={},
        forecastQualified=False,advisoryQualified=False,automaticActuation=False)
    return validate_release_output(output)



def forecast_regimes(forecast_rows, shadow):
    """Thermal regimes actually consumed by the original published trajectory."""
    from .pipeline import interpolate_hourly_forecast
    validate_shadow_output(shadow)
    if not isinstance(forecast_rows, (list, tuple)) or not 2 <= len(forecast_rows) <= 800:
        raise ValueError('bounded original forecast forcing required for regime coverage')
    trajectory = shadow['forecast']['trajectory']
    if not trajectory:
        raise ValueError('available original trajectory required')
    forcing = interpolate_hourly_forecast(forecast_rows,
        start=_utc(trajectory[0]['at']), end=_utc(trajectory[-1]['at']))
    mapping = {'warm': 'warm', 'spring': 'shoulder', 'fall_charge': 'shoulder', 'winter': 'winter'}
    return sorted({mapping[row['mode']] for row in forcing})


def _published_clock_matches(published, original):
    # The unchanged v1 pipeline publishes whole seconds. The full-precision
    # original remains bound by the frozen artifact digest and policy.
    published=_utc(published)
    return published.microsecond==0 and published==_utc(original).replace(microsecond=0)


def build_release_output(*,shadow,qualification_loader,now,artifact_sha256,runtime_sha256,sensor_epochs,forecast_rows=None):
    """Recompute qualification, bind current identity, and derive explicit mode."""
    now=_utc(now)
    try:
        if not callable(qualification_loader):raise ValueError('fresh qualification evaluator required')
        validate_shadow_output(shadow)
        if shadow['confidence']['grade']=='unavailable':raise ValueError('thermal inputs unavailable')
        if shadow['schedule']['candidate'] is not None:raise ValueError('baseline simulation required for forecast-only release')
        issued=_utc(shadow['generatedAt']);elapsed=now-issued
        if not timedelta(0)<=elapsed<=timedelta(minutes=20):raise ValueError('current forecast input is stale or future')
        for role in ('air','mass','outdoor','radiation'):
            age=shadow['provenance']['currentAgeMinutes'][role]
            if age is None or age+elapsed.total_seconds()/60>20:raise ValueError('current thermal sensor stale')
        _sha(artifact_sha256);_sha(runtime_sha256);_epochs(sensor_epochs)
        report=qualification_loader(now)
        if (not isinstance(report,dict) or report.get('schema')!='earthship-thermal-qualification-report/v3' or
                report.get('automatic_actuation_authorized') is not False):raise ValueError('qualified decision required')
        body={key:value for key,value in report.items() if key!='report_sha256'}
        if sha256(_canonical(body)).hexdigest()!=report['report_sha256']:raise ValueError('qualification decision changed')
        policy=report['policy'];validate_policy(policy);candidate=report['candidate']
        if (candidate!=policy['candidate'] or candidate['artifact_sha256']!=artifact_sha256 or
                candidate['runtime_sha256']!=runtime_sha256 or candidate['sensor_epochs']!=sensor_epochs or
                not _published_clock_matches(shadow['model']['createdAt'],candidate['created_at']) or
                not _published_clock_matches(shadow['model']['trainedThrough'],candidate['trained_through'])):
            raise ValueError('current artifact/runtime/epoch differs from frozen qualification')
        assessed=_utc(report['assessed_at']);expires=min(_utc(report['qualification_expires_at']),assessed+timedelta(hours=policy['max_qualification_age_hours']))
        if not assessed<=now<expires:raise ValueError('qualification is stale or future')
        gates=report['gates']
        if not isinstance(gates,dict) or set(gates)!=FORECAST_GATES or any(type(value) is not bool for value in gates.values()):
            raise ValueError('complete recomputed forecast gates required')
        forecast=all(gates.values())
        if report['forecast_qualified'] is not forecast:raise ValueError('forecast pass differs from actual gates')
        if forecast and not set(forecast_regimes(forecast_rows, shadow)).issubset(policy['regimes']):
            raise ValueError('current thermal regimes lack preregistered qualified support')
        # The v1 combined evaluator currently withholds action advice.
        if report['advisory_qualified'] is not False:raise ValueError('confirmed action evaluator unavailable')
        if report['recommended_stage']=='unavailable':raise ValueError('source or numerical qualification unavailable')
        output=deepcopy(shadow);output['version']=2;output['status']='forecast_active' if forecast else 'shadow'
        output['confidence']['grade']='high' if forecast else 'low'
        output['schedule']['candidate']=None
        output['schedule']['effect']={'morningMassDeltaF':0.0,'hallwayPeakDeltaF':0.0}
        for point in output['forecast']['trajectory']:point['actions']=[]
        output['provenance']['modelAgeHours']=round((issued-_utc(candidate['created_at'])).total_seconds()/3600,3)
        output['provenance']['trainingDataAgeHours']=round((issued-_utc(candidate['trained_through'])).total_seconds()/3600,3)
        output['release']=dict(schema=SCHEMA,qualifiedAt=assessed.isoformat(),expiresAt=expires.isoformat(),
            artifactSha256=artifact_sha256,runtimeSha256=runtime_sha256,policySha256=policy['policy_sha256'],
            reportSha256=report['report_sha256'],sensorEpochs=deepcopy(sensor_epochs),
            forecastQualified=forecast,advisoryQualified=False,automaticActuation=False)
        return validate_release_output(output)
    except (OSError,RuntimeError,ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return unavailable_release(now)


def write_release_output(path, payload):
    """Atomically persist one validated v2 state without changing the v1 writer."""
    from .pipeline import _write_validated_output
    validate_release_output(payload)
    return _write_validated_output(path, payload)
