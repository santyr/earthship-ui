"""Explicit, bounded opt-in configuration for the weather evidence extension."""
import json
import os
import stat

from weather_temperature_evidence import TemperaturePolicy


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate policy key')
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError('nonfinite policy constant')


def load_temperature_policies(path):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError('absolute policy path required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid() or metadata.st_mode & 0o022:
            raise ValueError('owned non-writable-by-others regular policy file required')
        if not 1 <= metadata.st_size <= 8192:
            raise ValueError('policy file size outside bounds')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            contents = stream.read(8193)
        if len(contents) > 8192:
            raise ValueError('policy file exceeds bounds')
    finally:
        os.close(fd)
    document = json.loads(contents, object_pairs_hook=_object, parse_constant=_nonfinite)
    if not isinstance(document, dict) or set(document) != {'version', 'streams'} or type(document['version']) is not int or document['version'] != 1:
        raise ValueError('unsupported policy schema')
    streams = document['streams']
    if not isinstance(streams, dict) or not 1 <= len(streams) <= 3:
        raise ValueError('one to three explicit streams required')
    fields = {'model', 'sensor_id', 'minimum_f', 'maximum_f', 'validity_seconds'}
    if any(not isinstance(policy, dict) or set(policy) != fields for policy in streams.values()):
        raise ValueError('closed explicit stream policy required')
    return {name: TemperaturePolicy(**policy) for name, policy in streams.items()}


def configure_temperature_receiver(app, environ=None):
    """Bad evidence configuration must not take down the legacy receiver."""
    env = os.environ if environ is None else environ
    if env.get('WEATHER_TEMP_EVIDENCE_ENABLE') != '1':
        return None
    try:
        from weather_temperature_receiver import install_temperature_evidence
        policies = load_temperature_policies(env.get('WEATHER_TEMP_EVIDENCE_POLICY'))
        return install_temperature_evidence(app, enabled=True, policies=policies)
    except Exception:
        app.logger.warning('temperature evidence configuration unavailable; legacy receiver retained')
        return None
