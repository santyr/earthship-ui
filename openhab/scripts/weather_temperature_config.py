"""Explicit, bounded opt-in configuration for the weather evidence extension."""
import json
import os
import stat

from weather_temperature_evidence import TemperaturePolicy, sensor_epoch_id


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate policy key')
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError('nonfinite policy constant')


def _read_policy_document(path):
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
    return document


def _decode_policy_document(document, *, version):
    if (not isinstance(document, dict) or set(document) != {'version', 'streams'} or
            type(document['version']) is not int or document['version'] != version):
        raise ValueError('unsupported policy schema')
    streams = document['streams']
    if not isinstance(streams, dict) or not 1 <= len(streams) <= 4:
        raise ValueError('one to four explicit streams required')
    fields = {'model', 'sensor_id', 'minimum_f', 'maximum_f', 'validity_seconds'}
    expected = fields | ({'sensor_epoch'} if version == 2 else set())
    if any(not isinstance(policy, dict) or set(policy) != expected for policy in streams.values()):
        raise ValueError('closed explicit stream policy required')
    policies = {name: TemperaturePolicy(**{key: policy[key] for key in fields})
                for name, policy in streams.items()}
    epochs = None if version == 1 else {
        name: sensor_epoch_id(policy['sensor_epoch']) for name, policy in streams.items()}
    return policies, epochs


def load_temperature_policies(path):
    """Legacy v1 loader deliberately refuses the separate hardware-phase schema."""
    return _decode_policy_document(_read_policy_document(path), version=1)[0]


def load_temperature_receiver_configuration(path):
    document = _read_policy_document(path)
    version = document.get('version') if isinstance(document, dict) else None
    if type(version) is not int or version not in (1, 2):
        raise ValueError('unsupported receiver policy schema')
    return _decode_policy_document(document, version=version)


def configure_temperature_receiver(app, environ=None):
    """Bad evidence configuration must not take down the legacy receiver."""
    env = os.environ if environ is None else environ
    if env.get('WEATHER_TEMP_EVIDENCE_ENABLE') != '1':
        return None
    try:
        from weather_temperature_receiver import install_temperature_evidence
        policies, epochs = load_temperature_receiver_configuration(env.get('WEATHER_TEMP_EVIDENCE_POLICY'))
        return install_temperature_evidence(app, enabled=True, policies=policies, sensor_epochs=epochs)
    except Exception:
        app.logger.warning('temperature evidence configuration unavailable; legacy receiver retained')
        return None
