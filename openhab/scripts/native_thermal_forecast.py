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
CONDITIONED_CAPTURE_SCHEMA='earthship-provisional-thermal-origin/v3'
SEGMENTED_CAPTURE_SCHEMA='earthship-provisional-thermal-origin/v4'
SEGMENTED_CONDITIONED_CAPTURE_SCHEMA='earthship-provisional-thermal-origin/v5'
SEGMENTED_CAPTURE_SCHEMAS=(SEGMENTED_CAPTURE_SCHEMA,SEGMENTED_CONDITIONED_CAPTURE_SCHEMA)
CONDITIONED_CAPTURE_SCHEMAS=(CONDITIONED_CAPTURE_SCHEMA,SEGMENTED_CONDITIONED_CAPTURE_SCHEMA)
NUMERIC_SCHEMA='earthship-provisional-thermal-forecast/v2'
PUBLICATION_SCHEMA='earthship-provisional-thermal-publication/v2'
INPUT_FIELDS=legacy.INPUT_FIELDS
CAPTURE_FIELDS=legacy.CAPTURE_FIELDS|{'geometry','geometry_series_sha256'}
MAX_CAPTURE_BYTES=6*1024*1024
SOURCE='openhab/scripts/native_thermal_forecast.py'

def capture_fields(value):
    if value.get('schema') in (CAPTURE_SCHEMA,SEGMENTED_CAPTURE_SCHEMA):return CAPTURE_FIELDS
    if value.get('schema') in CONDITIONED_CAPTURE_SCHEMAS:return CAPTURE_FIELDS|{'weather_conditioning'}
    raise ValueError('explicit original native forecast version required')


def capture_suffix(value):
    capture_fields(value)
    return {CAPTURE_SCHEMA:'.native-provisional-origin-v2.json',
        CONDITIONED_CAPTURE_SCHEMA:'.native-provisional-origin-v2.json',
        SEGMENTED_CAPTURE_SCHEMA:'.native-provisional-origin-v4.json',
        SEGMENTED_CONDITIONED_CAPTURE_SCHEMA:'.native-provisional-origin-v5.json'}[value['schema']]


SEGMENTED_BINDING_SOURCE_SHA256='77bcd69a3a5fcb6720db697c12064b8a3a159b0660d60dd8e9aebc5af5946d9a'
SEGMENTED_CODEC_SOURCE_SHA256='86106647f7f826f70a19d5fcb7ff51979f4c8e99b913be61ad7acff821ff9215'


def _segmented_helpers(runtime=None):
    """Seal optional operational helpers without changing the fitted closure."""
    import importlib
    from types import FunctionType
    from thermal_model.origin_capture import _source_bytes
    root=Path(__file__).absolute().parent;loaded=[]
    declarations=(
        ('weather_temperature_segmented_binding',SEGMENTED_BINDING_SOURCE_SHA256,
            ('build_segmented_native_origin_binding','replay_segmented_native_origin_binding','segmented_native_origin_files')),
        ('weather_temperature_source_segments',SEGMENTED_CODEC_SOURCE_SHA256,
            ('fetch_shared_temperature_source','write_shared_temperature_source','read_shared_temperature_source',
             'replay_shared_temperature_source','shared_temperature_source_files')))
    for name,pin,names in declarations:
        path=root/(name+'.py')
        if sha256(_source_bytes(path,maximum=262144)).hexdigest()!=pin:
            raise ValueError('shared native operational helper source changed')
    if runtime is not None and runtime['native_source_manifest'].get(SOURCE)!=sha256(_source_bytes(root/'native_thermal_forecast.py',maximum=262144)).hexdigest():
        raise ValueError('explicit successor forecast runtime required for shared native sources')
    for name,pin,names in declarations:
        path=root/(name+'.py')
        module=importlib.import_module(name)
        if getattr(module,'__file__',None)!=str(path):raise ValueError('shared native helper loaded from another runtime')
        for selected in names:
            function=getattr(module,selected,None)
            if (type(function) is not FunctionType or function.__globals__ is not module.__dict__ or
                    Path(function.__code__.co_filename)!=path):
                raise ValueError('shared native helper loaded implementation differs')
        loaded.append(module)
    return tuple(loaded)


def origin_source_files(value,*,check_budget=lambda:None):
    """Complete original inventory, with fresh segmented replay when selected."""
    if value.get('schema') in SEGMENTED_CAPTURE_SCHEMAS:
        binding,_=_segmented_helpers(value['candidate']['runtime'])
        return binding.segmented_native_origin_files(value['native_origin_binding'],check_budget=check_budget)
    return tuple(dict.fromkeys(Path(name) for name in value['native_origin_binding'].get('query_sources',{}).values()))


def _source_fingerprints(paths,*,check_budget):
    from thermal_model.native_operational_io import _fingerprint
    from weather_temperature_sources import MAX_CONTAINER_BYTES
    from thermal_model.forcing_capture import _private_directory
    paths=tuple(map(Path,paths));identities={path:_fingerprint(path) for path in paths};saved={}
    for directory in {path.parent for path in paths}:_private_directory(directory)
    for path in paths:
        check_budget();before=identities[path]
        if _fingerprint(path)!=before:raise ValueError('native origin source replaced before observation')
        raw=_owned_bytes(path,MAX_CONTAINER_BYTES)
        if _fingerprint(path)!=before:raise ValueError('native origin source changed during observation')
        saved[path]=(before,sha256(raw).hexdigest())
    check_budget()
    # Callbacks cannot change an earlier child after its bytes were observed.
    for directory in {path.parent for path in paths}:_private_directory(directory)
    if any(_fingerprint(path)!=record[0] for path,record in saved.items()):
        raise ValueError('native origin source custody changed before return')
    return saved


def origin_source_snapshot(value,*,check_budget=lambda:None):
    return _source_fingerprints(origin_source_files(value,check_budget=check_budget),check_budget=check_budget)


def verify_origin_source_snapshot(snapshot,*,check_budget=lambda:None):
    if _source_fingerprints(tuple(snapshot),check_budget=check_budget)!=snapshot:
        raise ValueError('original native manifest or child changed after replay')


def digest(value,field):return sha256(_canonical({k:v for k,v in value.items() if k!=field})).hexdigest()


def _candidate(value,runtime,identity,issue,check):
    checked=validate_native_candidate(value,assessed_at=issue,runtime=runtime,expected_artifact_sha256=identity,guard=check)
    if SOURCE not in checked['runtime']['native_source_manifest']:
        raise ValueError('native forecast implementation must be runtime-bound')
    return checked


def _numeric(candidate,inputs,geometry,*,issue,available,published,check_budget,weather_conditioning=None):
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
    if weather_conditioning is not None:
        from household.thermal_weather_conditioning import validate_context,apply_conditioning
        validate_context(weather_conditioning,issue=issue,available=available,forecast=inputs['forecast'],sensor_epoch=phases['outdoor'])
        if _canonical(weather_conditioning['native_runtime'])!=_canonical(packet['native_runtime']) or _canonical(weather_conditioning['site'])!=_canonical(descriptor['site']):raise ValueError('thermal conditioning native runtime or site differs')
        forcings=apply_conditioning(forcings,weather_conditioning,issue=issue,available=available,initial_outdoor_f=initial['outdoor'])
    rolled=model.rollout(origin_at=issue,air_f=initial['air'],mass_f=initial['mass'],forcings=forcings,guard=check_budget)
    trajectory=[dict(at=row.at.isoformat(),air_f=state[0],mass_f=state[1]) for i,(row,state) in enumerate(zip(forcings,rolled.states),1) if i%12==0]
    check_budget()
    return dict(schema=NUMERIC_SCHEMA,status='provisional',generated_at=issue.isoformat(),artifact_sha256=candidate['artifact_sha256'],
        runtime_sha256=candidate['runtime_sha256'],model_rule=profile['rule'],geometry_series_sha256=geometry.sha256,
        horizon_hours=inputs['forecast']['horizon_hours'],initial=dict(air_f=initial['air'],mass_f=initial['mass'],outdoor_f=initial['outdoor']),
        origin_actions=actions,trajectory=trajectory,confidence='low',prediction_intervals=None,advice=[],graduated=False,automatic_actuation=False)


def _build_capture(candidate,inputs,*,geometry,runtime,expected_artifact_sha256,expected_geometry_sha256,issue,available,published,check_budget,monitoring_report,candidate_validator,weather_conditioning=None,source_profile='compressed-v2'):
    issue,available,published=map(_instant,(issue,available,published));check_budget()
    candidate=candidate_validator(candidate,runtime,expected_artifact_sha256,issue,check_budget)
    if type(geometry) is not NativeGeometrySeries or geometry.sha256!=_sha(expected_geometry_sha256):
        raise ValueError('external native forecast geometry identity required')
    inputs=json.loads(_canonical(inputs))
    if not isinstance(inputs,dict) or set(inputs)!=INPUT_FIELDS:
        raise ValueError('complete original native sources required')
    if source_profile not in ('compressed-v2','segmented-v1'):raise ValueError('explicit supported native source profile required')
    segmented=source_profile=='segmented-v1'
    originals=None
    if segmented:
        builder=_segmented_helpers(candidate['runtime'])[0].build_segmented_native_origin_binding
        def observe(files):
            nonlocal originals
            originals=_source_fingerprints(files,check_budget=check_budget)
        binding=builder(inputs['origin_temperatures'],source_paths=inputs['native_source_paths'],issue_at=issue,
            check_budget=check_budget,observe_files=observe)
    else:binding=build_binding(inputs['origin_temperatures'],source_paths=inputs['native_source_paths'],issue_at=issue,check_budget=check_budget)
    if weather_conditioning is not None:
        weather_conditioning=json.loads(_canonical(weather_conditioning))
        from thermal_weather_source import verify_bindings
        verify_bindings(weather_conditioning,guard=check_budget)
    output=_numeric(candidate,inputs,geometry,issue=issue,available=available,published=published,check_budget=check_budget,weather_conditioning=weather_conditioning)
    legacy._validate_report(monitoring_report,candidate['artifact_sha256'],available)
    value=json.loads(_canonical(dict(schema=SEGMENTED_CAPTURE_SCHEMA if segmented else CAPTURE_SCHEMA,issued_at=issue.isoformat(),inputs_available_at=available.isoformat(),published_at=published.isoformat(),
        candidate=candidate,inputs=inputs,native_origin_binding=binding,geometry=geometry.to_dict(),geometry_series_sha256=geometry.sha256,output=output,monitoring_report=monitoring_report)))
    if weather_conditioning is not None:
        value.update(schema=SEGMENTED_CONDITIONED_CAPTURE_SCHEMA if segmented else CONDITIONED_CAPTURE_SCHEMA,weather_conditioning=weather_conditioning)
        verify_bindings(weather_conditioning,guard=check_budget)
    value['capture_sha256']=digest(value,'capture_sha256');check_budget()
    if len(_canonical(value))>MAX_CAPTURE_BYTES:raise ValueError('bounded retained native forecast required')
    if originals is not None:
        verify_origin_source_snapshot(originals,check_budget=check_budget);_segmented_helpers(candidate['runtime'])
    return value


def _validate_capture(value,*,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget,candidate_validator):
    # Callbacks and concurrent callers must never alter the validated snapshot.
    value=deepcopy(value);runtime=deepcopy(runtime)
    check_budget()
    if (not isinstance(value,dict) or set(value)!=capture_fields(value) or
            value['capture_sha256']!=_sha(expected_capture_sha256) or digest(value,'capture_sha256')!=value['capture_sha256'] or
            len(_canonical(value))>MAX_CAPTURE_BYTES):
        raise ValueError('closed original native forecast identity required')
    issue,available,published=map(_instant,(value['issued_at'],value['inputs_available_at'],value['published_at']))
    candidate=candidate_validator(value['candidate'],runtime,expected_artifact_sha256,issue,check_budget)
    segmented=value['schema'] in SEGMENTED_CAPTURE_SCHEMAS
    originals=origin_source_snapshot(value,check_budget=check_budget) if segmented else None
    replayer=_segmented_helpers(candidate['runtime'])[0].replay_segmented_native_origin_binding if segmented else replay_binding
    replayer(value['native_origin_binding'],value['inputs']['origin_temperatures'],issue_at=issue,check_budget=check_budget)
    if segmented and (not isinstance(value['inputs'],dict) or set(value['inputs'])!=INPUT_FIELDS or
            value['inputs']['native_source_paths']!=value['native_origin_binding']['query_sources']):
        raise ValueError('captured native source paths differ from original shared binding')
    packet=value['geometry']
    geometry=replay_series(_canonical(packet),request=packet['request'],expected_series_sha256=value['geometry_series_sha256'],expected_native_runtime=packet['native_runtime'])
    weather_conditioning=value.get('weather_conditioning')
    if value['schema'] in CONDITIONED_CAPTURE_SCHEMAS and not isinstance(weather_conditioning,dict):raise ValueError('conditioned native capture requires original proof')
    if weather_conditioning is not None:
        from thermal_weather_source import verify_bindings
        verify_bindings(weather_conditioning,guard=check_budget)
    output=_numeric(candidate,value['inputs'],geometry,issue=issue,available=available,published=published,check_budget=check_budget,weather_conditioning=weather_conditioning)
    if _canonical(output)!=_canonical(value['output']):raise ValueError('original native forecast trajectory differs')
    legacy._validate_report(value['monitoring_report'],candidate['artifact_sha256'],available)
    check_budget()
    if originals is not None:
        verify_origin_source_snapshot(originals,check_budget=check_budget);_segmented_helpers(candidate['runtime'])
    return deepcopy(value)



def build_capture(candidate,inputs,*,geometry,runtime,expected_artifact_sha256,expected_geometry_sha256,issue,available,published,check_budget=lambda:None,monitoring_report=None,weather_conditioning=None,source_profile='compressed-v2'):
    return _build_capture(candidate,inputs,geometry=geometry,runtime=runtime,
        expected_artifact_sha256=expected_artifact_sha256,expected_geometry_sha256=expected_geometry_sha256,
        issue=issue,available=available,published=published,check_budget=check_budget,
        monitoring_report=monitoring_report,candidate_validator=_candidate,weather_conditioning=weather_conditioning,source_profile=source_profile)


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


def build_serving_capture(model,inputs,*,geometry,expected_geometry_sha256,issue,available,published,check_budget=lambda:None,monitoring_report=None,weather_conditioning=None,source_profile='compressed-v2'):
    from native_model_serving_receipt import _require_model
    _require_model(model)
    inputs=deepcopy(inputs)
    candidate=model.candidate
    def verified(value,runtime,identity,at,check):
        return _serving_candidate(value,runtime,identity,at,check,model)
    return _build_capture(candidate,inputs,geometry=geometry,runtime=model.runtime,
        expected_artifact_sha256=candidate['artifact_sha256'],expected_geometry_sha256=expected_geometry_sha256,
        issue=issue,available=available,published=published,check_budget=check_budget,
        monitoring_report=deepcopy(monitoring_report),candidate_validator=verified,weather_conditioning=weather_conditioning,source_profile=source_profile)


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
    if value.get('schema') in SEGMENTED_CAPTURE_SCHEMAS and Path(path).name!=_sha(expected_capture_sha256)+capture_suffix(value):
        raise ValueError('named original segmented capture required')
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
    return legacy.persist(directory,value,field='capture_sha256',suffix=capture_suffix(value),maximum=MAX_CAPTURE_BYTES)


def read_capture(path,*,runtime,expected_artifact_sha256,expected_capture_sha256,check_budget=lambda:None):
    def nonfinite(_):raise ValueError('nonfinite native forecast JSON')
    try:value=json.loads(_owned_bytes(Path(path),MAX_CAPTURE_BYTES),object_pairs_hook=_object,parse_constant=nonfinite)
    except (UnicodeError,json.JSONDecodeError):raise ValueError('original native forecast JSON required') from None
    if value.get('schema') in SEGMENTED_CAPTURE_SCHEMAS and Path(path).name!=_sha(expected_capture_sha256)+capture_suffix(value):
        raise ValueError('named original segmented capture required')
    return validate_capture(value,runtime=runtime,expected_artifact_sha256=expected_artifact_sha256,expected_capture_sha256=expected_capture_sha256,check_budget=check_budget)


SERVING_RECEIPT_SOURCE_SHA256='11121a94a4501c7af520b9df54ec879a3c75edadc87a0d15afd279bf83bbf58e'
