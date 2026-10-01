"""Explicit, default-off radiation receiver configuration."""
import json
import os
import stat

from weather_radiation_evidence import RadiationPolicy


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate radiation policy key')
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError('nonfinite radiation policy constant')


def load_radiation_policy(path):
    if not isinstance(path, str) or not os.path.isabs(path):
        raise ValueError('absolute radiation policy path required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        metadata = os.fstat(fd)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o022 or not 1 <= metadata.st_size <= 4096):
            raise ValueError('owned bounded radiation policy file required')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            contents = stream.read(4097)
        if len(contents) > 4096:
            raise ValueError('radiation policy file exceeds bound')
    finally:
        os.close(fd)
    document = json.loads(contents, object_pairs_hook=_object,
                          parse_constant=_nonfinite)
    if (not isinstance(document, dict)
            or set(document) != {'version', 'sensor_id', 'validity_seconds'}
            or type(document['version']) is not int or document['version'] != 1):
        raise ValueError('unsupported radiation policy schema')
    return RadiationPolicy(sensor_id=document['sensor_id'],
                           validity_seconds=document['validity_seconds'])


def configure_radiation_receiver(app, environ=None):
    env = os.environ if environ is None else environ
    if env.get('WEATHER_RADIATION_EVIDENCE_ENABLE') != '1':
        return None
    try:
        from weather_radiation_receiver import install_radiation_evidence
        policy = load_radiation_policy(env.get('WEATHER_RADIATION_EVIDENCE_POLICY'))
        return install_radiation_evidence(app, enabled=True, policy=policy)
    except Exception:
        app.logger.warning('radiation evidence configuration unavailable; legacy receiver retained')
        return None
