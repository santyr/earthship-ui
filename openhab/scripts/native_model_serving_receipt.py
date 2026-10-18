"""Owned numerical admission evidence; no model selection or physical authority."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import re
import json
import math

from thermal_model.forcing_capture import _canonical, _private_directory
from thermal_model.graduation_policy import _utc, _sha
from thermal_model.origin_capture import _source_bytes
from thermal_model.runtime_bundle import _owned_bytes
from thermal_model.installed_shade_artifact import _persist
from thermal_model.replay_budget import capture_source_reads
import native_thermal_artifact as artifacts

SCHEMA = 'earthship-native-model-verification-receipt/v1'
MAX_BYTES = 131072
SUFFIX = '.native-model-verification-receipt-v1.json'


_SEAL = object()
SOURCE = 'openhab/scripts/native_model_serving_receipt.py'
FIELDS = {'schema', 'verified_at', 'validator_profile', 'candidate_path',
          'candidate_file_sha256', 'artifact_sha256', 'runtime', 'runtime_sha256',
          'originals', 'helper', 'fit_sha256', 'sensor_epochs', 'model_rule',
          'release_authorized', 'receipt_sha256'}


class OwnedServingSelection:
    """Issued only by the externally pinned owned stage reader."""
    __slots__ = ('_encoded', '_seal')

    def __init__(self, *args, **kwargs):
        raise TypeError('read the externally pinned owned serving selection')

    def __setattr__(self, name, value):
        raise AttributeError('owned serving selection is immutable')


class ServingModel:
    """A verified numerical admission; caller dictionaries cannot mint one."""
    __slots__ = ('_encoded', '_selection', '_seal')

    def __init__(self, *args, **kwargs):
        raise TypeError('read a verified serving model from an owned selection')

    def __setattr__(self, name, value):
        raise AttributeError('serving model is immutable')

    @property
    def candidate(self):
        _require_model(self)
        return json.loads(self._encoded)['candidate']

    @property
    def runtime(self):
        return self.candidate['runtime']

    def verify_bindings(self, *, assessed_at, guard):
        _require_model(self)
        fresh = read_serving_model(self._selection, assessed_at=assessed_at, guard=guard)
        if fresh._encoded != self._encoded:
            raise ValueError('frozen serving model bindings changed')


def _require_model(value):
    if type(value) is not ServingModel or getattr(value, '_seal', None) is not _SEAL:
        raise ValueError('verified opaque serving model required')


def _mint(kind, record, *, selection=None):
    value = object.__new__(kind)
    object.__setattr__(value, '_encoded', _canonical(record))
    object.__setattr__(value, '_seal', _SEAL)
    if kind is ServingModel:
        object.__setattr__(value, '_selection', selection)
    return value


def _helper_binding(runtime, guard):
    path = Path(__file__)
    if not path.is_absolute() or path.resolve() != path or Path(_helper_binding.__code__.co_filename) != path:
        raise ValueError('loaded serving helper location differs')
    guard()
    identity = sha256(_source_bytes(path, maximum=262144)).hexdigest()
    for name in sorted(artifacts.OPTIONAL_SOURCES):
        guard()
        if name not in runtime['native_source_manifest']:
            raise ValueError('complete optional serving closure required')
        raw = _source_bytes(artifacts.ROOT / name, maximum=2000000)
        pin = re.search(rb"^SERVING_RECEIPT_SOURCE_SHA256='([0-9a-f]{64})'$", raw, re.M)
        if pin is None or pin.group(1).decode() != identity:
            raise ValueError('serving helper literal source pin differs')
    return dict(source=SOURCE, sha256=identity)


def _bindings(candidate_path, runtime, guard):
    guard()
    raw, candidate = artifacts._read(candidate_path, MAX_BYTES)
    refs = candidate.get('originals') if isinstance(candidate, dict) else None
    if not isinstance(refs, dict) or set(refs) != set(artifacts.LIMITS):
        raise ValueError('complete original model dependencies required')
    originals = {}
    for role, ref in refs.items():
        guard()
        if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
            raise ValueError('closed original model dependency required')
        path = Path(ref['path'])
        if not path.is_absolute() or path.resolve() != path:
            raise ValueError('resolved original model path required')
        _private_directory(path.parent)
        identity = sha256(_owned_bytes(path, artifacts.LIMITS[role])).hexdigest()
        if identity != _sha(ref['sha256']):
            raise ValueError('original model dependency bytes changed')
        originals[role] = dict(path=str(path), sha256=identity, maximum_bytes=artifacts.LIMITS[role])
    actual = artifacts.current_native_runtime(guard=guard)
    if _canonical(actual) != _canonical(artifacts.validate_native_runtime(runtime)):
        raise ValueError('model admission executing runtime differs')
    helper = _helper_binding(actual, guard)
    guard()
    return raw, candidate, originals, actual, helper


def admit_model(candidate_path, *, runtime, expected_artifact_sha256, directory, clock, guard):
    """Fully replay once, then retain evidence only while all exact bytes agree."""
    candidate_path = Path(candidate_path)
    root = _private_directory(Path(directory))
    runtime = deepcopy(runtime)
    identity = _sha(expected_artifact_sha256)
    started = _utc(clock())
    with capture_source_reads() as sources:
        before = _bindings(candidate_path, runtime, guard)
        checked = artifacts.read_native_candidate(candidate_path, assessed_at=started,
            runtime=runtime, expected_artifact_sha256=identity, guard=guard)
        after = _bindings(candidate_path, runtime, guard)
        if before != after or _canonical(checked) != _canonical(after[1]):
            raise ValueError('model originals or runtime changed during admission')
        finished = _utc(clock())
        if not started <= finished or not _utc(checked['created_at']) <= finished:
            raise ValueError('model admission completion clock differs')
        record = dict(schema=SCHEMA, verified_at=finished.isoformat(),
            validator_profile=dict(rule='earthship-native-candidate-full-replay/v1',
                source_sha256=runtime['native_source_manifest']['openhab/scripts/native_thermal_artifact.py']),
            candidate_path=str(candidate_path), candidate_file_sha256=sha256(after[0]).hexdigest(),
            artifact_sha256=identity, runtime=runtime, runtime_sha256=checked['runtime_sha256'],
            originals=after[2], helper=after[4], fit_sha256=sha256(_canonical(checked['fit'])).hexdigest(),
            sensor_epochs=deepcopy(checked['fit']['sensor_epochs']), model_rule=checked['fit']['model_rule'],
            release_authorized=False)
        record['receipt_sha256'] = artifacts.digest(record, 'receipt_sha256')
        if len(_canonical(record)) > MAX_BYTES:
            raise ValueError('bounded model admission receipt required')
        sources.verify(); guard()
        target = _persist(root, record, record['receipt_sha256'], SUFFIX)
        raw, restored = artifacts._read(target, MAX_BYTES)
        if raw != _canonical(record) or restored != record:
            raise ValueError('model admission receipt readback differs')
        guard(); sources.verify()
        return target


def load_serving_selection(stage, *, expected_deployment_sha256, assessed_at, guard):
    """The expected stage pin comes from the owned effective command selection."""
    from household_cycle_deploy import verify_stage
    stage = _private_directory(Path(stage))
    pin = _sha(expected_deployment_sha256)
    guard()
    record = verify_stage(stage, expected_deployment_sha256=pin)
    if record['schema'] != 'earthship-household-cycle-deployment/v3':
        raise ValueError('explicit receipt-serving stage required')
    _, cycle = artifacts._read(stage / 'cycle.json', 8192)
    _, settings = artifacts._read(cycle['forecast_config'], 8192)
    binding = record['model_verification']
    if (settings['model_receipt_path'] != binding['receipt']['path'] or
            settings['model_receipt_sha256'] != binding['receipt']['sha256']):
        raise ValueError('owned selection receipt differs from configuration')
    raw, candidate = artifacts._read(settings['candidate_path'], MAX_BYTES)
    helper = _helper_binding(candidate['runtime'], guard)
    if (binding['helper']['path'] != str(stage / 'sources' / SOURCE) or
            binding['helper']['sha256'] != helper['sha256']):
        raise ValueError('owned stage executing helper differs')
    guard()
    if sha256(_owned_bytes(stage / 'deployment.json', MAX_BYTES)).hexdigest() != pin:
        raise ValueError('owned serving stage changed during selection read')
    return _mint(OwnedServingSelection, dict(stage=str(stage), deployment_sha256=pin,
        candidate_path=settings['candidate_path'], candidate_file_sha256=sha256(raw).hexdigest(),
        artifact_sha256=record['artifact_sha256'], runtime_sha256=record['runtime_sha256'],
        runtime=candidate['runtime'], receipt=binding['receipt'], helper=helper))


def _check_receipt(receipt, candidate, selected, originals, runtime, helper, assessed_at):
    if (not isinstance(receipt, dict) or set(receipt) != FIELDS or receipt['schema'] != SCHEMA or
            artifacts.digest(receipt, 'receipt_sha256') != _sha(receipt['receipt_sha256']) or
            receipt['release_authorized'] is not False):
        raise ValueError('closed original model verification receipt required')
    if (set(candidate) != artifacts.FIELDS or candidate['schema'] not in artifacts.SCHEMAS or
            artifacts.digest(candidate, 'artifact_sha256') != selected['artifact_sha256'] or
            candidate['artifact_sha256'] != selected['artifact_sha256'] or
            candidate['runtime_sha256'] != selected['runtime_sha256'] or
            artifacts.digest(runtime) != selected['runtime_sha256'] or
            _canonical(candidate['runtime']) != _canonical(runtime)):
        raise ValueError('receipt-bound candidate identity differs')
    for field in ('candidate_path', 'candidate_file_sha256', 'artifact_sha256', 'runtime_sha256'):
        if receipt[field] != selected[field]:
            raise ValueError('original verified candidate binding differs')
    if (receipt['runtime'] != runtime or receipt['originals'] != originals or
            receipt['helper'] != helper or helper != selected['helper'] or
            receipt['validator_profile'] != dict(rule='earthship-native-candidate-full-replay/v1',
                source_sha256=runtime['native_source_manifest']['openhab/scripts/native_thermal_artifact.py'])):
        raise ValueError('original verified model dependencies differ')
    fit = candidate['fit']
    from native_thermal_inputs import solar_feature_contract
    profile=artifacts.fit_profile(fit)
    if (set(fit) != profile['fields'] or
            fit['model_rule'] != profile['rule'] or fit['solar_feature'] != profile['solar_feature']() or
            fit['graduated'] is not False or fit['release_authorized'] is not False or
            fit['as_issued_forecast'] is not False or receipt['model_rule'] != profile['rule'] or
            receipt['sensor_epochs'] != fit['sensor_epochs'] or
            receipt['fit_sha256'] != sha256(_canonical(fit)).hexdigest()):
        raise ValueError('original verified fit contract differs')
    for key in ('coefficients', 'initial_coefficients'):
        values = fit[key]
        if (not isinstance(values, list) or len(values) != profile['count'] or
                any(type(x) not in (int, float) or not math.isfinite(x) or not low <= x <= high
                    for x, low, high in zip(values, profile['lower'], profile['upper']))):
            raise ValueError('verified physical coefficients required')
    if not _utc(candidate['created_at']) <= _utc(receipt['verified_at']) <= _utc(assessed_at):
        raise ValueError('verified model admission chronology differs')


def read_serving_model(selection, *, assessed_at, guard):
    """Freshly hash every dependency; reuse only the earlier numerical replay."""
    if type(selection) is not OwnedServingSelection or getattr(selection, '_seal', None) is not _SEAL:
        raise ValueError('owned externally pinned serving selection required')
    selected = json.loads(selection._encoded)
    with capture_source_reads() as sources:
        fresh = load_serving_selection(selected['stage'], expected_deployment_sha256=selected['deployment_sha256'],
            assessed_at=assessed_at, guard=guard)
        if fresh._encoded != selection._encoded:
            raise ValueError('owned serving selection changed')
        receipt_raw, receipt = artifacts._read(selected['receipt']['path'], MAX_BYTES)
        if sha256(receipt_raw).hexdigest() != selected['receipt']['sha256']:
            raise ValueError('externally pinned receipt bytes differ')
        raw, candidate, originals, runtime, helper = _bindings(Path(selected['candidate_path']), selected['runtime'], guard)
        if sha256(raw).hexdigest() != selected['candidate_file_sha256']:
            raise ValueError('verified candidate exact bytes differ')
        _check_receipt(receipt, candidate, selected, originals, runtime, helper, assessed_at)
        guard(); sources.verify()
        if sha256(_owned_bytes(Path(selected['stage']) / 'deployment.json', MAX_BYTES)).hexdigest() != selected['deployment_sha256']:
            raise ValueError('owned serving stage changed during model read')
        return _mint(ServingModel, dict(candidate=candidate, receipt=receipt), selection=selection)
