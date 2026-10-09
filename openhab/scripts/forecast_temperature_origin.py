"""Opt-in exact temperature correction origins; no score or release authority.

HTTP completion alone is not publication evidence. A subsequent scorer must
bind actual persisted detail bytes and native qualified mature outcomes.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

from forecast_input_capture import _canonical, _directory, _instant, capture, read_as_of
from weather_temperature_config import _decode_policy_document, _read_policy_document

SCHEMA = 'earthship-temperature-correction-origin/v1'
RUNTIME_SCHEMA = 'earthship-temperature-correction-runtime/v1'
RUNTIME_ROOT = Path(__file__).resolve().parent
RUNTIME_PATHS = ('forecast_intel.py', 'forecast_ml_evidence.py',
                 'forecast_input_capture.py', 'forecast_temperature_origin.py',
                 'weather_temperature_config.py', 'weather_temperature_evidence.py')
FIELDS = {'schema', 'weather_reference', 'detail_state', 'hourly_model',
          'daily_adjustment', 'native_policy', 'runtime', 'inputs_available_at',
          'publication_started_at', 'publication_completed_at',
          'publication_item', 'delivery_verified'}
MAX_BYTES = 128 * 1024


def _clock():
    return datetime.now(timezone.utc)


def _read(path, maximum=MAX_BYTES, *, source=False):
    path = Path(path)
    before = path.lstat()
    allowed = (0, os.getuid()) if source else (os.getuid(),)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid not in allowed
            or before.st_mode & 0o022 or before.st_size > maximum
            or path.resolve(strict=True) != path
            or (not source and (stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1))):
        raise ValueError('owned bounded immutable source required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as handle:
        opened = os.fstat(handle.fileno())
        raw = handle.read(maximum + 1)
        after = os.fstat(handle.fileno())
    if (len(raw) != before.st_size or len(raw) > maximum
            or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
            or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) !=
               (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise ValueError('source changed during read')
    return raw


def _runtime_binding():
    manifest = {name: sha256(_read(RUNTIME_ROOT / name, 2_000_000, source=True)).hexdigest()
                for name in RUNTIME_PATHS}
    interpreter = Path(sys.executable).resolve(strict=True)
    record = {'schema': RUNTIME_SCHEMA, 'source_manifest': manifest,
              'python_version': '.'.join(map(str, sys.version_info[:3])),
              'interpreter_sha256': sha256(_read(interpreter, 64_000_000, source=True)).hexdigest()}
    record['code_revision'] = sha256(_canonical(record)).hexdigest()
    for name, expected in manifest.items():
        if sha256(_read(RUNTIME_ROOT / name, 2_000_000, source=True)).hexdigest() != expected:
            raise ValueError('runtime changed across capture')
    if sha256(_read(interpreter, 64_000_000, source=True)).hexdigest() != record['interpreter_sha256']:
        raise ValueError('interpreter changed across capture')
    return record


def _write(root, name, raw):
    root = _directory(root)
    target = root / name
    fd, temporary = tempfile.mkstemp(prefix='.temperature-origin-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            if _read(target, max(MAX_BYTES, len(raw))) != raw:
                raise ValueError('immutable origin collision')
        directory_fd = os.open(root, os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temporary)
    return target


def _policy(document):
    policies, epochs = _decode_policy_document(document, version=2)
    outdoor = policies.get('outdoor')
    if outdoor is None or outdoor.model != 'Fineoffset-WH65B' or outdoor.sensor_id != 206:
        raise ValueError('qualified native outdoor policy required')
    return policies, epochs


def _validate(record):
    if (not isinstance(record, dict) or set(record) != FIELDS or record['schema'] != SCHEMA
            or record['publication_item'] != 'Forecast_10Day_JSON'
            or record['delivery_verified'] is not False):
        raise ValueError('unverified exact temperature origin required')
    available, started, completed = (_instant(record[name]) for name in
        ('inputs_available_at', 'publication_started_at', 'publication_completed_at'))
    if not available <= started <= completed or (completed - started).total_seconds() > 180:
        raise ValueError('original publication clocks inconsistent')
    state = record['detail_state']
    if not isinstance(state, str) or not 0 < len(state.encode()) < 64 * 1024:
        raise ValueError('bounded exact detail bytes required')
    from weather_temperature_config import _object, _nonfinite
    detail = json.loads(state, object_pairs_hook=_object, parse_constant=_nonfinite)
    if (not isinstance(detail, dict) or set(detail) !=
            {'version', 'generatedAt', 'timezone', 'temperatureAdjustment', 'days'}
            or type(detail['version']) is not int or detail['version'] != 2
            or not _instant(detail['generatedAt']) <= started):
        raise ValueError('incompatible detail publication')
    from zoneinfo import ZoneInfo
    ZoneInfo(detail['timezone'])
    if not isinstance(detail['days'], list) or not 1 <= len(detail['days']) <= 10:
        raise ValueError('bounded published days required')
    _policy(record['native_policy'])
    runtime = record['runtime']
    if (not isinstance(runtime, dict) or set(runtime) !=
            {'schema', 'source_manifest', 'python_version', 'interpreter_sha256', 'code_revision'}
            or runtime['schema'] != RUNTIME_SCHEMA
            or not isinstance(runtime['source_manifest'], dict)
            or set(runtime['source_manifest']) != set(RUNTIME_PATHS)
            or not isinstance(runtime['python_version'], str)
            or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', runtime['python_version'])):
        raise ValueError('original correction runtime required')
    if any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v)
           for v in (*runtime['source_manifest'].values(), runtime['interpreter_sha256'], runtime['code_revision'])):
        raise ValueError('original runtime digest invalid')
    body = {k: v for k, v in runtime.items() if k != 'code_revision'}
    if sha256(_canonical(body)).hexdigest() != runtime['code_revision']:
        raise ValueError('runtime revision mismatch')
    # Preserve precisely the safe state used by the existing producer, including
    # learned per-hour biases omitted from the public detail2 support metadata.
    import forecast_intel as fi
    if (fi._hourly_model_snapshot(record['hourly_model']) != record['hourly_model']
            or fi.normalize_temperature_adjustment(record['daily_adjustment'], record['hourly_model'])
               != detail['temperatureAdjustment']):
        raise ValueError('original adjustment state differs from publication')
    if len(_canonical(record)) > MAX_BYTES:
        raise ValueError('origin exceeds decoded bound')
    return record


class TemperatureOriginObserver:
    def __init__(self, directory, native_policy_path):
        self.root = _directory(Path(directory))
        self.policy_path = str(native_policy_path)

    def prepare(self, *, snapshot, payloads, hourly_model, temperature_adjustment):
        import forecast_intel as fi
        policy = _read_policy_document(self.policy_path); _policy(policy)
        runtime = _runtime_binding()
        weather_root = self.root / 'weather-inputs'
        weather_root.mkdir(mode=0o700, exist_ok=True); _directory(weather_root)
        reference = capture(weather_root, snapshot=deepcopy(snapshot),
                            request_url=fi.OM_URL, captured_at=_clock())
        sources = self.root / 'runtime-sources'
        sources.mkdir(mode=0o700, exist_ok=True); _directory(sources)
        version = sources / runtime['code_revision']
        version.mkdir(mode=0o700, exist_ok=True); _directory(version)
        for name, expected in runtime['source_manifest'].items():
            raw = _read(RUNTIME_ROOT / name, 2_000_000, source=True)
            if sha256(raw).hexdigest() != expected:
                raise ValueError('runtime changed before source retention')
            _write(version, name, raw)
        token = {'schema': SCHEMA, 'weather_reference': reference,
                 'detail_state': fi.serialize_detail(deepcopy(payloads[2])),
                 'hourly_model': fi._hourly_model_snapshot(deepcopy(hourly_model)),
                 'daily_adjustment': deepcopy(payloads[2]['temperatureAdjustment']),
                 'native_policy': policy, 'runtime': runtime,
                 'inputs_available_at': _clock().isoformat(),
                 'publication_item': 'Forecast_10Day_JSON', 'delivery_verified': False}
        return token

    def complete(self, token, *, publication_started_at, publication_completed_at):
        record = deepcopy(token)
        if (_runtime_binding() != record['runtime']
                or _read_policy_document(self.policy_path) != record['native_policy']):
            raise ValueError('original code or sensor policy changed')
        record.update(publication_started_at=publication_started_at.isoformat(),
                      publication_completed_at=publication_completed_at.isoformat())
        _validate(record)
        read_as_of(self.root / 'weather-inputs', record['weather_reference'],
                   origin=_instant(record['inputs_available_at']))
        raw = _canonical(record)
        return _write(self.root, sha256(raw).hexdigest() + '.temperature-origin-v1.json', raw)


def read_origin(directory, path):
    root = _directory(Path(directory)); path = Path(path)
    if path.parent != root or not re.fullmatch(r'[0-9a-f]{64}\.temperature-origin-v1\.json', path.name):
        raise ValueError('original capture path invalid')
    raw = _read(path)
    if sha256(raw).hexdigest() != path.name.split('.')[0]:
        raise ValueError('original capture digest mismatch')
    from weather_temperature_config import _object, _nonfinite
    record = json.loads(raw, object_pairs_hook=_object, parse_constant=_nonfinite)
    _validate(record)
    if _canonical(record) != raw:
        raise ValueError('noncanonical original capture')
    sources = _directory(root / 'runtime-sources')
    version = _directory(sources / record['runtime']['code_revision'])
    for name, expected in record['runtime']['source_manifest'].items():
        if sha256(_read(version / name, 2_000_000)).hexdigest() != expected:
            raise ValueError('retained original runtime source mismatch')
    weather = read_as_of(root / 'weather-inputs', record['weather_reference'],
                        origin=_instant(record['inputs_available_at']))
    return record, weather


def observer_from_environment(environ=None):
    env = os.environ if environ is None else environ
    directory = env.get('FORECAST_TEMPERATURE_ORIGIN_DIR')
    policy = env.get('FORECAST_TEMPERATURE_ORIGIN_POLICY')
    if directory is None and policy is None:
        return None
    if not directory or not policy or not Path(directory).is_absolute() or not Path(policy).is_absolute():
        raise ValueError('explicit private origin directory and native policy required')
    return TemperatureOriginObserver(directory, policy)
