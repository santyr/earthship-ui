"""Native solar as-issued originals, independent of qualified actuation profiles."""
from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from astro_geometry_series import NativeGeometrySeries,replay_series
from astro_geometry import _instant
from native_thermal_artifact import validate_native_candidate,_read,LIMITS,fit_profile
from native_thermal_model import NativeInstalledShadeDynamics,RULE
from thermal_model.forcing_capture import _canonical
from thermal_model.graduation_policy import _utc,_sha
from thermal_model.origin_capture import _temperatures,_object
from thermal_model.installed_shade_origin import _origin_actions,_forecast_forcing
from thermal_model.installed_shade_raw_score_sources import build_compressed_native_origin_binding as build_binding,replay_compressed_native_origin_binding as replay_binding
from thermal_model import provisional_forecast as legacy
from thermal_model.runtime_bundle import _owned_bytes

CAPTURE_SCHEMA='earthship-provisional-thermal-origin/v2'
NUMERIC_SCHEMA='earthship-provisional-thermal-forecast/v2'
PUBLICATION_SCHEMA='earthship-provisional-thermal-publication/v2'
INPUT_FIELDS=legacy.INPUT_FIELDS
CAPTURE_FIELDS=legacy.CAPTURE_FIELDS|{'geometry','geometry_series_sha256'}
MAX_CAPTURE_BYTES=6*1024*1024
SOURCE='openhab/scripts/native_thermal_forecast.py'

def digest(value,field):return sha256(_canonical({k:v for k,v in value.items() if k!=field})).hexdigest()


def _candidate(value,runtime,identity,issue,check):
    checked=validate_native_candidate(value,assessed_at=issue,runtime=runtime,expected_artifact_sha256=identity,guard=check)
    if SOURCE not in checked['runtime']['native_source_manifest']:
        raise ValueError('native forecast implementation must be runtime-bound')
    return checked


def _numeric(candidate,inputs,geometry,*,issue,available,published,check_budget):
    check_budget()
    if not available<=issue<=published<issue+timedelta(seconds=90) or issue.second not in (0,15) or issue.microsecond or issue.minute%5:
        raise ValueError('aligned causal native provisional issue required')
    if not isinstance(inputs,dict) or set(inputs)!=INPUT_FIELDS:
        raise ValueError('complete original native provisional sources required')
    if _utc(inputs['origin_temperatures']['assessed_at'])>available:
        raise ValueError('temperature inputs unavailable at issue')
    phases,initial=_temperatures(inputs['origin_temperatures'],inputs['current'],issued_at=issue,published_at=published,version=2)
    if phases!=candidate['fit']['sensor_epochs']:raise ValueError('native provisional sensor phase differs')
    profile=fit_profile(candidate['fit'])
    actions=_origin_actions(inputs['action_snapshot'],issue,allow_removed=profile['joint'])
    forcings=_forecast_forcing(inputs['forecast'],issue,available,actions)
    if type(geometry) is not NativeGeometrySeries:
        raise ValueError('original immutable native forecast geometry required')
    packet=geometry.to_dict();descriptor=geometry.descriptor()
    if (_utc(descriptor['available_at'])>available or
            packet['request']['instants']!=[row.at.isoformat() for row in forcings]):
        raise ValueError('exact native geometry unavailable before forecast issue')
    reference=candidate['originals']['geometry'];raw,training=_read(Path(reference['path']),LIMITS['geometry'])
    if sha256(raw).hexdigest()!=reference['sha256']:
        raise ValueError('original fitted geometry changed')
    if (packet['native_runtime']!=training['native_runtime'] or
            descriptor['site']!=training['caches'][0]['source']['site'] or
            descriptor['timezone']!=training['request']['timezone']):
        raise ValueError('native forecast calculation differs from fitted geometry')
    model=profile['model'](tuple(candidate['fit']['coefficients']),geometry=geometry,expected_series_sha256=geometry.sha256)
    rolled=model.rollout(origin_at=issue,air_f=initial['air'],mass_f=initial['mass'],forcings=forcings,guard=check_budget)
    trajectory=[dict(at=row.at.isoformat(),air_f=state[0],mass_f=state[1]) for i,(row,state) in enumerate(zip(forcings,rolled.states),1) if i%12==0]
    check_budget()
    return dict(schema=NUMERIC_SCHEMA,status='provisional',generated_at=issue.isoformat(),artifact_sha256=candidate['artifact_sha256'],
        runtime_sha256=candidate['runtime_sha256'],model_rule=profile['rule'],geometry_series_sha256=geometry.sha256,
        horizon_hours=inputs['forecast']['horizon_hours'],initial=dict(air_f=initial['air'],mass_f=initial['mass'],outdoor_f=initial['outdoor']),
        origin_actions=actions,trajectory=trajectory,confidence='low',prediction_intervals=None,advice=[],graduated=False,automatic_actuation=False)


def _build_capture(candidate,inputs,*,geometry,runtime,expected_artifact_sha256,expected_geometry_sha256,issue,available,published,check_budget,monitoring_report,candidate_validator):
    issue,available,published=map(_instant,(issue,available,published));check_budget()
    candidate=candidate_validator(candidate,runtime,expected_artifact_sha256,issue,check_budget)
    if type(geometry) is not NativeGeometrySeries or geometry.sha256!=_sha(expected_geometry_sha256):
        raise ValueError('external native forecast geometry identity required')
    inputs=json.loads(_canonical(inputs))
    if not isinstance(inputs,dict) or set(inputs)!=INPUT_FIELDS:
        raise ValueError('complete original native sources required')
    binding=build_binding(inputs['origin_temperatures'],source_paths=inputs['native_source_paths'],issue_at=issue,check_budget=check_budget)
    output=_numeric(candidate,inputs,geometry,issue=issue,available=available,published=published,check_budget=check_budget)
    legacy._validate_report(monitoring_report,candidate['artifact_sha256'],available)
    value=json.loads(_canonical(dict(schema=CAPTURE_SCHEMA,issued_at=issue.isoformat(),inputs_available_at=available.isoformat(),published_at=published.isoformat(),
        candidate=candidate,inputs=inputs,native_origin_binding=binding,geometry=geometry.to_dict(),geometry_series_sha256=geometry.sha256,output=output,monitoring_report=monitoring_report)))
    value['capture_sha256']=digest(value,'capture_sha256');check_budget()
    if len(_canonical(value))>MAX_CAPTURE_BYTES:raise ValueError('bounded retained native forecast required')
    return value


def _validate_capture(value,*,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget,candidate_validator):
    # Callbacks and concurrent callers must never alter the validated snapshot.
    value=deepcopy(value);runtime=deepcopy(runtime)
    check_budget()
    if (not isinstance(value,dict) or set(value)!=CAPTURE_FIELDS or value['schema']!=CAPTURE_SCHEMA or
            value['capture_sha256']!=_sha(expected_capture_sha256) or digest(value,'capture_sha256')!=value['capture_sha256'] or
            len(_canonical(value))>MAX_CAPTURE_BYTES):
        raise ValueError('closed original native forecast identity required')
    issue,available,published=map(_instant,(value['issued_at'],value['inputs_available_at'],value['published_at']))
    candidate=candidate_validator(value['candidate'],runtime,expected_artifact_sha256,issue,check_budget)
    replay_binding(value['native_origin_binding'],value['inputs']['origin_temperatures'],issue_at=issue,check_budget=check_budget)
    packet=value['geometry']
    geometry=replay_series(_canonical(packet),request=packet['request'],expected_series_sha256=value['geometry_series_sha256'],expected_native_runtime=packet['native_runtime'])
    output=_numeric(candidate,value['inputs'],geometry,issue=issue,available=available,published=published,check_budget=check_budget)
    if _canonical(output)!=_canonical(value['output']):raise ValueError('original native forecast trajectory differs')
    legacy._validate_report(value['monitoring_report'],candidate['artifact_sha256'],available)
    check_budget();return deepcopy(value)



def build_capture(candidate,inputs,*,geometry,runtime,expected_artifact_sha256,expected_geometry_sha256,issue,available,published,check_budget=lambda:None,monitoring_report=None):
    return _build_capture(candidate,inputs,geometry=geometry,runtime=runtime,
        expected_artifact_sha256=expected_artifact_sha256,expected_geometry_sha256=expected_geometry_sha256,
        issue=issue,available=available,published=published,check_budget=check_budget,
        monitoring_report=monitoring_report,candidate_validator=_candidate)


def validate_capture(value,*,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget=lambda:None):
    return _validate_capture(value,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget,candidate_validator=_candidate)


def _serving_candidate(value,runtime,identity,issue,check,model):
    from native_model_serving_receipt import _require_model
    _require_model(model)
    model.verify_bindings(assessed_at=issue,guard=check)
    checked=model.candidate
    if (_canonical(value)!=_canonical(checked) or _canonical(runtime)!=_canonical(model.runtime) or
            identity!=checked['artifact_sha256'] or SOURCE not in checked['runtime']['native_source_manifest']):
        raise ValueError('original verified serving candidate differs')
    return checked


def build_serving_capture(model,inputs,*,geometry,expected_geometry_sha256,issue,available,published,check_budget=lambda:None,monitoring_report=None):
    from native_model_serving_receipt import _require_model
    _require_model(model)
    inputs=deepcopy(inputs)
    candidate=model.candidate
    def verified(value,runtime,identity,at,check):
        return _serving_candidate(value,runtime,identity,at,check,model)
    return _build_capture(candidate,inputs,geometry=geometry,runtime=model.runtime,
        expected_artifact_sha256=candidate['artifact_sha256'],expected_geometry_sha256=expected_geometry_sha256,
        issue=issue,available=available,published=published,check_budget=check_budget,
        monitoring_report=deepcopy(monitoring_report),candidate_validator=verified)


def validate_serving_capture(value,model,*,expected_capture_sha256,check_budget=lambda:None):
    from native_model_serving_receipt import _require_model
    _require_model(model)
    candidate=model.candidate
    def verified(value,runtime,identity,at,check):
        return _serving_candidate(value,runtime,identity,at,check,model)
    return _validate_capture(value,runtime=model.runtime,expected_artifact_sha256=candidate['artifact_sha256'],
        expected_capture_sha256=expected_capture_sha256,check_budget=check_budget,candidate_validator=verified)


def read_serving_capture(path,model,*,expected_capture_sha256,check_budget=lambda:None):
    from native_model_serving_receipt import _require_model
    _require_model(model)
    def nonfinite(_):raise ValueError('nonfinite native forecast JSON')
    try:value=json.loads(_owned_bytes(Path(path),MAX_CAPTURE_BYTES),object_pairs_hook=_object,parse_constant=nonfinite)
    except (UnicodeError,json.JSONDecodeError):raise ValueError('original native forecast JSON required') from None
    return validate_serving_capture(value,model,expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)


def publication(capture):
    # Formatting does not select or validate a model. Callers must first replay
    # the capture under its external identities, as with the original formatter.
    value=legacy.publication(capture);value.update(schema=PUBLICATION_SCHEMA,version=9)
    if fit_profile(capture['candidate']['fit'])['joint']:
        from native_joint_shade import REGIMES
        f=capture['candidate']['fit'];a=capture['output']['origin_actions']
        regime=REGIMES[(a['indoor_shade_closed'],a['outdoor_shade_present'])]
        support=f['regime_support'][regime]['status'];rating=f['shade_context']['nominal_shade_rejection_fraction']*100
        value['reasons'].append(f'{rating:g}% outdoor shade rating supplies provisional solar priors, not measured building attenuation.')
        value['reasons'].append(f'Current shade regime: {regime}; solar response evidence: {support}. Unshaded performance is unqualified.')
    if len(_canonical(value))>=16384:raise ValueError('bounded provisional publication required')
    return value


def persist(directory,value):
    return legacy.persist(directory,value,field='capture_sha256',suffix='.native-provisional-origin-v2.json',maximum=MAX_CAPTURE_BYTES)


def read_capture(path,*,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget=lambda:None):
    def nonfinite(_):raise ValueError('nonfinite native forecast JSON')
    try:value=json.loads(_owned_bytes(Path(path),MAX_CAPTURE_BYTES),object_pairs_hook=_object,parse_constant=nonfinite)
    except (UnicodeError,json.JSONDecodeError):raise ValueError('original native forecast JSON required') from None
    return validate_capture(value,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)


SERVING_RECEIPT_SOURCE_SHA256='0a62922ff3e0c7e79db7c92e1c519c42a8ff7d32f82baf8c82393e8d243d923a'
